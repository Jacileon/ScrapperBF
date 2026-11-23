"""
reader_core/zone_pdf_generator.py — Niveau 2 : Génération physique des sous-PDFs de Zones

Ce module découpe le PDF original et sauvegarde physiquement les sous-fichiers :
  - resultat_global : {numero}_Zone_RESULTATS_p{debut}_p{fin}.pdf
  - avis_global     : {numero}_Zone_AVIS_p{debut}_p{fin}.pdf
  - sous-PDFs AVIS par famille (optionnel ou configuré) :
      * {numero}_AVIS_Fournitures_et_Services.pdf
      * {numero}_AVIS_Travaux.pdf
      * {numero}_AVIS_Prestations_Intellectuelles.pdf
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
import pypdfium2 as pdfium
import pdfplumber

log = logging.getLogger("scrapperbf.zone_generator")


def extract_numero_and_date(pdf_path: str) -> Tuple[str, Optional[str]]:
    """
    Détecte le numéro officiel du Quotidien (ex: N°4504) et sa date de parution.
    Priorité au texte de la première page, fallback sur le nom de fichier.
    """
    stem = Path(pdf_path).stem
    m_num = re.search(r'[Nn][°o]?\s*(\d{3,4}(?:[-_]\d{3,4})?(?:\s*bis)?)', stem, re.IGNORECASE)
    numero_default = f"N°{m_num.group(1).replace('_', '-')}" if m_num else stem

    date_str = None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            txt = pdf.pages[0].extract_text() or ""
            # Chercher le numéro exact
            m_txt_num = re.search(r'N[°o]\s*(\d{3,4}(?:[-_]\d{3,4})?(?:\s*bis)?)', txt[:300], re.IGNORECASE)
            if m_txt_num:
                numero_default = f"N°{m_txt_num.group(1)}"

            # Chercher la date de parution sur la ligne du numéro officiel du bulletin
            for line in txt.splitlines()[:20]:
                if m_txt_num and m_txt_num.group(1) in line:
                    m_d = re.search(r'(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*(\d{1,2}(?:er)?\s+[a-zéûë]+\s+\d{4})', line, re.IGNORECASE)
                    if m_d:
                        date_str = m_d.group(0).strip()
                        break
            if not date_str:
                m_date = re.search(r'(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2}(?:er)?\s+[a-zéûë]+\s+\d{4})', txt[:500], re.IGNORECASE)
                if m_date:
                    date_str = m_date.group(0).strip()

    except Exception:
        pass

    clean_numero = re.sub(r'[\\/*?:"<>|]', '_', numero_default).strip()
    return clean_numero, date_str


def generate_zone_pdfs(
    pdf_path: str,
    zones: Dict[str, Any],
    output_dir: str,
    split_categories: bool = True
) -> Dict[str, Path]:
    """
    Génère les sous-PDFs physiques pour les zones RÉSULTATS et AVIS.
    
    Retourne un dictionnaire des chemins créés :
      {
         "RESULTATS": Path,
         "AVIS_GLOBAL": Path,
         "fournitures": Path (optionnel),
         "travaux": Path (optionnel),
         "prestations": Path (optionnel)
      }
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    created_files = {}
    numero, date_parution = extract_numero_and_date(pdf_path)

    doc = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(doc)

    # -------------------------------------------------------------
    # 1. Génération physique du sous-PDF Zone RÉSULTATS
    # -------------------------------------------------------------
    r_zone = zones.get("RESULTATS")
    if r_zone:
        r_start, r_end = r_zone
        if 0 <= r_start <= r_end < total_pages:
            r_doc = pdfium.PdfDocument.new()
            r_doc.import_pages(doc, list(range(r_start, r_end + 1)))
            r_filename = f"{numero}_Zone_RESULTATS_p{r_start+1}_p{r_end+1}.pdf"
            r_path = out_path / r_filename
            r_doc.save(str(r_path))
            r_doc.close()
            created_files["RESULTATS"] = r_path
            log.info("Sous-PDF RÉSULTATS créé : %s (%d pages)", r_filename, (r_end - r_start + 1))

    # -------------------------------------------------------------
    # 2. Génération physique du sous-PDF Zone AVIS (Global)
    # -------------------------------------------------------------
    a_zone = zones.get("AVIS")
    if a_zone:
        a_start, a_end = a_zone
        if 0 <= a_start <= a_end < total_pages:
            a_doc = pdfium.PdfDocument.new()
            a_doc.import_pages(doc, list(range(a_start, a_end + 1)))
            a_filename = f"{numero}_Zone_AVIS_p{a_start+1}_p{a_end+1}.pdf"
            a_path = out_path / a_filename
            a_doc.save(str(a_path))
            a_doc.close()
            created_files["AVIS_GLOBAL"] = a_path
            log.info("Sous-PDF AVIS GLOBAL créé : %s (%d pages)", a_filename, (a_end - a_start + 1))

            # ---------------------------------------------------------
            # 3. Sous-catégorisation en 3 PDFs (Travaux / Fournitures / Prestations)
            # ---------------------------------------------------------
            if split_categories:
                cat_pages = {"fournitures": [], "travaux": [], "prestations": []}
                current_cat = "fournitures"

                with pdfplumber.open(str(pdf_path)) as pdf:
                    for p_idx in range(a_start, a_end + 1):
                        page = pdf.pages[p_idx]
                        txt = (page.extract_text() or "").lower()
                        head = " ".join(txt.splitlines()[:5])

                        # Vérifier s'il y a un changement de famille
                        if "travaux" in head:
                            current_cat = "travaux"
                        elif "fourniture" in head:
                            current_cat = "fournitures"
                        elif "prestation" in head or "consultant" in head:
                            current_cat = "prestations"

                        cat_pages[current_cat].append(p_idx)

                cat_labels = {
                    "fournitures": "Fournitures_et_Services",
                    "travaux": "Travaux",
                    "prestations": "Prestations_Intellectuelles",
                }
                for c_key, pages_list in cat_pages.items():
                    if pages_list:
                        sub_doc = pdfium.PdfDocument.new()
                        sub_doc.import_pages(doc, pages_list)
                        sub_name = f"{numero}_AVIS_{cat_labels[c_key]}.pdf"
                        sub_path = out_path / sub_name
                        sub_doc.save(str(sub_path))
                        sub_doc.close()
                        created_files[c_key] = sub_path
                        log.info("Sous-PDF [%s] créé : %s (%d pages)", c_key, sub_name, len(pages_list))

    doc.close()
    return created_files
