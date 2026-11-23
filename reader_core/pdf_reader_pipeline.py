"""
reader_core/pdf_reader_pipeline.py — Point d'entrée pour traiter un PDF un à un

Orchestre les 3 niveaux de split :
  1. Macro-Split (Séparation AVIS vs RÉSULTATS avec Stratégie A sommaire & B marqueurs)
  2. Niveau 2 : Génération physique des sous-PDFs de zones
  3. Micro-Split AVIS : Découpage déterministe par annonce individuelle en .md

Usage CLI :
  python -m reader_core.pdf_reader_pipeline path/to/quotidien.pdf
  python reader_core/pdf_reader_pipeline.py path/to/quotidien.pdf --out-dir output_reader
"""

import sys
import json
import logging
import argparse
from pathlib import Path

# Permet l'exécution directe en script ou en package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reader_core.macro_splitter import split_sections
from reader_core.zone_pdf_generator import generate_zone_pdfs, extract_numero_and_date
from reader_core.avis_micro_splitter import segment_avis_annonces


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scrapperbf.reader_pipeline")


def process_single_pdf(
    pdf_path: str,
    output_root: str = "output_reader",
    split_categories_pdf: bool = True
) -> dict:
    """
    Traite un PDF unique de bout en bout :
      - Macro-split
      - Extraction sous-PDFs
      - Micro-split en Markdown unitaire
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Le fichier PDF {pdf_path} n'existe pas.")

    numero, date_parution = extract_numero_and_date(str(pdf_file))
    log.info("=== TRAITEMENT DU BULLETIN %s (%s) ===", numero, date_parution or "Date inconnue")

    # Dossier de sortie dédié pour ce bulletin
    bulletin_dir = Path(output_root) / f"{numero}"
    zones_pdf_dir = bulletin_dir / "zones_pdf"
    annonces_md_dir = bulletin_dir / "annonces_avis_md"

    # 1. Macro-Split
    log.info("[Étape 1] Lancement du Macro-Split...")
    zones = split_sections(str(pdf_file))
    log.info("Zones détectées : AVIS=%s, RÉSULTATS=%s (Méthode : %s)",
             zones.get("AVIS"), zones.get("RESULTATS"), zones.get("methode"))

    # 2. Génération physique des sous-PDFs
    log.info("[Étape 2] Génération physique des sous-PDFs de zones...")
    created_pdfs = generate_zone_pdfs(
        pdf_path=str(pdf_file),
        zones=zones,
        output_dir=str(zones_pdf_dir),
        split_categories=split_categories_pdf
    )

    # 3. Micro-Split des AVIS
    annonces_avis = []
    avis_zone = zones.get("AVIS")
    if avis_zone:
        log.info("[Étape 3] Découpage géométrique des annonces de la zone AVIS...")
        annonces_avis = segment_avis_annonces(
            pdf_path=str(pdf_file),
            avis_range=avis_zone,
            output_md_dir=str(annonces_md_dir),
            numero_bulletin=numero,
            date_parution=date_parution
        )
        log.info("Total annonces exportées en Markdown : %d", len(annonces_avis))
    else:
        log.warning("Aucune zone AVIS identifiée dans ce bulletin.")

    # Synthèse récapitulative
    summary = {
        "source_pdf": str(pdf_file.name),
        "numero": numero,
        "date_parution": date_parution,
        "pages_totales": zones.get("n_pages"),
        "macro_split": {
            "methode": zones.get("methode"),
            "avis_range": zones.get("AVIS"),
            "resultats_range": zones.get("RESULTATS"),
        },
        "sous_pdfs_generes": {k: str(v) for k, v in created_pdfs.items()},
        "total_annonces_avis": len(annonces_avis),
        "annonces_avis": annonces_avis,
        "dossier_sortie": str(bulletin_dir),
    }

    # Sauvegarder le bilan JSON
    summary_path = bulletin_dir / f"{numero}_bilan_decoupage.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Bilan complet sauvegardé : %s", summary_path)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline unitaire de lecture et découpage de PDF DGCMEF")
    parser.add_argument("pdf_path", help="Chemin du fichier PDF à traiter")
    parser.add_argument("--out-dir", default="output_reader", help="Dossier racine de sortie")
    parser.add_argument("--no-sub-categories", action="store_true",
                        help="Désactive la séparation d'avis en sous-PDFs par famille")
    args = parser.parse_args()

    res = process_single_pdf(
        pdf_path=args.pdf_path,
        output_root=args.out_dir,
        split_categories_pdf=(not args.no_sub_categories)
    )
    print("\n=== RAPPORT D'EXÉCUTION ===")
    print(f"Bulletin : {res['numero']}")
    print(f"Méthode Macro-Split : {res['macro_split']['methode']}")
    print(f"Sous-PDFs créés : {len(res['sous_pdfs_generes'])}")
    print(f"Annonces AVIS extraites en .md : {res['total_annonces_avis']}")
    print(f"Dossier résultat : {res['dossier_sortie']}")
