#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de découpage spécialisé pour la section RÉSULTATS :
Sépare la section RÉSULTATS en :
  1. Résultats MIMOD (Ministères, Institutions et Maîtrises d'Ouvrages Déléguées)
  2. Résultats Régions (Collectivités territoriales / Régions)

Fonctionnalités :
  - Supporte l'analyse automatique d'un PDF de Quotidien complet ou d'un dossier de quotidiens.
  - Détecte avec précision les bornes de pages depuis le sommaire officiel (Page 2)
    et par fallback via l'analyse structurelle des barres d'émetteurs (pdfplumber).
  - Génère les sous-PDFs découpés pour chaque section.
  - Peut également convertir chaque sous-section en Markdown structuré (.md).
"""

import os
import sys
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pdfplumber
import pypdfium2 as pdfium

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scrapperbf.split_resultats")


def detecter_bornes_resultats(pdf_path: str) -> Dict[str, Optional[Tuple[int, int]]]:
    """
    Détecte les bornes (index_debut_0_based, index_fin_0_based inclus)
    pour 'RESULTATS_MIMOD' et 'RESULTATS_REGION'.
    """
    bornes = {
        "mimod": None,
        "region": None,
        "avis_debut": None,
        "numero": None,
        "date_parution": None,
        "total_pages": 0
    }

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        bornes["total_pages"] = total
        if total < 2:
            return bornes

        # 1. Extraction N° Quotidien et Date en priorité depuis le nom du fichier
        m_fname = re.search(r"(\d{3,4}(?:bis)?)", Path(pdf_path).stem, re.I)
        if m_fname:
            bornes["numero"] = "N" + m_fname.group(1)

        # Extraction de la Date depuis la page 1 ou 3
        for p_idx in [0, 2]:
            if p_idx >= total:
                continue
            txt = pdf.pages[p_idx].extract_text() or ""
            # On cherche spécifiquement la date associée au numéro du fichier
            m_date = re.search(
                r"N[°o]?\s*" + (m_fname.group(1) if m_fname else r"\d{3,4}") + r"\s*[•·-–]\s*([A-Za-zÀ-ÿ]+\s+\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})",
                txt,
                re.IGNORECASE,
            )
            if m_date:
                bornes["date_parution"] = re.sub(r"\s+", " ", m_date.group(1)).strip()
                break

        if not bornes["numero"]:
            bornes["numero"] = "N_INCONNU"

        # 2. Analyse Sommaire (Page 2 = index 1)
        p2_text = pdf.pages[1].extract_text() or ""
        
        # Regex pour les lignes du sommaire
        m_min = re.search(r"Minist[èe]res[^\n]*?P\.\s*(\d+)", p2_text, re.I)
        m_reg = re.search(r"R[ée]gions[^\n]*?P\.\s*(\d+)", p2_text, re.I)
        
        # Première page de AVIS
        idx_avis = p2_text.upper().find("AVIS")
        m_avis = re.search(r"P\.\s*(\d+)", p2_text[idx_avis:]) if idx_avis != -1 else None

        p_min = int(m_min.group(1)) if m_min else None
        p_reg = int(m_reg.group(1)) if m_reg else None
        p_avis = int(m_avis.group(1)) if m_avis else None

        bornes["avis_debut"] = p_avis

        # Calcul des plages (0-based), bornées strictement à [0, total - 1]
        if p_min:
            idx_min_start = min(total - 1, max(0, p_min - 1))
            if p_reg:
                idx_min_end = min(total - 1, max(idx_min_start, p_reg - 2))
            elif p_avis:
                idx_min_end = min(total - 1, max(idx_min_start, p_avis - 2))
            else:
                idx_min_end = total - 1
            bornes["mimod"] = (idx_min_start, idx_min_end)

        if p_reg:
            idx_reg_start = min(total - 1, max(0, p_reg - 1))
            if p_avis:
                idx_reg_end = min(total - 1, max(idx_reg_start, p_avis - 2))
            else:
                idx_reg_end = total - 1
            bornes["region"] = (idx_reg_start, idx_reg_end)

    return bornes


def extraire_texte_pages(pdf_path: str, start_idx: int, end_idx: int) -> str:
    """Extrait le texte complet entre deux indices de pages (inclus)."""
    lignes = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(start_idx, min(end_idx + 1, len(pdf.pages))):
            p = pdf.pages[i]
            lignes.append(f"\n--- Page {i + 1} ---\n")
            txt = p.extract_text() or ""
            lignes.append(txt)
    return "\n".join(lignes).strip()


def decouper_resultats_pdf(
    pdf_path: str,
    output_dir: Optional[str] = None,
    generer_md: bool = True
) -> Dict[str, Path]:
    """
    Découpe le Quotidien PDF pour séparer Résultats MIMOD et Résultats Régions.
    
    Retourne un dictionnaire des fichiers créés :
      {
        'pdf_mimod': Path(...),
        'pdf_region': Path(...),
        'md_mimod': Path(...),
        'md_region': Path(...)
      }
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Fichier introuvable : {pdf_path}")

    out_path = Path(output_dir) if output_dir else pdf_file.parent / f"{pdf_file.stem}_resultats_scindes"
    out_path.mkdir(parents=True, exist_ok=True)

    bornes = detecter_bornes_resultats(str(pdf_file))
    numero = bornes["numero"]
    log.info("Traitement de [%s] (%s pages) : MIMOD=%s | REGION=%s",
             numero, bornes["total_pages"], bornes["mimod"], bornes["region"])

    doc = pdfium.PdfDocument(str(pdf_file))
    resultats_crees = {}

    # 1. Traitement RÉSULTATS MIMOD
    if bornes["mimod"]:
        s, e = bornes["mimod"]
        pdf_out = out_path / f"{numero}_Resultats_MIMOD_p{s+1}_p{e+1}.pdf"
        sub_doc = pdfium.PdfDocument.new()
        sub_doc.import_pages(doc, list(range(s, e + 1)))
        sub_doc.save(str(pdf_out))
        sub_doc.close()
        resultats_crees["pdf_mimod"] = pdf_out
        log.info("-> Créé PDF MIMOD : %s (pages %d à %d)", pdf_out.name, s + 1, e + 1)

        if generer_md:
            md_out = out_path / f"{numero}_Resultats_MIMOD_p{s+1}_p{e+1}.md"
            texte = extraire_texte_pages(str(pdf_file), s, e)
            header = f"# {numero} — Résultats Provisoires : Ministères, Institutions et Maîtrises d'Ouvrages Déléguées (MIMOD)\n"
            if bornes["date_parution"]:
                header += f"**Date de parution** : {bornes['date_parution']}\n"
            header += f"**Pages du Quotidien** : {s + 1} à {e + 1}\n\n"
            md_out.write_text(header + texte, encoding="utf-8")
            resultats_crees["md_mimod"] = md_out
            log.info("-> Créé MD MIMOD  : %s", md_out.name)
    else:
        log.warning("[%s] Aucune section Résultats MIMOD détectée.", numero)

    # 2. Traitement RÉSULTATS RÉGIONS
    if bornes["region"]:
        s, e = bornes["region"]
        pdf_out = out_path / f"{numero}_Resultats_Region_p{s+1}_p{e+1}.pdf"
        sub_doc = pdfium.PdfDocument.new()
        sub_doc.import_pages(doc, list(range(s, e + 1)))
        sub_doc.save(str(pdf_out))
        sub_doc.close()
        resultats_crees["pdf_region"] = pdf_out
        log.info("-> Créé PDF REGION: %s (pages %d à %d)", pdf_out.name, s + 1, e + 1)

        if generer_md:
            md_out = out_path / f"{numero}_Resultats_Region_p{s+1}_p{e+1}.md"
            texte = extraire_texte_pages(str(pdf_file), s, e)
            header = f"# {numero} — Résultats Provisoires : Régions (Collectivités territoriales)\n"
            if bornes["date_parution"]:
                header += f"**Date de parution** : {bornes['date_parution']}\n"
            header += f"**Pages du Quotidien** : {s + 1} à {e + 1}\n\n"
            md_out.write_text(header + texte, encoding="utf-8")
            resultats_crees["md_region"] = md_out
            log.info("-> Créé MD REGION : %s", md_out.name)
    else:
        log.warning("[%s] Aucune section Résultats Régions détectée.", numero)

    doc.close()
    return resultats_crees


def main():
    parser = argparse.ArgumentParser(
        description="Scinde la section RÉSULTATS d'un Quotidien en Résultats MIMOD et Résultats Régions."
    )
    parser.add_argument("pdf", help="Chemin vers le fichier PDF du Quotidien complet")
    parser.add_argument("-o", "--output-dir", help="Dossier de destination (optionnel)", default=None)
    parser.add_argument("--no-md", action="store_true", help="Ne pas générer les fichiers Markdown texte")

    args = parser.parse_args()
    decouper_resultats_pdf(args.pdf, output_dir=args.output_dir, generer_md=not args.no_md)


if __name__ == "__main__":
    main()
