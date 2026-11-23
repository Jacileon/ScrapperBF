"""
prod_pipeline/avis_micro_splitter.py — Micro-Split géométrique unitaire des AVIS.

Principe :
1. Dans la zone AVIS, une seule page contient souvent 2 ou 3 annonces distinctes.
2. Détection géométrique déterministe des rectangles colorés :
   - ROUGE  -> Bandeau de Catégorie (Fournitures, Travaux, Prestations)
   - JAUNE  -> Bandeau d'Émetteur (Autorité contractante)
   - CYAN   -> Bandeau d'Objet = DÉBUT d'une annonce distincte
3. Chaque bandeau CYAN délimite le début d'un avis d'appel d'offres distinct.
4. Le texte est segmenté déterministement entre chaque rectangle sans faire appel à un LLM ni à des regex hasardeuses.
5. Export d'un fichier Markdown (.md) par annonce avec frontmatter YAML complet.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import pdfplumber

from prod_pipeline.colors import (
    classify_color, is_valid_banner_geometry, dedup_rectangles,
    is_red, is_yellow, is_cyan,
    ROLE_ROUGE, ROLE_JAUNE, ROLE_CYAN
)

log = logging.getLogger("scrapperbf.avis_micro_splitter")


def detect_printed_page_number(page) -> int:
    """
    Détecte le numéro de page officiel imprimé en bas à droite du bulletin.
    Retourne l'entier exact imprimé, ou page.page_number en repli.
    """
    w, h = page.width, page.height
    try:
        # Zone basse droite : derniers 55 pt verticaux, 30% droits de la page
        crop = page.crop((w * 0.70, h - 55, w, h - 10))
        words = crop.extract_words()
        candidates = []
        for wd in words:
            text = wd["text"].strip()
            if text.isdigit():
                candidates.append((int(text), wd["x0"], wd["top"]))
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        crop_full_footer = page.crop((0, h - 55, w, h - 10))
        txt = crop_full_footer.extract_text() or ""
        m = re.findall(r'\b(\d{1,3})\b', txt)
        if m:
            valid = [int(val) for val in m if int(val) not in (2024, 2025, 2026) and int(val) < 250]
            if valid:
                return valid[-1]
    except Exception:
        pass
    return page.page_number


def _clean_slug(text: str, max_len: int = 50) -> str:
    """Génère un slug lisible pour le nom de fichier."""
    clean = re.sub(r'[\r\n\t]+', ' ', text or "")
    clean = re.sub(r'[^\w\s-]', '', clean, flags=re.UNICODE)
    clean = re.sub(r'\s+', '_', clean).strip('_')
    return clean[:max_len] if clean else "Annonce"


def _crop_text_rect(page, rect, pad_bottom: float = 2.0) -> str:
    """Extrait le texte contenu dans la boîte englobante d'un bandeau."""
    try:
        x0 = max(0, rect["x0"] - 2)
        x1 = min(page.width, rect["x1"] + 2)
        top = max(0, rect["top"] - 1)
        bottom = min(page.height, rect["bottom"] + pad_bottom)
        c = page.crop((x0, top, x1, bottom))
        return " ".join((c.extract_text() or "").split())
    except Exception:
        return ""


def _extract_text_between_y(page, top: float, bottom: float) -> str:
    """Extrait le texte d'une page entre deux positions verticales Y."""
    try:
        if bottom <= top + 1:
            return ""
        c = page.crop((0, max(0, top), page.width, min(page.height, bottom)))
        return (c.extract_text() or "").strip()
    except Exception:
        return ""


