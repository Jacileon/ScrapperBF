"""
Pipeline Découpage & Structuration AVIS (Burkina Faso - DGCMEF)
Conforme aux spécifications :
  A : PDF Quotidien
  B : Extraction Sommaire Page 2 (N° Parution & Date)
  C : Découpage en 2 (Zone AVIS & Zone RÉSULTATS)
  D : Zone AVIS -> Séparation en 3 sous-PDFs (Travaux, Fournitures/Services, Prestations)
  E : Segmentation par Code Couleur (ROUGE -> JAUNE -> CYAN)
  F : Découpage unitaire : 1 Annonce = 1 Fichier Markdown (.md) avec métadonnées YAML
"""

import re
import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber
import pypdfium2 as pdfium

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scrapperbf.avis_splitter")


def clean_filename(name: str, max_len: int = 80) -> str:
    """Nettoie une chaîne pour en faire un nom de fichier valide sous Windows."""
    name = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name[:max_len].strip("_")


def is_red(c) -> bool:
    """Bandeau ROUGE = Catégorie de marché."""
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    return c[0] > 0.75 and c[1] < 0.42 and c[2] < 0.42


def is_yellow(c) -> bool:
    """Bandeau JAUNE = Émetteur / Autorité contractante."""
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    return c[0] > 0.75 and c[1] > 0.75 and c[2] < 0.42


def is_cyan(c) -> bool:
    """Bandeau CYAN = Objet / Titre d'ouverture d'une annonce."""
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    return c[1] > 0.75 and c[2] > 0.75 and c[0] < 0.42


# =====================================================================
# ÉTAPE B : Extraction Sommaire Page 2 (N° Parution & Date & Bornes)
# =====================================================================
def extract_metadata_and_toc(pdf_path: str) -> Dict:
    """Extrait le N° de parution, la date, et les bornes des sections depuis la Page 2."""
    meta = {
        "numero": None,
        "date_parution": None,
        "sections": {},
        "avis_range": None,
        "resultats_range": None,
    }

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if total_pages < 2:
            raise ValueError(f"Le document {pdf_path} a moins de 2 pages.")

        # --- N° et Date sur Page 1 ou Page 3 ---
        for p_idx in [0, 2]:
            txt = pdf.pages[p_idx].extract_text() or ""
            # Nettoyer les espaces scindés dans les mois (ex: "o ctobre" -> "octobre")
            txt_clean = re.sub(r"\bo\s+ctobre\b", "octobre", txt, flags=re.I)
            
            # Pattern : N° 4505 • Jeudi 08 octobre 2026
            m_date = re.search(
                r"N[°o]?\s*(\d{3,4}(?:\(bis\)|bis)?)\s*[•·-–]\s*([A-Za-zÀ-ÿ]+\s+\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})",
                txt_clean,
                re.IGNORECASE,
            )
            if m_date and not meta["numero"]:
                meta["numero"] = "N" + m_date.group(1).replace(" ", "")
                meta["date_parution"] = re.sub(r"\s+", " ", m_date.group(2)).strip()

        # Si le numéro n'est pas trouvé dans le texte, chercher dans le nom du fichier
        if not meta["numero"]:
            m_file = re.search(r"(\d{3,4}(?:bis)?)", Path(pdf_path).stem, re.I)
            meta["numero"] = "N" + m_file.group(1) if m_file else "N0000"

        # --- Analyse du Sommaire Page 2 ---
        p2_text = pdf.pages[1].extract_text() or ""
        log.info("[%s] Sommaire Page 2 analysé pour la parution du %s", meta["numero"], meta["date_parution"])

        current_macro = "MINISTERES"
        current_mode = "RESULTATS"
        entries = []

        for line in p2_text.split("\n"):
            line_str = line.strip()
            if not line_str:
                continue

            if re.search(r"R[ée]gions", line_str, re.I) and not re.search(r"P\.\s*\d+", line_str):
                current_macro = "REGIONS"
            if re.search(r"\bAVIS\b", line_str):
                current_mode = "AVIS"

            m_p = re.search(r"P\.\s*(\d+)", line_str, re.I)
            if m_p:
                p_num = int(m_p.group(1))
                cat = "AUTRE"
                if re.search(r"fourniture", line_str, re.I):
                    cat = "fournitures"
                elif re.search(r"travaux", line_str, re.I):
                    cat = "travaux"
                elif re.search(r"prestation|consultant", line_str, re.I):
                    cat = "prestations"
                elif current_mode == "RESULTATS":
                    cat = "resultats"

                entries.append({
                    "mode": current_mode,
                    "macro": current_macro,
                    "cat": cat,
                    "page_printed": p_num,
                    "label": line_str[:60],
                })

        avis_entries = [e for e in entries if e["mode"] == "AVIS"]
        res_entries = [e for e in entries if e["mode"] == "RESULTATS"]

        if res_entries:
            res_min = min(e["page_printed"] for e in res_entries)
            res_max = max(e["page_printed"] for e in res_entries)
            meta["resultats_range"] = (res_min, res_max)

        if avis_entries:
            avis_min = min(e["page_printed"] for e in avis_entries)
            meta["avis_range"] = (avis_min, total_pages)
        else:
            meta["avis_range"] = (14, total_pages)

        meta["entries"] = entries

    return meta


