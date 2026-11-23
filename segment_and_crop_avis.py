#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
segment_and_crop_avis.py
========================
Script orchestrateur autonome de Macro-Segmentation et Découpage strict (Micro-Split)
des annonces AVIS d'appels d'offres en Markdown (.md).

Fonctionnalités :
  1. Auto-détection des métadonnées du bulletin (Numéro, Date, Titre).
  2. Macro-Segmentation basée sur le sommaire officiel de la Page 2.
  3. Bornage strict de la section AVIS (exclut résultats, communiqués, etc.).
  4. Micro-Segmentation géométrique par triplet de bandeaux :
     - 🔴 ROUGE (Catégorie)
     - 🟡 JAUNE (Émetteur / Autorité)
     - 🔵 CYAN (Objet de l'appel d'offres)
  5. Découpage du contenu depuis la base du bandeau CYAN jusqu'au bandeau ROUGE suivant.
  6. Détection automatique du numéro de page officiel imprimé en bas à droite.
  7. Exportation ordonnée en fichiers .md individuels et index récapitulatif JSON/MD.

Usage :
  python segment_and_crop_avis.py --pdf "chemin/vers/Quotidien.pdf"
  python segment_and_crop_avis.py --dir "telechargements_pdf_classes/2026/11"
  python segment_and_crop_avis.py --all
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import pdfplumber
from prod_pipeline.macro_splitter import parse_sommaire_page2, calibrate_and_bound_sections
from prod_pipeline.avis_micro_splitter import segment_avis_annonces

