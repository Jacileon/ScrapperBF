"""
runner.py — Traitement de tous les PDFs un par un via reader_core

Parcourt le répertoire telechargements_pdf/ (ou un dossier spécifié),
et exécute sur chaque PDF :
  1. Macro-Split (AVIS vs RÉSULTATS avec priorité sommaire page 2 + repli marqueurs)
  2. Niveau 2 : Génération physique des sous-PDFs de zones
  3. Niveau 3 : Micro-Split géométrique des AVIS en fichiers Markdown unitaires
Gère la reprise automatique : les bulletins déjà traités sont sautés.
"""

import os
import sys
import glob
import logging
import argparse
from pathlib import Path

# Assurer l'accès au package reader_core
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reader_core.pdf_reader_pipeline import process_single_pdf
from reader_core.zone_pdf_generator import extract_numero_and_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("scrapperbf.runner")


def run_all(source_dir: str = "telechargements_pdf", out_dir: str = "output_bulletins", limit: int = None):
    src = Path(source_dir)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(glob.glob(str(src / "*.pdf")))
    total = len(pdf_files)
    log.info("Lancement du traitement global : %d PDF(s) trouvés dans %s", total, src)

    if limit:
        pdf_files = pdf_files[:limit]
        log.info("Limite appliquée : %d PDF(s) seront traités", len(pdf_files))

    succes = 0
    ignores = 0
    erreurs = 0

    for idx, pdf_path in enumerate(pdf_files, start=1):
        numero, _ = extract_numero_and_date(pdf_path)
        bulletin_dir = dest / numero
        bilan_json = bulletin_dir / f"{numero}_bilan_decoupage.json"

        # Reprise intelligente
        if bilan_json.exists():
            log.info("[%d/%d] [DÉJÀ TRAITÉ] Bulletin %s -> ignoré", idx, total, numero)
            ignores += 1
            continue

        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log.info("[%d/%d] Traitement du bulletin : %s (%s)", idx, total, numero, Path(pdf_path).name)
        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        try:
            res = process_single_pdf(
                pdf_path=pdf_path,
                output_root=str(dest),
                split_categories_pdf=True
            )
            log.info("[%d/%d] [SUCCÈS] %s : %d sous-PDFs, %d avis exportés en .md",
                     idx, total, numero, len(res["sous_pdfs_generes"]), res["total_annonces_avis"])
            succes += 1
        except Exception as e:
            log.error("[%d/%d] [ERREUR] Échec sur %s : %s", idx, total, pdf_path, e, exc_info=True)
            erreurs += 1

    log.info("=========================================================")
    log.info("=== FIN DU TRAITEMENT : %d traités, %d ignorés (déjà faits), %d erreurs sur %d ===",
             succes, ignores, erreurs, total)
    log.info("=========================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exécuteur global du pipeline de lecture des PDFs DGCMEF")
    parser.add_argument("--src", default="telechargements_pdf", help="Dossier contenant les PDFs")
    parser.add_argument("--out", default="output_bulletins", help="Dossier de sortie des bulletins traités")
    parser.add_argument("--limit", type=int, default=None, help="Nombre maximal de PDFs à traiter")
    args = parser.parse_args()

    run_all(source_dir=args.src, out_dir=args.out, limit=args.limit)