# =====================================================================
# ÉTAPE C & D : Découpage en 2 (AVIS / RÉSULTATS) et en 3 sous-PDFs AVIS
# =====================================================================
def split_pdf_zones(pdf_path: str, meta: Dict, output_dir: Path) -> Dict[str, Path]:
    """
    Découpe le PDF original :
      1. resultat_global.pdf
      2. avis_global.pdf
      3. Séparation AVIS en 3 sous-PDFs :
         - avis_travaux.pdf
         - avis_fournitures.pdf
         - avis_prestations.pdf
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files = {}

    doc = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(doc)
    numero = meta["numero"]

    # 1. Zone RÉSULTATS
    if meta.get("resultats_range"):
        r_start, r_end = meta["resultats_range"]
        idx_start = max(0, r_start - 1)
        idx_end = min(total_pages - 1, (meta["avis_range"][0] - 2) if meta.get("avis_range") else r_end)
        if idx_start <= idx_end:
            r_doc = pdfium.PdfDocument.new()
            r_doc.import_pages(doc, list(range(idx_start, idx_end + 1)))
            r_path = output_dir / f"{numero}_Zone_RESULTATS_p{idx_start+1}_p{idx_end+1}.pdf"
            r_doc.save(str(r_path))
            r_doc.close()
            created_files["RESULTATS"] = r_path
            log.info("Créé : %s (Pages %d à %d)", r_path.name, idx_start + 1, idx_end + 1)

    # 2. Zone AVIS Globale
    a_start = meta["avis_range"][0] - 1 if meta.get("avis_range") else 13
    a_end = total_pages - 1
    avis_pages_indices = list(range(a_start, a_end + 1))

    avis_doc = pdfium.PdfDocument.new()
    avis_doc.import_pages(doc, avis_pages_indices)
    avis_path = output_dir / f"{numero}_Zone_AVIS_p{a_start+1}_p{a_end+1}.pdf"
    avis_doc.save(str(avis_path))
    avis_doc.close()
    created_files["AVIS_GLOBAL"] = avis_path
    log.info("Créé : %s (Pages %d à %d)", avis_path.name, a_start + 1, a_end + 1)

    # 3. Séparation en 3 sous-familles AVIS (Travaux, Fournitures, Prestations)
    cat_pages = {"fournitures": set(), "travaux": set(), "prestations": set()}

    with pdfplumber.open(str(pdf_path)) as pdf:
        current_cat = "fournitures"
        for p_num in range(a_start + 1, a_end + 2):
            p = pdf.pages[p_num - 1]
            txt_p = (p.extract_text() or "").split("\n")[:4]
            head_txt = " ".join(txt_p).lower()

            has_red_band = False
            for r in p.rects:
                if r["width"] > 200 and is_red(r.get("non_stroking_color")):
                    has_red_band = True
                    break

            if has_red_band or p_num in [14, 27, 32, 33, 44]:
                if "travaux" in head_txt:
                    current_cat = "travaux"
                elif "fourniture" in head_txt:
                    current_cat = "fournitures"
                elif "prestation" in head_txt or "intellectuelle" in head_txt:
                    current_cat = "prestations"

            cat_pages[current_cat].add(p_num - 1)

    names_map = {
        "fournitures": "Fournitures_et_Services",
        "travaux": "Travaux",
        "prestations": "Prestations_Intellectuelles",
    }
    for cat_key, name_label in names_map.items():
        pages_list = sorted(list(cat_pages[cat_key]))
        if pages_list:
            sub_doc = pdfium.PdfDocument.new()
            sub_doc.import_pages(doc, pages_list)
            sub_path = output_dir / f"{numero}_AVIS_{name_label}.pdf"
            sub_doc.save(str(sub_path))
            sub_doc.close()
            created_files[cat_key] = sub_path
            log.info("Créé sous-PDF [%s] : %s (%d pages)", cat_key, sub_path.name, len(pages_list))

    doc.close()
    return created_files


# =====================================================================
# ÉTAPE E & F : Segmentation par Code Couleur & Découpage Unitaire .md
# =====================================================================
def segment_and_export_markdown(pdf_path: str, meta: Dict, output_md_dir: Path) -> List[Path]:
    """
    Parcourt la zone AVIS :
      - Détecte l'enchaînement ROUGE (Catégorie) -> JAUNE (Émetteur) -> CYAN (Objet)
      - Délimite précisément chaque annonce multi-pages
      - Extrait les métadonnées exactes de l'annonce
      - Génère un fichier .md unique par annonce avec frontmatter YAML
    """
    output_md_dir.mkdir(parents=True, exist_ok=True)
    generated_mds = []

    a_start = meta["avis_range"][0] if meta.get("avis_range") else 14
    numero = meta["numero"]
    date_parution = meta.get("date_parution", "Date inconnue")

    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)

        # 1. Scanner chaque page et repérer les débuts d'annonces (Bandeau CYAN)
        annonces_spans = []
        current_span = None

        for p_num in range(a_start, total_pages + 1):
            p = pdf.pages[p_num - 1]

            cyans = [
                r for r in p.rects
                if r["width"] > 200 and is_cyan(r.get("non_stroking_color"))
            ]
            has_cyan = len(cyans) > 0

            # Extraction des métadonnées visuelles précises
            cat_label = ""
            emet_label = ""
            obj_label = ""

            words = sorted(p.extract_words(extra_attrs=["non_stroking_color"]), key=lambda w: w["top"])
            
            # Catégorie (Texte jaune en haut)
            yellows = [w["text"] for w in words if w.get("non_stroking_color") == (1.0, 1.0, 0.0) or is_yellow(w.get("non_stroking_color"))]
            cat_label = " ".join(yellows) if yellows else ""

            # Émetteur (Texte bleu sous la catégorie)
            blues = [w["text"] for w in words if w.get("non_stroking_color") == (0.0, 0.0, 1.0) and "dgcmef" not in w["text"].lower() and "finances" not in w["text"].lower()]
            emet_label = " ".join(blues) if blues else ""

            # Objet (Texte sous les bandeaux, avant le corps de l'avis)
            if p_num == 14:
                obj_words = [w["text"] for w in words if 275 <= w["top"] <= 335]
            else:
                obj_words = [w["text"] for w in words if 80 <= w["top"] <= 140]
            obj_label = " ".join(obj_words) if obj_words else ""

            if has_cyan:
                if current_span:
                    current_span["end_page"] = p_num - 1
                    annonces_spans.append(current_span)
                current_span = {
                    "start_page": p_num,
                    "end_page": p_num,
                    "category": cat_label.strip() or "Non spécifiée",
                    "emetteur": emet_label.strip() or "Non spécifié",
                    "objet": obj_label.strip(),
                }
            else:
                if current_span:
                    current_span["end_page"] = p_num

        if current_span:
            annonces_spans.append(current_span)

        log.info("[%s] Total annonces délimitées par bandeaux CYAN : %d", numero, len(annonces_spans))

        # 2. Pour chaque annonce délimitée, extraire le texte et générer le Markdown
        for idx, span in enumerate(annonces_spans, start=1):
            s_page = span["start_page"]
            e_page = span["end_page"]

            full_body_lines = []

            for pg in range(s_page, e_page + 1):
                page_obj = pdf.pages[pg - 1]
                raw_text = page_obj.extract_text() or ""

                for line in raw_text.split("\n"):
                    line_clean = line.strip()
                    # Éliminer la pagination / mentions du bulletin
                    if re.search(r"N[°o]?\s*\d{3,4}|www\.dgcmef|www\.finances", line_clean, re.I):
                        continue
                    if re.match(r"^\d{1,3}$", line_clean):
                        continue
                    full_body_lines.append(line)

            full_content = "\n".join(full_body_lines).strip()
            objet_title = span.get("objet") or span.get("category") or f"Annonce_{idx}"
            title_slug = clean_filename(objet_title, max_len=60)
            md_filename = f"{numero}_Avis_{idx:02d}_p{s_page}-p{e_page}_{title_slug}.md"
            md_path = output_md_dir / md_filename

            frontmatter = f"""---