def extraire_metadonnees_pdf(pdf_path: str):
    """Extrait le numéro officiel et la date imprimée sur la couverture du bulletin."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            txt = pdf.pages[0].extract_text() or ""
            m = re.search(r'N°\s*(\d+.*?)(?:–|-)\s*([A-Za-zÀ-ÿ]+\s+\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})', txt)
            if m:
                numero = f"Quotidien N°{m.group(1).strip()}"
                date_str = m.group(2).strip()
                return numero, date_str
    except Exception as e:
        print(f"  [Avertissement] Impossible de lire les métadonnées p.1 de {pdf_path}: {e}")

    # Repli sur le nom du fichier
    stem = Path(pdf_path).stem
    return stem, "Date inconnue"

def traiter_bulletin_pdf(pdf_path: str, base_output_dir: str = None) -> dict:
    """
    Exécute le pipeline complet pour un bulletin PDF unique :
    Macro-split -> Micro-split -> Génération des fichiers .md ordonnés.
    """
    pdf_p = Path(pdf_path).resolve()
    if not pdf_p.exists():
        print(f"[ERREUR] Fichier introuvable : {pdf_p}")
        return {"status": "error", "message": "Fichier introuvable"}

    numero, date_str = extraire_metadonnees_pdf(str(pdf_p))
    print(f"\n{'='*70}")
    print(f" Traitement : {numero} ({date_str})")
    print(f" Source     : {pdf_p.name}")
    print(f"{'='*70}")

    # Détermination du dossier de sortie ordonné
    if base_output_dir:
        out_dir = Path(base_output_dir) / pdf_p.stem
    else:
        out_dir = pdf_p.parent / "03_avis_decoupes" / pdf_p.stem

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Macro-Segmentation (Sommaire page 2)
    print("  [1/3] Analyse du sommaire officiel (Macro-Segmentation)...")
    sections_sommaire = parse_sommaire_page2(str(pdf_p), numero)
    
    with pdfplumber.open(str(pdf_p)) as pdf:
        total_pages = len(pdf.pages)
        sections = calibrate_and_bound_sections(sections_sommaire, total_pages)

    avis_sections = [s for s in sections if s.get('context') == 'Avis']
    if avis_sections:
        min_p = min(s['start_idx'] for s in avis_sections)
        max_p = max(s['end_idx'] for s in avis_sections)
        avis_range = (min_p, max_p)
        print(f"        -> Zone AVIS bornée : pages PDF {min_p + 1} à {max_p + 1} (imprimées p. {avis_sections[0]['page_printed_start']} à {avis_sections[-1].get('page_printed_start', '?')})")
    else:
        # Aucun Avis au sommaire : bulletin dédié aux Résultats ou Communiqués (ex: N° 4306 bis)
        print("        -> Aucune section AVIS présente au sommaire officiel. Pas d'annonces AVIS à découper.")
        index_file = out_dir / "_index_annonces.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump({
                "bulletin": numero,
                "date": date_str,
                "source_pdf": str(pdf_p),
                "nb_annonces": 0,
                "note": "Aucune section Avis au sommaire officiel",
                "annonces": []
            }, f, ensure_ascii=False, indent=2)
        return {
            "status": "success",
            "bulletin": numero,
            "date": date_str,
            "nb_annonces": 0,
            "output_dir": str(out_dir)
        }

    # 2. Micro-Segmentation géométrique (Triplet Rouge-Jaune-Cyan et détection des numéros de page)
    print("  [2/3] Découpage géométrique des annonces AVIS...")
    annonces = segment_avis_annonces(
        pdf_path=str(pdf_p),
        avis_range=avis_range,
        output_md_dir=str(out_dir),
        bulletin_info={"numero": numero, "date_str": date_str}
    )

    # 3. Récapitulatif et index ordonné
    print(f"  [3/3] Génération de l'index : {len(annonces)} annonce(s) découpée(s) en .md")
    index_file = out_dir / "_index_annonces.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump({
            "bulletin": numero,
            "date": date_str,
            "source_pdf": str(pdf_p),
            "nb_annonces": len(annonces),
            "annonces": annonces
        }, f, ensure_ascii=False, indent=2)

    for a in annonces:
        print(f"        - [{a['pages']:^10}] {a['id']} : {a['emetteur'][:45]}")

    print(f"  [OK] Annonces sauvegardées dans : {out_dir}")
    return {
        "status": "success",
        "bulletin": numero,
        "date": date_str,
        "nb_annonces": len(annonces),
        "output_dir": str(out_dir)
    }

def traiter_dossier(directory: str, skip_existing: bool = True):
    """Traite tous les fichiers PDF trouvés dans un dossier ou sous-dossiers de manière ordonnée."""
    dir_p = Path(directory)
    if not dir_p.exists():
        print(f"[ERREUR] Répertoire introuvable : {dir_p}")
        return

    # Exclusion des PDFs déjà découpés ou temporaires
    pdfs = sorted([
        p for p in dir_p.rglob("*.pdf") 
        if "crop" not in p.name.lower() and "scratch" not in str(p).lower()
    ])

    print(f"\nTraitement par lot de {len(pdfs)} bulletin(s) PDF dans : {dir_p}")
    bilan = []
    total_annonces = 0
    t0 = datetime.now()

    for i, p in enumerate(pdfs, 1):
        idx_file = p.parent / "03_avis_decoupes" / p.stem / "_index_annonces.json"
        if skip_existing and idx_file.exists():
            try:
                with open(idx_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    total_annonces += data.get("nb_annonces", 0)
                print(f"[{i}/{len(pdfs)}] Déjà traité (passé) : {p.name}")
                continue
            except Exception:
                pass

        print(f"\n>>> Progression : {i}/{len(pdfs)} <<<")
        try:
            res = traiter_bulletin_pdf(str(p))
            if res.get("status") == "success":
                total_annonces += res["nb_annonces"]
                bilan.append(res)
        except Exception as e:
            print(f"  [ERREUR sur {p.name}] : {e}")

    duree = (datetime.now() - t0).total_seconds()
    print(f"\n{'='*70}")
    print(f" SYNTHÈSE DU TRAITEMENT PAR LOT")
    print(f" Nouveaux bulletins traités   : {len(bilan)}")
    print(f" Total annonces AVIS découpées : {total_annonces} fichiers .md")
    print(f" Temps total                   : {round(duree, 2)} s")
    print(f"{'='*70}")

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline automatique de Macro-Segmentation et Découpage d'annonces AVIS (Quotidien des Marchés Publics)"
    )
    parser.add_argument("--pdf", type=str, help="Chemin d'un fichier PDF unique à traiter")
    parser.add_argument("--dir", type=str, help="Dossier contenant des PDFs à traiter par lot")
    parser.add_argument("--out", type=str, help="Répertoire de sortie personnalisé (optionnel)")
    parser.add_argument("--recents", action="store_true", help="Traiter tous les bulletins récents de novembre 2026")
    parser.add_argument("--all", action="store_true", help="Traiter absolument TOUS les bulletins PDF disponibles")
    parser.add_argument("--force", action="store_true", help="Recalculer même les bulletins déjà traités")

    args = parser.parse_args()

    if args.pdf:
        traiter_bulletin_pdf(args.pdf, base_output_dir=args.out)
    elif args.dir:
        traiter_dossier(args.dir, skip_existing=not args.force)
    elif args.all:
        traiter_dossier("telechargements_pdf_classes", skip_existing=not args.force)
    elif args.recents:
        traiter_dossier("telechargements_pdf_classes/2026/11", skip_existing=not args.force)
    else:
        # Par défaut, traite tout
        traiter_dossier("telechargements_pdf_classes", skip_existing=not args.force)

if __name__ == "__main__":
    main()
