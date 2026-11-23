"""
reader_core/daily_structured_processor.py

Traite un PDF de bulletin complet en respectant l'arborescence :
  telechargements_pdf_classes/ANNEE/MOIS/Jour_YYYY-MM-DD_NXXXX/
    ├── source/
    ├── 01_sections_pdf/
    │   ├── N°XXXX-Avis-MIMOD-fournitures_et_services_courants.pdf
    │   ├── N°XXXX-Avis-MIMOD-travaux.pdf
    │   ├── N°XXXX-Avis-MIMOD-prestations_intellectuelles.pdf
    │   ├── N°XXXX-Avis-Region-fournitures_et_services_courants.pdf
    │   ├── N°XXXX-Avis-Region-travaux.pdf
    │   ├── N°XXXX-Avis-Region-prestations_intellectuelles.pdf
    │   ├── N°XXXX-Resultats-MIMOD.pdf
    │   └── N°XXXX-Resultats-Region.pdf
    ├── 02_sections_md/
    │   └── (fichiers .md correspondants à chaque section PDF)
    └── 03_annonces_unitaires_md/
        └── (fichiers unitaires .md par annonce via découpage géométrique)
"""

import os
import re
import sys
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

import pdfplumber
import pypdfium2 as pdfium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reader_core.macro_splitter import parse_sommaire
from reader_core.avis_micro_splitter import segment_avis_annonces

log = logging.getLogger("scrapperbf.daily_processor")

MOIS_FR = {
    'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12, 'décembre': 12
}


def clean_slug(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    name = re.sub(r'\s+', '_', name)
    return name


def extract_metadata(pdf_path: str) -> Dict[str, Any]:
    """Extrait le numéro officiel du bulletin et sa date complète."""
    stem = Path(pdf_path).stem
    m_num = re.search(r'[Nn][°o]?\s*(\d{3,4}(?:[-_]\d{3,4})?(?:\s*bis)?)', stem, re.IGNORECASE)
    numero_default = f"N°{m_num.group(1).replace('_', '-')}" if m_num else stem

    date_obj = None
    date_str = ""

    date_pattern = re.compile(
        r'(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*(\d{1,2})(?:er)?\s+([a-zéûë]+)\s+(\d{4})',
        re.IGNORECASE
    )

    try:
        with pdfplumber.open(pdf_path) as pdf:
            txt = pdf.pages[0].extract_text() or ""
            # Chercher numéro officiel
            m_txt_num = re.search(r'N[°o]\s*(\d{3,4}(?:[-_]\d{3,4})?(?:\s*bis)?)', txt[:300], re.IGNORECASE)
            if m_txt_num:
                numero_default = f"N°{m_txt_num.group(1)}"

            # Chercher la date
            for line in txt.splitlines()[:20]:
                if m_txt_num and m_txt_num.group(1) in line:
                    m = date_pattern.search(line)
                    if m:
                        date_str = m.group(0).strip()
                        j = int(m.group(1))
                        m_nom = m.group(2).lower()
                        a = int(m.group(3))
                        m_int = MOIS_FR.get(m_nom)
                        if m_int:
                            date_obj = datetime(a, m_int, j).date()
                        break
            if not date_obj:
                m = date_pattern.search(txt[:500])
                if m:
                    date_str = m.group(0).strip()
                    j = int(m.group(1))
                    m_nom = m.group(2).lower()
                    a = int(m.group(3))
                    m_int = MOIS_FR.get(m_nom)
                    if m_int:
                        date_obj = datetime(a, m_int, j).date()
    except Exception:
        pass

    return {
        "numero": numero_default,
        "date_str": date_str,
        "date_obj": date_obj
    }


def parse_toc_sections(pdf_path: str, numero: str) -> List[Dict[str, Any]]:
    """
    Parse la page 2 (sommaire) pour extraire toutes les sections selon la nomenclature :
    N°3827-Avis-MIMOD-fournitures_et_services_courants, N°3827-Resultats-MIMOD, etc.
    """
    sections = []
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) < 2:
            return []
        
        # Chercher la page de sommaire
        page_sommaire = None
        for p in (pdf.pages[1], pdf.pages[0]):
            txt = p.extract_text() or ""
            if "sommaire" in txt.lower():
                page_sommaire = p
                break
        
        if not page_sommaire:
            return []

        text = page_sommaire.extract_text() or ""
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        current_context = "UNKNOWN"
        current_categorie = "UNKNOWN"
        current_name_parts = []

        for line in lines:
            upper = line.upper()
            if "RESULTATS" in upper or "DÉPOUILLEMENTS" in upper or "DEPOUILLEMENTS" in upper:
                current_context = "Resultats"
            elif "AVIS" in upper:
                current_context = "Avis"

            if re.search(r'minist[èe]res|institutions|mimod|ma[îi]trises', line, re.I):
                current_categorie = "MIMOD"
            elif re.search(r'r[ée]gion|collectivit', line, re.I):
                current_categorie = "Region"

            match = re.search(r'(.*?)\.?\b(?<!B\.)P\.\s*(\d+)', line, re.I)
            if match:
                text_part = re.sub(r'\.+$', '', match.group(1)).strip()
                page_num = int(match.group(2))
                if text_part:
                    current_name_parts.append(text_part)
                full_name = " ".join(current_name_parts)

                type_marche = ""
                if re.search(r'fourniture', full_name, re.I):
                    type_marche = "fournitures_et_services_courants"
                elif re.search(r'travaux', full_name, re.I):
                    type_marche = "travaux"
                elif re.search(r'intellectuelle|consultant', full_name, re.I):
                    type_marche = "prestations_intellectuelles"

                num_clean = clean_slug(numero)
                if current_categorie != "UNKNOWN" and type_marche and current_context == "Avis":
                    final_name = f"{num_clean}-Avis-{current_categorie}-{type_marche}"
                elif current_categorie != "UNKNOWN" and current_context == "Resultats":
                    final_name = f"{num_clean}-Resultats-{current_categorie}"
                else:
                    clean_raw = clean_slug(re.sub(r"^[-•*:]\s*", "", full_name)[:40])
                    final_name = f"{num_clean}-{current_context}-{clean_raw}"

                sections.append({
                    "name": final_name,
                    "page_printed": page_num,
                    "context": current_context,
                    "category": current_categorie,
                    "type_marche": type_marche
                })
                current_name_parts = []
            else:
                clean_l = line.strip()
                if clean_l and not re.search(r'sommaire|bulletin|quotidien', clean_l, re.I):
                    current_name_parts.append(clean_l)

    return sections


