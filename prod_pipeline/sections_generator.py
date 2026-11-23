"""
prod_pipeline/sections_generator.py — Génération physique des sous-PDFs et conversion Markdown.

Rôles :
1. Découpage physique des sous-PDFs de zones dans `01_sections_pdf/` via `pypdfium2` :
   - Respect strict de la nomenclature :
     - N°XXXX-Avis-MIMOD-fournitures_et_services_courants.pdf
     - N°XXXX-Avis-MIMOD-travaux.pdf
     - N°XXXX-Avis-MIMOD-prestations_intellectuelles.pdf
     - N°XXXX-Avis-Region-fournitures_et_services_courants.pdf
     - N°XXXX-Avis-Region-travaux.pdf
     - N°XXXX-Avis-Region-prestations_intellectuelles.pdf
     - N°XXXX-Resultats-MIMOD.pdf
     - N°XXXX-Resultats-Region.pdf
2. Conversion intégrale en Markdown structuré dans `02_sections_md/` via `pdfplumber` :
   - Fichiers `.md` portant exactement le même radical que les sous-PDFs.
   - Préservation fidèle des tableaux en format Markdown (| col 1 | col 2 | ... |).
   - Pagination traçable (ancres `## Page X (PDF p. Y)`).
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import pdfplumber
import pypdfium2 as pdfium

from prod_pipeline.light_ocr import needs_ocr, recover_page_text_if_needed

log = logging.getLogger("scrapperbf.sections_generator")


def _format_markdown_table(table_matrix: List[List[Optional[str]]]) -> str:
    """
    Convertit une matrice de cellules brutes en tableau Markdown GitHub Flavored.
    Gère le nettoyage des sauts de ligne internes et aligne les colonnes.
    """
    if not table_matrix:
        return ""

    # Nettoyage et normalisation
    cleaned_rows = []
    max_cols = 0
    for row in table_matrix:
        cleaned_cells = []
        for cell in row:
            txt = (cell or "").strip()
            # Remplacement des retours chariots multiples par des espaces ou <br>
            txt = re.sub(r'\s*\n\s*', ' ', txt)
            # Échapper les barres verticales dans le texte
            txt = txt.replace('|', '\\|')
            cleaned_cells.append(txt)
        if any(c for c in cleaned_cells): # Éviter les lignes 100% vides
            cleaned_rows.append(cleaned_cells)
            max_cols = max(max_cols, len(cleaned_cells))

    if not cleaned_rows or max_cols == 0:
        return ""

    # Harmoniser la largeur de toutes les lignes
    for row in cleaned_rows:
        while len(row) < max_cols:
            row.append("")

    lines = []
    # En-tête (première ligne)
    header = cleaned_rows[0]
    lines.append("| " + " | ".join(header) + " |")
    # Ligne de séparation
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # Lignes de données
    for row in cleaned_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def generate_sections(
    pdf_path: str,
    sections: List[Dict[str, Any]],
    output_pdf_dir: str,
    output_md_dir: str,
    bulletin_info: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Génère physiquement les sous-PDFs et les fichiers Markdown de section.
    """
    out_pdf_path = Path(output_pdf_dir)
    out_md_path = Path(output_md_dir)
    out_pdf_path.mkdir(parents=True, exist_ok=True)
    out_md_path.mkdir(parents=True, exist_ok=True)

    info = bulletin_info or {}
    numero = info.get("numero", "N°XXXX")
    date_str = info.get("date_str", "")

    generated_records = []

    # 1. Génération physique des sous-PDFs avec pypdfium2
    src_doc = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(src_doc)

    for sec in sections:
        sec_name = sec["name"]
        start_idx = sec["start_idx"]
        end_idx = min(total_pages - 1, sec["end_idx"])

        if start_idx > end_idx:
            log.warning("Intervalle invalide pour %s : [%d, %d]", sec_name, start_idx, end_idx)
            continue

        target_pdf = out_pdf_path / f"{sec_name}.pdf"
        sub_doc = pdfium.PdfDocument.new()
        pages_to_import = list(range(start_idx, end_idx + 1))
        sub_doc.import_pages(src_doc, pages_to_import)
        sub_doc.save(str(target_pdf))
        sub_doc.close()

        sec["file_pdf"] = str(target_pdf)
        log.info("Sous-PDF généré : %s (p. %d-%d)", target_pdf.name, start_idx + 1, end_idx + 1)

    src_doc.close()

    # 2. Conversion Markdown intégrale avec pdfplumber
    with pdfplumber.open(pdf_path) as plumber_pdf:
        for sec in sections:
            sec_name = sec["name"]
            start_idx = sec["start_idx"]
            end_idx = min(len(plumber_pdf.pages) - 1, sec["end_idx"])

            if start_idx > end_idx:
                continue

            target_md = out_md_path / f"{sec_name}.md"

            md_content = [
                f"# Section : {sec_name}",
                f"- **Bulletin :** {numero}" + (f" ({date_str})" if date_str else ""),
                f"- **Contexte :** {sec.get('context', 'Inconnu')}",
                f"- **Catégorie :** {sec.get('category', 'Général')}",
                f"- **Type de marché :** {sec.get('type_marche') or 'Non spécifié'}",
                f"- **Pages du bulletin :** {start_idx + 1} à {end_idx + 1} (Total : {end_idx - start_idx + 1} pages)",
                f"- **Stratégie de découpe :** {sec.get('strategy', 'SOMMAIRE')}",
                "\n---\n"
            ]

            is_avis = (sec.get("context") == "Avis")

            for pi in range(start_idx, end_idx + 1):
                page = plumber_pdf.pages[pi]
                page_num_doc = pi + 1
                md_content.append(f"## Page {page_num_doc}\n")

                # Extraction du texte courant (pour capturer les préambules et paragraphes hors table)
                page_text = page.extract_text() or ""
                # Repli LightOCR si page scannée ou corrompue
                if needs_ocr(page_text)[0]:
                    page_text, ocr_diag = recover_page_text_if_needed(pdf_path, pi, page_text)
                    if ocr_diag.get("ocr_applique"):
                        md_content.append("> [!NOTE]\n> *Texte récupéré via LightOCR*\n")

                if is_avis:
                    # En section AVIS : restitution intégrale du texte sans troncature
                    md_content.append(page_text.strip())
                    md_content.append("\n")
                else:
                    # En section RÉSULTATS : extraction et mise en forme des vrais tableaux
                    tables = page.extract_tables()
                    real_tables = [t for t in tables if t and len(t) >= 2 and len(t[0]) >= 2]
                    if real_tables:
                        for tbl in real_tables:
                            t_md = _format_markdown_table(tbl)
                            if t_md:
                                md_content.append(t_md)
                                md_content.append("\n")

                        # Conserver tout le contexte textuel hors table SANS TRONCATURE
                        all_table_text = " ".join(" ".join(str(c) for c in row if c) for tbl in real_tables for row in tbl)
                        extra_lines = []
                        for l in page_text.splitlines():
                            clean_l = l.strip()
                            if clean_l and clean_l[:35] not in all_table_text:
                                extra_lines.append(clean_l)
                        if extra_lines:
                            md_content.append("### Contexte & Préambule")
                            md_content.append("\n".join(extra_lines))
                            md_content.append("\n")
                    else:
                        md_content.append(page_text.strip())
                        md_content.append("\n")

            target_md.write_text("\n".join(md_content), encoding="utf-8")
            sec["file_md"] = str(target_md)
            log.info("Markdown de section généré : %s", target_md.name)

            generated_records.append({
                "name": sec_name,
                "context": sec.get("context"),
                "category": sec.get("category"),
                "type_marche": sec.get("type_marche"),
                "start_page": start_idx + 1,
                "end_page": end_idx + 1,
                "pdf_path": str(target_pdf),
                "md_path": str(target_md)
            })

    return generated_records