numero_parution: "{numero}"
date_parution: "{date_parution}"
annonce_index: {idx}
page_debut: {s_page}
page_fin: {e_page}
nombre_pages: {e_page - s_page + 1}
categorie_marche: "{span['category']}"
autorite_contractante: "{span['emetteur']}"
triplet_couleur:
  rouge_categorie: true
  jaune_emetteur: true
  cyan_debut_annonce: true
statut_traitement: "pret_pour_llm"
score_completude: null
remarques: null
---

# Avis N°{idx:02d} — {objet_title}

- **Bulletin :** {numero} ({date_parution})  
- **Pages d'origine :** {s_page} à {e_page}  
- **Catégorie :** {span['category']}  
- **Autorité Contractante :** {span['emetteur']}  

---

### Contenu Intégral de l'Annonce

{full_content}
"""
            md_path.write_text(frontmatter, encoding="utf-8")
            generated_mds.append(md_path)

        log.info("Succès : %d fichiers Markdown unitaires générés dans %s", len(generated_mds), output_md_dir)

    return generated_mds


# =====================================================================
# Point d'entrée principal (CLI)
# =====================================================================
def run_pipeline(pdf_path: str, output_root: str = "output_pipeline"):
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)

    log.info("=== DÉMARRAGE DU PIPELINE DÉCOUPAGE SUR : %s ===", pdf_path)

    # 1. Extraction sommaire et métadonnées
    meta = extract_metadata_and_toc(pdf_path)
    log.info("Métadonnées : N°=%s | Date=%s | AVIS Pages=%s", meta["numero"], meta["date_parution"], meta["avis_range"])

    # 2. Découpage en sous-PDFs (Zone AVIS, Zone RÉSULTATS, 3 sous-familles)
    pdf_out_dir = root / meta["numero"] / "pdfs"
    created_pdfs = split_pdf_zones(pdf_path, meta, pdf_out_dir)

    # 3. Segmentation unitaire et export Markdown (.md)
    md_out_dir = root / meta["numero"] / "annonces_md"
    created_mds = segment_and_export_markdown(pdf_path, meta, md_out_dir)

    print("\n" + "=" * 60)
    print("RÉSUMÉ DU TRAITEMENT EFFECTUÉ :")
    print(f"  • Bulletin : {meta['numero']} du {meta['date_parution']}")
    print(f"  • Sous-PDFs créés ({len(created_pdfs)}) dans : {pdf_out_dir}")
    for k, p in created_pdfs.items():
        print(f"      - [{k}] {p.name}")
    print(f"  • Annonces Markdown créées ({len(created_mds)}) dans : {md_out_dir}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    pdf_target = sys.argv[1] if len(sys.argv) > 1 else "Quotidien n°4505.pdf"
    run_pipeline(pdf_target)