def process_bulletin_daily(pdf_path: str, base_out_dir: str = "telechargements_pdf_classes"):
    meta = extract_metadata(pdf_path)
    numero = meta["numero"]
    d_obj = meta["date_obj"] or datetime.now().date()
    date_str = meta["date_str"]

    year_str = f"{d_obj.year:04d}"
    month_str = f"{d_obj.month:02d}"
    day_folder = f"Jour_{d_obj.strftime('%Y-%m-%d')}_{clean_slug(numero)}"

    target_root = Path(base_out_dir) / year_str / month_str / day_folder
    dir_source = target_root / "source"
    dir_sections_pdf = target_root / "01_sections_pdf"
    dir_sections_md = target_root / "02_sections_md"
    dir_annonces_md = target_root / "03_annonces_unitaires_md"

    for d in (dir_source, dir_sections_pdf, dir_sections_md, dir_annonces_md):
        d.mkdir(parents=True, exist_ok=True)

    # Copie du PDF source
    dest_pdf = dir_source / Path(pdf_path).name
    if not dest_pdf.exists():
        shutil.copy2(pdf_path, dest_pdf)

    log.info("Traitement du jour : %s -> %s", numero, target_root)

    # 1. Macro-Split & Découpage des sections PDF
    doc = pdfium.PdfDocument(str(pdf_path))
    total_pages = len(doc)
    sections = parse_toc_sections(pdf_path, numero)

    created_sections_pdf = []
    avis_min_page = None
    avis_max_page = None

    if sections:
        # Trier par page imprimée
        sections.sort(key=lambda s: s["page_printed"])
        
        # Calibration delta
        delta = -1
        for s in sections:
            s["start_idx"] = max(0, s["page_printed"] + delta)
        
        for i in range(len(sections)):
            if i < len(sections) - 1:
                sections[i]["end_idx"] = min(total_pages - 1, sections[i+1]["start_idx"] - 1)
            else:
                sections[i]["end_idx"] = total_pages - 1

        for s in sections:
            start = s["start_idx"]
            end = s["end_idx"]
            if start <= end:
                sub_doc = pdfium.PdfDocument.new()
                sub_doc.import_pages(doc, list(range(start, end + 1)))
                out_pdf_path = dir_sections_pdf / f"{s['name']}.pdf"
                sub_doc.save(str(out_pdf_path))
                sub_doc.close()
                created_sections_pdf.append((out_pdf_path, s))
                log.info("Créé sous-PDF de section : %s (Pages %d-%d)", out_pdf_path.name, start+1, end+1)

                if s["context"] == "Avis":
                    if avis_min_page is None or start < avis_min_page:
                        avis_min_page = start
                    if avis_max_page is None or end > avis_max_page:
                        avis_max_page = end

    doc.close()

    # 2. Conversion intégrale en Markdown de chaque section PDF
    with pdfplumber.open(pdf_path) as plumber_pdf:
        for sec_pdf_path, sec_info in created_sections_pdf:
            start = sec_info["start_idx"]
            end = sec_info["end_idx"]
            
            lines_md = [
                f"# Section : {sec_info['name']}",
                f"- **Bulletin :** {numero} ({date_str})",
                f"- **Pages d'origine :** {start+1} à {end+1}",
                f"- **Catégorie :** {sec_info.get('category')}",
                f"- **Type de marché :** {sec_info.get('type_marche')}",
                "\n---\n"
            ]

            for pi in range(start, end + 1):
                p_obj = plumber_pdf.pages[pi]
                text = p_obj.extract_text() or ""
                lines_md.append(f"## Page {pi+1}\n")
                lines_md.append(text)
                lines_md.append("\n")

            out_md_path = dir_sections_md / f"{sec_pdf_path.stem}.md"
            out_md_path.write_text("\n".join(lines_md), encoding="utf-8")
            log.info("Créé Markdown de section : %s", out_md_path.name)

    # 3. Micro-Split Géométrique unitaire des AVIS
    avis_range = (avis_min_page, avis_max_page) if (avis_min_page is not None and avis_max_page is not None) else None
    annonces = segment_avis_annonces(
        pdf_path=pdf_path,
        avis_range=avis_range,
        output_md_dir=str(dir_annonces_md),
        numero_bulletin=numero,
        date_parution=date_str
    )
    log.info("Total annonces unitaires générées en .md : %d", len(annonces))

    return {
        "numero": numero,
        "dossier": str(target_root),
        "sections_pdf": len(created_sections_pdf),
        "annonces_md": len(annonces)
    }

