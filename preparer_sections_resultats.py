#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de préparation physique et logique des sections RÉSULTATS
pour tous les Quotidiens disponibles.

Opérations effectuées SANS AUCUN APPEL LLM :
1. Parcours de l'arborescence des Quotidiens.
2. Détection précise des bornes des sections RÉSULTATS (MIMOD et RÉGIONS) via le sommaire officiel.
3. Découpage physique instantané des pages de résultats avec pypdfium2 (C++ ultra-rapide)
   dans le dossier dédié : `sections_resultats_pretes/`.
4. Génération du manifeste maître d'extraction `manifeste_queue_resultats.json`.
5. Rapport de préparation détaillé.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pypdfium2 as pdfium
from split_resultats_sections import detecter_bornes_resultats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("prep_resultats")

OUTPUT_BASE_DIR = Path("sections_resultats_pretes")
MANIFEST_FILE = Path("manifeste_queue_resultats.json")


def trancher_pdf(doc: pdfium.PdfDocument, start_idx: int, end_idx: int, out_pdf: Path) -> bool:
    """Découpe un sous-document PDF avec pypdfium2."""
    try:
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        sub_doc = pdfium.PdfDocument.new()
        pages = list(range(start_idx, min(end_idx + 1, len(doc))))
        if not pages:
            return False
        sub_doc.import_pages(doc, pages)
        sub_doc.save(str(out_pdf))
        sub_doc.close()
        return True
    except Exception as e:
        logger.error(f"Erreur découpage {out_pdf.name}: {e}")
        return False


def preparer_quotidien(pdf_path: Path, output_subfolder: Path) -> Optional[Dict]:
    """Analyse et prépare les sous-PDFs de résultats d'un Quotidien."""
    try:
        bornes = detecter_bornes_resultats(str(pdf_path))
    except Exception as e:
        logger.warning(f"Erreur analyse sommaire sur {pdf_path.name}: {e}")
        return None

    numero = bornes.get("numero") or pdf_path.stem
    date_parution = bornes.get("date_parution")
    total_pages = bornes.get("total_pages", 0)

    mimod_range = bornes.get("mimod")
    reg_range = bornes.get("region")

    if not mimod_range and not reg_range:
        return None

    try:
        doc = pdfium.PdfDocument(str(pdf_path))
    except Exception as e:
        logger.error(f"Fichier corrompu {pdf_path.name}: {e}")
        return None

    sections_pretes = {}

    # 1. Section MIMOD
    if mimod_range:
        s, e = mimod_range
        out_name = f"{numero}_Resultats_MIMOD_p{s+1}_p{e+1}.pdf"
        out_pdf = output_subfolder / out_name
        if not out_pdf.exists() or out_pdf.stat().st_size == 0:
            trancher_pdf(doc, s, e, out_pdf)
        sections_pretes["mimod"] = {
            "pdf_path": str(out_pdf),
            "page_debut": s + 1,
            "page_fin": e + 1,
            "nb_pages": e - s + 1,
            "statut": "PRET"
        }

    # 2. Section RÉGION
    if reg_range:
        s, e = reg_range
        out_name = f"{numero}_Resultats_Region_p{s+1}_p{e+1}.pdf"
        out_pdf = output_subfolder / out_name
        if not out_pdf.exists() or out_pdf.stat().st_size == 0:
            trancher_pdf(doc, s, e, out_pdf)
        sections_pretes["region"] = {
            "pdf_path": str(out_pdf),
            "page_debut": s + 1,
            "page_fin": e + 1,
            "nb_pages": e - s + 1,
            "statut": "PRET"
        }

    doc.close()

    return {
        "numero": numero,
        "bulletin_nom": f"Quotidien {numero.replace('N', 'N°')}",
        "date_parution": date_parution,
        "source_pdf": str(pdf_path),
        "total_pages_quotidien": total_pages,
        "sections": sections_pretes,
        "pret_pour_extraction": True
    }


def executer_preparation(dossier_source: Path, annee_cible: Optional[str] = "2026") -> List[Dict]:
    """Parcourt et prépare tous les quotidiens de l'année cible."""
    logger.info(f"Recherche des Quotidiens complets dans {dossier_source}...")
    
    # Récupérer tous les PDF de Quotidiens
    all_pdfs = list(dossier_source.rglob("*.pdf"))
    candidats = []
    for p in all_pdfs:
        if "Quotidien" in p.name and "sections_pdf" not in str(p) and "Resultats" not in p.name:
            if annee_cible and annee_cible not in str(p):
                continue
            candidats.append(p)

    candidats.sort()
    logger.info(f"{len(candidats)} Quotidiens trouvés pour l'année {annee_cible or 'toutes'}.")

    t0 = time.time()
    manifeste = []
    nb_mimod = 0
    nb_reg = 0
    pages_totales_resultats = 0

    for i, pdf_p in enumerate(candidats, 1):
        # Déterminer le sous-dossier de sortie (ex: sections_resultats_pretes/2026/10/)
        parts = pdf_p.parts
        # Trouver l'année et le mois
        subfolder = OUTPUT_BASE_DIR
        for j, part in enumerate(parts):
            if part == "2026" and j + 1 < len(parts):
                subfolder = OUTPUT_BASE_DIR / part / parts[j+1]
                break

        res = preparer_quotidien(pdf_p, subfolder)
        if res:
            manifeste.append(res)
            if "mimod" in res["sections"]:
                nb_mimod += 1
                pages_totales_resultats += res["sections"]["mimod"]["nb_pages"]
            if "region" in res["sections"]:
                nb_reg += 1
                pages_totales_resultats += res["sections"]["region"]["nb_pages"]

        if i % 25 == 0 or i == len(candidats):
            logger.info(f"Progression : {i}/{len(candidats)} Quotidiens traités ({len(manifeste)} préparés)...")

    duree = time.time() - t0
    logger.info(f"\nPréparation terminée en {duree:.1f} secondes !")
    logger.info(f"Quotidiens préparés  : {len(manifeste)} / {len(candidats)}")
    logger.info(f"Sections MIMOD prêtes: {nb_mimod}")
    logger.info(f"Sections REGION prêtes: {nb_reg}")
    logger.info(f"Total pages de résultats découpées: {pages_totales_resultats}")

    # Enregistrement du manifeste JSON
    MANIFEST_FILE.write_text(json.dumps(manifeste, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Manifeste maître enregistré dans : {MANIFEST_FILE.resolve()}")

    return manifeste


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Préparation physique et manifeste des sections résultats.")
    parser.add_argument("--dir", default="telechargements_pdf_classes/2026", help="Dossier contenant les Quotidiens")
    parser.add_argument("--annee", default="2026", help="Année à préparer (défaut: 2026)")
    args = parser.parse_args()

    executer_preparation(Path(args.dir), annee_cible=args.annee)
