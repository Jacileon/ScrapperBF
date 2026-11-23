"""
reader_core/avis_micro_splitter.py — Micro-Split des AVIS (Découpage par Annonce individuelle)

Logique :
  1. Détection géométrique déterministe des rectangles colorés :
     - ROUGE  -> Bandeau de Catégorie (Travaux, Fournitures, Prestations)
     - JAUNE  -> Bandeau d'Émetteur (Autorité contractante)
     - CYAN   -> Bandeau d'Objet = DÉBUT d'une annonce distincte
  2. Chaque bandeau CYAN délimite le début d'un avis d'appel d'offres distinct.
     Une même page peut contenir 2 ou 3 annonces indépendantes.
  3. Le texte est segmenté déterministement entre chaque rectangle sans faire appel
     à un LLM ni à des regex hasardeuses.
  4. Génération d'un fichier Markdown (.md) par annonce avec frontmatter YAML complet.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pdfplumber

log = logging.getLogger("scrapperbf.avis_micro_splitter")


# Sémantique couleur calibrée
def is_red(c) -> bool:
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    r, g, b = c[0], c[1], c[2]
    return r > 0.75 and g < 0.45 and b < 0.45

def is_yellow(c) -> bool:
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    r, g, b = c[0], c[1], c[2]
    return r > 0.70 and g > 0.70 and b < 0.50

def is_cyan(c) -> bool:
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    r, g, b = c[0], c[1], c[2]
    return r < 0.60 and g > 0.60 and b > 0.60

def classify_rect_color(color) -> Optional[str]:
    """Assigne le rôle structurel d'un rectangle selon sa couleur."""
    if is_red(color):
        return "categorie"
    if is_yellow(color):
        return "emetteur"
    if is_cyan(color):
        return "objet"
    return None


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


def clean_slug(text: str, max_len: int = 50) -> str:
    """Génère un slug lisible pour le nom de fichier."""
    clean = re.sub(r'[\r\n\t]+', ' ', text)
    clean = re.sub(r'[^\w\s-]', '', clean, flags=re.UNICODE)
    clean = re.sub(r'\s+', '_', clean).strip('_')
    return clean[:max_len] if clean else "Annonce"


