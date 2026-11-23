"""
prod_pipeline/daily_orchestrator.py — Orchestrateur journalier de production.

Structure créée par bulletin :
  telechargements_pdf_classes/YYYY/MM/Jour_YYYY-MM-DD_NXXXX/
    ├── source/
    │   └── Quotidien N°XXXX.pdf (copie intègre du PDF original)
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
    │   └── (fichiers .md correspondants à chaque section PDF avec tables Markdown)
    ├── 03_annonces_unitaires_md/
    │   ├── avis/
    │   │   └── (1 fichier .md par annonce individuelle avec frontmatter YAML)
    │   └── resultats/
    │       └── (1 fichier .md par unité-émetteur / lot avec tables Markdown et YAML)
    └── rapport_traitement.json
"""

import os
import re
import sys
import json
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdfplumber

from prod_pipeline.macro_splitter import execute_macro_split
from prod_pipeline.sections_generator import generate_sections
from prod_pipeline.avis_micro_splitter import segment_avis_annonces

log = logging.getLogger("scrapperbf.daily_orchestrator")

MOIS_FR = {
    'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12, 'décembre': 12
}


def _clean_slug(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    name = re.sub(r'\s+', '_', name)
    return name


def extract_bulletin_metadata(pdf_path: str) -> Dict[str, Any]:
    """Extrait le numéro officiel et la date de parution précise du bulletin."""
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
            txt_p1 = pdf.pages[0].extract_text() or ""
            # Chercher numéro officiel en première page
            m_txt_num = re.search(r'N[°o]\s*(\d{3,4}(?:[-_]\d{3,4})?(?:\s*bis)?)', txt_p1[:350], re.IGNORECASE)
            if m_txt_num:
                numero_default = f"N°{m_txt_num.group(1)}"

            # Chercher la date sur la ligne du numéro
            lines = txt_p1.splitlines()[:25]
            for line in lines:
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
                m = date_pattern.search(txt_p1[:600])
                if m:
                    date_str = m.group(0).strip()
                    j = int(m.group(1))
                    m_nom = m.group(2).lower()
                    a = int(m.group(3))
                    m_int = MOIS_FR.get(m_nom)
                    if m_int:
                        date_obj = datetime(a, m_int, j).date()
    except Exception as e:
        log.warning("Impossible d'extraire la date de une pour %s : %s", pdf_path, e)

    return {
        "numero": numero_default,
        "date_str": date_str,
        "date_obj": date_obj
    }


def process_single_bulletin(
    pdf_path: str,
    base_output_dir: str = "telechargements_pdf_classes",
    force: bool = False
) -> Dict[str, Any]:
    """
    Traite un unique bulletin PDF et génère l'arborescence chronologique complète.
    """
    t0 = time.time()
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Fichier introuvable : {pdf_path}")

    # 1. Métadonnées
    meta = extract_bulletin_metadata(str(pdf_file))
    numero = meta["numero"]
    d_obj = meta["date_obj"] or datetime.fromtimestamp(pdf_file.stat().st_mtime).date()
    date_str = meta["date_str"] or d_obj.strftime("%d/%m/%Y")

    # 2. Arborescence du jour (Année / Mois / Semaine / Jour)
    year_str = f"{d_obj.year:04d}"
    month_str = f"{d_obj.month:02d}"
    week_str = f"Semaine_{d_obj.isocalendar()[1]:02d}"
    day_folder = f"Jour_{d_obj.strftime('%Y-%m-%d')}_{_clean_slug(numero)}"

    target_root = Path(base_output_dir) / year_str / month_str / week_str / day_folder
    dir_source = target_root / "source"
    dir_sections_pdf = target_root / "01_sections_pdf"
    dir_sections_md = target_root / "02_sections_md"
    dir_annonces_avis = target_root / "03_avis"

    for d in (dir_source, dir_sections_pdf, dir_sections_md, dir_annonces_avis):
        d.mkdir(parents=True, exist_ok=True)
        if force:
            for old_f in d.glob("*.*"):
                try:
                    old_f.unlink()
                except Exception:
                    pass

    # Nettoyage de l'ancien dossier 03_annonces_unitaires_md s'il existe
    old_unitaires_dir = target_root / "03_annonces_unitaires_md"
    if old_unitaires_dir.exists():
        shutil.rmtree(old_unitaires_dir, ignore_errors=True)

    # 3. Copie du PDF source
    dest_pdf = dir_source / pdf_file.name
    if not dest_pdf.exists() or force:
        shutil.copy2(pdf_file, dest_pdf)

    log.info("===> Début de traitement : %s (%s) -> %s", numero, date_str, target_root)

    # 4. Macro-Split (Sommaire p.2 + repli visuel)
    # Découpe et conserve les sections RÉSULTATS (MIMOD, Régions) et AVIS
    sections, macro_meta = execute_macro_split(str(pdf_file), numero)
    log.info("Macro-Split : %d sections trouvées (Stratégie : %s)", len(sections), macro_meta["strategy"])

    # 5. Découpage physique des sous-PDFs et conversion Markdown (Sections globales RÉSULTATS & AVIS)
    sections_gen = generate_sections(
        pdf_path=str(pdf_file),
        sections=sections,
        output_pdf_dir=str(dir_sections_pdf),
        output_md_dir=str(dir_sections_md),
        bulletin_info={"numero": numero, "date_str": date_str}
    )

    # 6. Micro-Split AVIS (Uniquement la zone AVIS découpée annonce par annonce)
    avis_annonces = []
    if macro_meta["avis_range"]:
        avis_annonces = segment_avis_annonces(
            pdf_path=str(pdf_file),
            avis_range=macro_meta["avis_range"],
            output_md_dir=str(dir_annonces_avis),
            bulletin_info={"numero": numero, "date_str": date_str}
        )
        log.info("Micro-Split AVIS : %d annonces créées", len(avis_annonces))

    elapsed = round(time.time() - t0, 2)

    # 7. Rapport de synthèse du jour
    rapport = {
        "bulletin": {
            "numero": numero,
            "date_parution": d_obj.strftime("%Y-%m-%d"),
            "date_str": date_str,
            "fichier_source": pdf_file.name,
            "total_pages": macro_meta["total_pages"],
            "taille_octets": pdf_file.stat().st_size
        },
        "arborescence": {
            "repertoire_racine": str(target_root),
            "repertoire_source": str(dir_source),
            "repertoire_sections_pdf": str(dir_sections_pdf),
            "repertoire_sections_md": str(dir_sections_md),
            "repertoire_annonces_avis": str(dir_annonces_avis)
        },
        "macro_split": {
            "strategie": macro_meta["strategy"],
            "bornes_resultats": macro_meta["resultats_range"],
            "bornes_avis": macro_meta["avis_range"],
            "sections_generees": [s["name"] for s in sections_gen]
        },
        "statistiques": {
            "nombre_sections_pdf": len(sections_gen),
            "nombre_sections_md": len(sections_gen),
            "nombre_annonces_avis_md": len(avis_annonces),
            "temps_execution_secondes": elapsed
        },
        "statut": "SUCCES"
    }

    rapport_path = target_root / "rapport_traitement.json"
    rapport_path.write_text(json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Rapport de traitement enregistré : %s (%s s)", rapport_path.name, elapsed)

    return rapport