def segment_avis_annonces(
    pdf_path: str,
    avis_range: Optional[Tuple[int, int]],
    output_md_dir: str,
    bulletin_info: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Découpe la zone AVIS en annonces unitaires basées sur les bandeaux CYAN.
    Génère un fichier .md par annonce avec frontmatter YAML complet.
    """
    out_dir = Path(output_md_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    info = bulletin_info or {}
    numero = info.get("numero", "N°XXXX")
    date_str = info.get("date_str", "")

    annonces_crees = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        p_start = avis_range[0] if avis_range else 0
        p_end = min(total_pages - 1, avis_range[1]) if avis_range else (total_pages - 1)

        # 1. Collecte séquentielle de tous les bandeaux dans la zone AVIS
        banner_events = []

        for pi in range(p_start, p_end + 1):
            page = pdf.pages[pi]
            w = page.width

            valid_rects = [
                r for r in page.rects
                if is_valid_banner_geometry(r, w, min_width_ratio=0.20, min_height=4.0)
            ]
            unique_rects = dedup_rectangles(valid_rects)

            # Séparer et fusionner les bandeaux multilignes par rôle
            by_role = {}
            for r in unique_rects:
                col = r.get("non_stroking_color")
                role = classify_color(col)
                if role in (ROLE_ROUGE, ROLE_JAUNE, ROLE_CYAN):
                    by_role.setdefault(role, []).append(r)

            page_banners = []
            for role, r_list in by_role.items():
                r_list.sort(key=lambda x: x["top"])
                merged_role = []
                for r in r_list:
                    if not merged_role:
                        merged_role.append(dict(r))
                    else:
                        last = merged_role[-1]
                        # Si chevauchement ou bandeaux verticaux contigus (distance <= 6.0 pt)
                        if r["top"] <= last["bottom"] + 6.0:
                            last["top"] = min(last["top"], r["top"])
                            last["bottom"] = max(last["bottom"], r["bottom"])
                            last["x0"] = min(last["x0"], r["x0"])
                            last["x1"] = max(last["x1"], r["x1"])
                        else:
                            merged_role.append(dict(r))

                for mr in merged_role:
                    txt = _crop_text_rect(page, mr)
                    if len(txt.strip()) >= 3:
                        page_banners.append({
                            "page_idx": pi,
                            "page_num": pi + 1,
                            "top": mr["top"],
                            "bottom": mr["bottom"],
                            "role": role,
                            "text": txt,
                            "rect": mr
                        })

            # Trier les bandeaux de la page par position Y
            page_banners.sort(key=lambda x: x["top"])
            banner_events.extend(page_banners)

        # 2. Construction déterministe des annonces avec le pattern strict (ROUGE -> JAUNE -> CYAN)
        # Chaque annonce débute par son triplet (ou bandeau CYAN)
        annonces_patterns = []
        
        # On regroupe les séquences de bandeaux
        current_cat_banner = None
        current_emet_banner = None

        for b in banner_events:
            if b["role"] == ROLE_ROUGE and b["text"]:
                current_cat_banner = b
            elif b["role"] == ROLE_JAUNE and b["text"]:
                current_emet_banner = b
            elif b["role"] == ROLE_CYAN:
                # Marqueur d'annonce détecté
                # Le début physique de l'en-tête de cette annonce est son bandeau ROUGE (ou JAUNE à défaut)
                cut_banner = current_cat_banner or current_emet_banner or b
                annonces_patterns.append({
                    "cyan_page_idx": b["page_idx"],
                    "cyan_bottom": b["bottom"],
                    "cut_page_idx": cut_banner["page_idx"],
                    "cut_top": cut_banner["top"],
                    "objet": b["text"] or "Avis d'appel d'offres",
                    "categorie": (current_cat_banner["text"] if current_cat_banner else "Marchés publics"),
                    "emetteur": (current_emet_banner["text"] if current_emet_banner else "Autorité contractante non spécifiée")
                })
                # Une fois consommé pour cette annonce, on réinitialise pour capturer le prochain pattern spécifique
                current_cat_banner = None
                current_emet_banner = None

        # Déduplication stricte des annonces successives redondantes
        clean_annonces = []
        for a in annonces_patterns:
            if clean_annonces:
                prev = clean_annonces[-1]
                if prev["cyan_page_idx"] == a["cyan_page_idx"] and (abs(prev["cut_top"] - a["cut_top"]) < 18.0 or prev["objet"] == a["objet"]):
                    continue
            clean_annonces.append(a)
        annonces_patterns = clean_annonces

        # Si aucun bandeau CYAN n'a été trouvé, fallback sur découpage par page
        if not annonces_patterns:
            log.warning("Aucun bandeau CYAN détecté dans la zone Avis. Fallback par page.")
            for pi in range(p_start, p_end + 1):
                page = pdf.pages[pi]
                txt = (page.extract_text() or "").strip()
                if len(txt) > 50:
                    annonces_patterns.append({
                        "cyan_page_idx": pi,
                        "cyan_bottom": 10.0,
                        "cut_page_idx": pi,
                        "cut_top": 0.0,
                        "objet": f"Avis Page {pi+1}",
                        "categorie": "Général",
                        "emetteur": "Non spécifié"
                    })

        # 3. Extraction géométrique du texte : du bas du CYAN jusqu'au sommet du ROUGE du pattern suivant
        for idx, a in enumerate(annonces_patterns):
            p0 = a["cyan_page_idx"]
            bottom0 = a["cyan_bottom"]

            # Fin = le sommet (cut_top) du pattern de l'annonce suivante (son bandeau ROUGE)
            if idx + 1 < len(annonces_patterns):
                nxt = annonces_patterns[idx + 1]
                p1 = nxt["cut_page_idx"]
                top1 = nxt["cut_top"]
            else:
                p1 = p_end
                top1 = pdf.pages[p1].height

            # Assemblage du texte entre les bornes géométriques
            text_parts = []
            contributing_pages = []
            footer_keywords = ("www.dgcmef.gov.bf", "www.finances.gov.bf", "n°3827", "n° 3827", "quotidien n°")
            for pi in range(p0, p1 + 1):
                pg = pdf.pages[pi]
                y_start = (bottom0 + 1.0) if pi == p0 else 0.0
                y_end = top1 if pi == p1 else pg.height
                part = _extract_text_between_y(pg, y_start, y_end)
                if part:
                    # Éliminer les résidus qui ne sont que le footer de pied de page
                    cleaned_part = "\n".join(
                        l for l in part.splitlines()
                        if not any(kw in l.lower() for kw in footer_keywords)
                    ).strip()
                    if len(cleaned_part) > 100:
                        text_parts.append(part)
                        contributing_pages.append(pi)

            body_text = "\n\n".join(text_parts).strip()

            # Numéros officiels imprimés en bas à droite calculés sur les pages ayant réellement du contenu
            first_pi = contributing_pages[0] if contributing_pages else p0
            last_pi = contributing_pages[-1] if contributing_pages else p0
            printed_p0 = detect_printed_page_number(pdf.pages[first_pi])
            printed_p1 = detect_printed_page_number(pdf.pages[last_pi])
            pages_span = f"p. {printed_p0}" if printed_p0 == printed_p1 else f"p. {printed_p0} à {printed_p1}"

            # Détermination de la macro_section (MIMOD vs Region)
            is_region = bool(re.search(r'\b(r[ée]gion|commune|mairie)\b', a["emetteur"], re.I))
            macro_sec = "Avis-Region" if is_region else "Avis-MIMOD"

            # Nettoyage des titres et slug
            clean_num = _clean_slug(numero)
            slug_obj = _clean_slug(a["objet"], max_len=40)
            slug_cat = _clean_slug(a["categorie"], max_len=25)

            annonce_id = f"{clean_num}_avis_{idx + 1:03d}"
            filename = f"{annonce_id}_{slug_cat}_{slug_obj}.md"
            target_path = out_dir / filename

            # Création du Markdown avec frontmatter YAML
            md_lines = [
                "---",
                f"id: \"{annonce_id}\"",
                f"bulletin: \"{numero}\"",
                f"date_parution: \"{date_str}\"",
                f"macro_section: \"{macro_sec}\"",
                f"categorie: \"{a['categorie']}\"",
                f"autorite_contractante: \"{a['emetteur']}\"",
                f"objet: \"{a['objet']}\"",
                f"pages: \"{pages_span}\"",
                "type_document: \"AVIS\"",
                "---",
                "",
                f"# {a['objet']}",
                f"- **Autorité contractante :** {a['emetteur']}",
                f"- **Catégorie :** {a['categorie']}",
                f"- **Source :** Bulletin {numero} ({pages_span})",
                "",
                "## Contenu intégral de l'annonce",
                "",
                body_text or "(Texte non extrait ou annonce sous forme de tableau complexe)"
            ]

            target_path.write_text("\n".join(md_lines), encoding="utf-8")
            log.info("Annonce unitaire AVIS créée : %s", target_path.name)

            annonces_crees.append({
                "id": annonce_id,
                "fichier": str(target_path),
                "objet": a["objet"],
                "emetteur": a["emetteur"],
                "categorie": a["categorie"],
                "pages": pages_span,
                "taille_texte": len(body_text)
            })

    return annonces_crees