def segment_avis_annonces(
    pdf_path: str,
    avis_range: Optional[Tuple[int, int]],
    output_md_dir: str,
    numero_bulletin: Optional[str] = None,
    date_parution: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Découpe la zone AVIS en annonces unitaires basées sur les bandeaux CYAN.
    Génère les fichiers Markdown correspondants avec frontmatter YAML.
    """
    out_dir = Path(output_md_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        p_start = avis_range[0] if avis_range else 0
        p_end = avis_range[1] if avis_range else total_pages - 1

        # -------------------------------------------------------------
        # 1. Collecte ordonnée de tous les bandeaux de la zone AVIS
        # -------------------------------------------------------------
        all_bands = []
        for p_idx in range(p_start, p_end + 1):
            page = pdf.pages[p_idx]
            w = page.width

            for r in page.rects:
                if r["height"] < 6:
                    continue
                color = r.get("non_stroking_color")
                role = classify_rect_color(color)
                if not role:
                    continue

                # Règle géométrique de largeur minimale
                min_w = w * 0.30 if role == "categorie" else w * 0.45
                if r["width"] < min_w:
                    continue

                txt = _crop_text_rect(page, r)
                all_bands.append({
                    "page_idx": p_idx,
                    "top": r["top"],
                    "bottom": r["bottom"],
                    "role": role,
                    "text": txt,
                })

        # Trier dans l'ordre de lecture
        all_bands.sort(key=lambda b: (b["page_idx"], b["top"]))

        # Dédupliquer les bordures doubles
        unique_bands = []
        seen = set()
        for b in all_bands:
            k = (b["page_idx"], round(b["top"] / 4), b["role"])
            if k not in seen:
                seen.add(k)
                unique_bands.append(b)

        # -------------------------------------------------------------
        # 2. Association des triplets (Catégorie -> Émetteur -> Objet)
        # -------------------------------------------------------------
        cur_cat = "Fournitures et Services"
        cur_emet = "Autorité non spécifiée"
        annonces_plan = []

        for i, b in enumerate(unique_bands):
            if b["role"] == "categorie":
                if b["text"]:
                    cur_cat = b["text"]
            elif b["role"] == "emetteur":
                if b["text"]:
                    cur_emet = b["text"]
            elif b["role"] == "objet":
                annonces_plan.append({
                    "band_idx": i,
                    "categorie": cur_cat,
                    "emetteur": cur_emet,
                    "objet": b["text"] or "Avis de marché public",
                    "page_start": b["page_idx"],
                    "top": b["bottom"], # Le corps démarre sous le bandeau cyan
                })

        log.info("Micro-Split géométrique : %d bandeaux CYAN (annonces) détectés", len(annonces_plan))

        # -------------------------------------------------------------
        # 3. Découpage du texte corps de chaque annonce
        # -------------------------------------------------------------
        results = []
        for idx, ann in enumerate(annonces_plan, start=1):
            band_i = ann["band_idx"]
            current_band = unique_bands[band_i]
            next_band = unique_bands[band_i + 1] if (band_i + 1) < len(unique_bands) else None

            p0 = current_band["page_idx"]
            top0 = current_band["bottom"]

            if next_band:
                p1 = next_band["page_idx"]
                top1 = next_band["top"]
            else:
                p1 = p_end
                top1 = pdf.pages[p1].height

            # Extraction du texte entre les deux frontières
            parts = []
            for pi in range(p0, p1 + 1):
                pg = pdf.pages[pi]
                t = top0 if pi == p0 else 0
                b = top1 if pi == p1 else pg.height
                page_txt = _extract_text_between_y(pg, t, b)
                if page_txt:
                    # Nettoyer les bas de page répétitifs (numéro de page, site web)
                    lines_clean = []
                    for ln in page_txt.splitlines():
                        s = ln.strip()
                        if re.search(r"www\.dgcmef|www\.finances|^\s*\d{1,3}\s*$|N[°o]?\s*\d{3,4}\s*[–-]", s, re.I):
                            continue
                        lines_clean.append(ln)
                    parts.append("\n".join(lines_clean))


            body_text = "\n\n".join(parts).strip()

            # Pages 1-based pour l'utilisateur
            page_debut_num = p0 + 1
            page_fin_num = p1 + 1

            # ---------------------------------------------------------
            # 4. Génération du fichier Markdown
            # ---------------------------------------------------------
            slug = clean_slug(ann["objet"], max_len=45)
            num_clean = clean_slug(numero_bulletin or "Quotidien", max_len=15)
            md_filename = f"{num_clean}_Avis_{idx:02d}_p{page_debut_num}-p{page_fin_num}_{slug}.md"
            md_path = out_dir / md_filename

            md_content = f"""---
bulletin: "{numero_bulletin or 'Inconnu'}"
date_parution: "{date_parution or 'Non spécifiée'}"
index_annonce: {idx}
page_debut: {page_debut_num}
page_fin: {page_fin_num}
categorie: "{ann['categorie']}"
autorite_contractante: "{ann['emetteur']}"
objet: "{ann['objet']}"
methode_decoupage: "geometrique_bandeaux_couleur"
---

# Avis N°{idx:02d} — {ann['objet']}

- **Bulletin :** {numero_bulletin or 'Inconnu'} ({date_parution or 'Non spécifiée'})
- **Pages d'origine :** Page {page_debut_num} à {page_fin_num}
- **Catégorie :** {ann['categorie']}
- **Autorité contractante :** {ann['emetteur']}

---

### Texte Intégral de l'Annonce

{body_text}
"""
            md_path.write_text(md_content, encoding="utf-8")
            log.info("Fichier Markdown unitaire créé : %s", md_filename)

            results.append({
                "index": idx,
                "md_path": str(md_path),
                "page_debut": page_debut_num,
                "page_fin": page_fin_num,
                "categorie": ann["categorie"],
                "emetteur": ann["emetteur"],
                "objet": ann["objet"],
                "taille_texte": len(body_text),
            })

    return results
