"""
prod_pipeline/cli.py — Interface en ligne de commande de production.

Exemples d'utilisation :
  python prod_pipeline/cli.py --file "telechargements_pdf/Quotidien n°4514.pdf"
  python prod_pipeline/cli.py --dir "telechargements_pdf" --limit 5
  python prod_pipeline/cli.py --dir "telechargements_pdf" --workers 4
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed

from prod_pipeline.daily_orchestrator import process_single_bulletin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("scrapperbf.cli")


def _worker_wrapper(args):
    pdf_path, out_dir, force = args
    try:
        res = process_single_bulletin(pdf_path, base_output_dir=out_dir, force=force)
        return True, pdf_path, res
    except Exception as e:
        log.error("Erreur sur %s : %s", pdf_path, e)
        return False, pdf_path, str(e)


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de Production DGCMEF — Traitement et structuration journalière des bulletins."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Chemin vers un fichier PDF unique à traiter.")
    group.add_argument("--dir", type=str, help="Dossier contenant les fichiers PDF à traiter en masse.")

    parser.add_argument("--out", type=str, default="telechargements_pdf_classes", help="Dossier de sortie racine.")
    parser.add_argument("--limit", type=int, default=0, help="Nombre maximal de fichiers à traiter (0 = illimité).")
    parser.add_argument("--workers", type=int, default=1, help="Nombre de workers parallèles (défaut 1).")
    parser.add_argument("--force", action="store_true", help="Forcer le re-traitement même si déjà traité.")

    args = parser.parse_args()

    if args.file:
        pdf_file = Path(args.file)
        if not pdf_file.exists():
            log.error("Fichier introuvable : %s", args.file)
            sys.exit(1)
        res = process_single_bulletin(str(pdf_file), base_output_dir=args.out, force=args.force)
        print("\n" + "=" * 60)
        print(f"BULLETIN {res['bulletin']['numero']} TRAITÉ AVEC SUCCÈS !")
        print(f"Dossier du jour : {res['arborescence']['repertoire_racine']}")
        print(f"Sections PDF créées : {res['statistiques']['nombre_sections_pdf']}")
        print(f"Sections MD créées : {res['statistiques']['nombre_sections_md']}")
        print(f"Annonces AVIS unitaires : {res['statistiques']['nombre_annonces_avis_md']}")
        print(f"Temps de traitement : {res['statistiques']['temps_execution_secondes']} secondes")
        print("=" * 60)
        return

    if args.dir:
        input_dir = Path(args.dir)
        if not input_dir.is_dir():
            log.error("Dossier introuvable : %s", args.dir)
            sys.exit(1)

        pdf_files = sorted(list(input_dir.glob("*.pdf")))
        if args.limit > 0:
            pdf_files = pdf_files[:args.limit]

        log.info("Traitement de %d fichiers PDF avec %d workers...", len(pdf_files), args.workers)

        tasks = [(str(p), args.out, args.force) for p in pdf_files]
        success_count = 0
        failure_count = 0

        if args.workers > 1:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(_worker_wrapper, t) for t in tasks]
                for fut in as_completed(futures):
                    ok, path_name, detail = fut.result()
                    if ok:
                        success_count += 1
                    else:
                        failure_count += 1
        else:
            for t in tasks:
                ok, path_name, detail = _worker_wrapper(t)
                if ok:
                    success_count += 1
                else:
                    failure_count += 1

        print("\n" + "=" * 60)
        print(f"BILAN TRAITEMENT DE MASSE :")
        print(f"Succès : {success_count} / {len(pdf_files)}")
        print(f"Échecs : {failure_count}")
        print("=" * 60)


if __name__ == "__main__":
    main()
