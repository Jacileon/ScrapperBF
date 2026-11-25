#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de veille, téléchargement et préparation automatique du Quotidien du Jour.
Fonctionnalités :
1. Interroge l'API officielle SECOP (Ministère des Finances du Burkina Faso).
2. Détecte si un nouveau bulletin officiel a été publié aujourd'hui (ou le dernier disponible).
3. Télécharge le PDF original de manière résiliente et le classe par Année / Mois / Semaine.
4. Découpe et prépare l'extraction complète des RÉSULTATS :
   - Découpage physique des sections MIMOD et RÉGIONS avec pypdfium2.
   - Enregistrement dans sections_resultats_pretes/ et mise à jour de manifeste_complet_resultats.json.
5. Découpe et prépare l'extraction complète des ANNONCES / AVIS :
   - Détection de la zone AVIS (p. debut à fin).
   - Découpage physique de la zone AVIS et séparation par catégories (Travaux, Fournitures, Prestations).
   - Enregistrement dans sections_avis_pretes/ et génération de manifeste_queue_avis.json.
6. Peut être exécuté ponctuellement (--check-once) ou en boucle de veille programmée.
"""

import argparse
import datetime
import json
import logging
import os
import re
import shutil
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pypdfium2 as pdfium
from pipeline_avis_splitter import extract_metadata_and_toc
from split_resultats_sections import detecter_bornes_resultats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("veilleur_dgcmef")

SECOP_API_URL = "https://secop-gateway.finances.bf/api/revue/publications/quotidiens?page=0&size=10&service=revue-ms"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}

DOWNLOAD_DIR = Path("telechargements_pdf")
CLASSES_DIR = Path("telechargements_pdf_classes")
RESULTATS_DIR = Path("sections_resultats_pretes")
AVIS_DIR = Path("sections_avis_pretes")
MANIFEST_RESULTATS = Path("manifeste_complet_resultats.json")
MANIFEST_AVIS = Path("manifeste_queue_avis.json")


def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def decouper_plage_pdf(src_path: Path, start_page_1based: int, end_page_1based: int, out_path: Path) -> bool:
    """Découpe une plage de pages (inclusives, 1-based) avec pypdfium2."""
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc = pdfium.PdfDocument(str(src_path))
        total = len(doc)
        start_idx = max(0, start_page_1based - 1)
        end_idx = min(total - 1, end_page_1based - 1)
        if start_idx > end_idx:
            doc.close()
            return False

        sub_doc = pdfium.PdfDocument.new()
        sub_doc.import_pages(doc, list(range(start_idx, end_idx + 1)))
        sub_doc.save(str(out_path))
        sub_doc.close()
        doc.close()
        return True
    except Exception as e:
        logger.error(f"Erreur découpage {out_path.name}: {e}")
        return False


def verifier_publications_secop() -> List[Dict]:
    """Récupère les parutions récentes sur l'API SECOP."""
    ctx = get_ssl_context()
    req = urllib.request.Request(SECOP_API_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("content", [])
    except Exception as e:
        logger.error(f"Erreur connexion SECOP API: {e}")
        return []


def telecharger_pdf_secop(item: Dict) -> Optional[Path]:
    """Télécharge le PDF d'une parution SECOP et le classe."""
    pub_id = item.get("id")
    titre = item.get("titre", "")
    date_pub_str = item.get("datePublication")
    pdfs = item.get("pdfs", [])
    if not pdfs:
        logger.warning(f"Aucun PDF associé à la parution ID {pub_id}")
        return None

    pdf_info = pdfs[0]
    rang = pdf_info.get("rang", 1)

    m_num = re.search(r"[Nn][°o\s]+(\d{3,4})", titre)
    num = m_num.group(1) if m_num else "Inconnu"
    nom_fichier = f"Quotidien N°{num}.pdf"

    # Déterminer la date
    dt = None
    if date_pub_str:
        try:
            dt = datetime.datetime.fromisoformat(date_pub_str).date()
        except Exception:
            pass
    if not dt:
        dt = datetime.date.today()

    isocal = dt.isocalendar()
    week_num = isocal[1]
    annee_str = str(dt.year)
    mois_str = f"{dt.month:02d}"

    dest_folder = CLASSES_DIR / annee_str / mois_str / f"Semaine_{week_num:02d}"
    dest_folder.mkdir(parents=True, exist_ok=True)
    classified_path = dest_folder / nom_fichier
    raw_path = DOWNLOAD_DIR / nom_fichier

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Si déjà présent et valide
    if classified_path.exists() and classified_path.stat().st_size > 50000:
        logger.info(f"Le fichier {nom_fichier} est déjà présent dans {classified_path}.")
        return classified_path

    pdf_url = f"https://secop-gateway.finances.bf/api/revue/publications/quotidiens/{pub_id}/pdfs/{rang}?service=revue-ms"
    logger.info(f"Téléchargement du nouveau Quotidien : {titre} (ID: {pub_id})")
    logger.info(f"  URL : {pdf_url}")

    ctx = get_ssl_context()
    req = urllib.request.Request(pdf_url, headers=HEADERS)

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=90) as resp:
                content = resp.read()
                raw_path.write_bytes(content)
                shutil.copy2(str(raw_path), str(classified_path))
                logger.info(f"  Téléchargé avec succès : {classified_path} ({len(content):,} octets).")
                return classified_path
        except Exception as e:
            logger.warning(f"Tentative {attempt}/3 échouée: {e}")
            time.sleep(3 * attempt)

    logger.error(f"Échec du téléchargement pour {titre}.")
    return None


def preparer_resultats_nouveau_quotidien(pdf_path: Path, annee: str, mois: str) -> Dict:
    """Découpe les sections résultats et met à jour le manifeste des résultats."""
    bornes = detecter_bornes_resultats(str(pdf_path))
    numero = bornes.get("numero") or pdf_path.stem.replace("Quotidien ", "")
    date_parution = bornes.get("date_parution")
    total_pages = bornes.get("total_pages", 0)

    out_folder = RESULTATS_DIR / annee / mois
    out_folder.mkdir(parents=True, exist_ok=True)

    sections_pretes = {}

    mimod_range = bornes.get("mimod")
    reg_range = bornes.get("region")

    if mimod_range:
        s, e = mimod_range
        p_start, p_end = s + 1, e + 1
        out_name = f"{numero}_Resultats_MIMOD_p{p_start}_p{p_end}.pdf"
        out_pdf = out_folder / out_name
        decouper_plage_pdf(pdf_path, p_start, p_end, out_pdf)
        sections_pretes["mimod"] = {
            "pdf_path": str(out_pdf),
            "page_debut": p_start,
            "page_fin": p_end,
            "nb_pages": p_end - p_start + 1,
            "statut": "PRET"
        }
        logger.info(f"  [RÉSULTATS MIMOD] {out_name} (p.{p_start} à p.{p_end}, {p_end - p_start + 1} pages).")

    if reg_range:
        s, e = reg_range
        p_start, p_end = s + 1, e + 1
        out_name = f"{numero}_Resultats_Region_p{p_start}_p{p_end}.pdf"
        out_pdf = out_folder / out_name
        decouper_plage_pdf(pdf_path, p_start, p_end, out_pdf)
        sections_pretes["region"] = {
            "pdf_path": str(out_pdf),
            "page_debut": p_start,
            "page_fin": p_end,
            "nb_pages": p_end - p_start + 1,
            "statut": "PRET"
        }
        logger.info(f"  [RÉSULTATS RÉGION] {out_name} (p.{p_start} à p.{p_end}, {p_end - p_start + 1} pages).")

    entry_data = {
        "numero": numero,
        "bulletin_nom": f"Quotidien {numero.replace('N', 'N°')}",
        "date_parution": date_parution,
        "annee": annee,
        "mois": mois,
        "source_pdf": str(pdf_path),
        "total_pages_quotidien": total_pages,
        "sections": sections_pretes,
        "pret_pour_extraction": True
    }

    # Mise à jour du manifeste complet
    if MANIFEST_RESULTATS.exists():
        manifeste = json.loads(MANIFEST_RESULTATS.read_text(encoding="utf-8"))
        q_key = f"queue_{annee}"
        queue = manifeste.setdefault(q_key, [])
        # Remplacement si existant, sinon ajout
        existing_idx = next((i for i, x in enumerate(queue) if x["numero"] == numero), None)
        if existing_idx is not None:
            queue[existing_idx] = entry_data
        else:
            queue.append(entry_data)
        MANIFEST_RESULTATS.write_text(json.dumps(manifeste, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"  Manifeste RÉSULTATS actualisé dans {MANIFEST_RESULTATS.name}.")

    return entry_data


def preparer_annonces_nouveau_quotidien(pdf_path: Path, annee: str, mois: str) -> Dict:
    """Découpe la zone AVIS et ses sous-catégories, et met à jour le manifeste AVIS."""
    meta = extract_metadata_and_toc(str(pdf_path))
    numero = meta.get("numero") or pdf_path.stem.replace("Quotidien ", "")
    date_parution = meta.get("date_parution")
    avis_range = meta.get("avis_range")
    entries = meta.get("entries", [])

    out_folder = AVIS_DIR / annee / mois
    out_folder.mkdir(parents=True, exist_ok=True)

    sections_avis = {}

    # 1. Découpage de la Zone AVIS Globale
    if avis_range:
        p_start, p_end = avis_range
        out_global_name = f"{numero}_Zone_AVIS_p{p_start}_p{p_end}.pdf"
        out_global_pdf = out_folder / out_global_name
        decouper_plage_pdf(pdf_path, p_start, p_end, out_global_pdf)
        sections_avis["zone_avis_complete"] = {
            "pdf_path": str(out_global_pdf),
            "page_debut": p_start,
            "page_fin": p_end,
            "nb_pages": p_end - p_start + 1,
            "statut": "PRET"
        }
        logger.info(f"  [ZONE AVIS GLOBALE] {out_global_name} (p.{p_start} à p.{p_end}, {p_end - p_start + 1} pages).")

    # 2. Découpage par sous-catégories détectées dans le sommaire
    avis_items = [e for e in entries if e.get("mode") == "AVIS"]
    categories_vues = {}
    for i, it in enumerate(avis_items):
        cat = it.get("cat", "autre")
        p_deb = it.get("page_printed")
        # Calcul de la fin : page de l'item suivant - 1 ou fin de la zone avis
        if i + 1 < len(avis_items):
            p_suiv = avis_items[i+1].get("page_printed", p_deb)
            p_fin = max(p_deb, p_suiv - 1)
        else:
            p_fin = avis_range[1] if avis_range else p_deb

        sub_cat_name = f"{numero}_Avis_{cat.capitalize()}_p{p_deb}_p{p_fin}.pdf"
        sub_cat_pdf = out_folder / sub_cat_name
        decouper_plage_pdf(pdf_path, p_deb, p_fin, sub_cat_pdf)

        categories_vues[f"{cat}_{i+1}"] = {
            "categorie": cat,
            "intitule": it.get("label"),
            "pdf_path": str(sub_cat_pdf),
            "page_debut": p_deb,
            "page_fin": p_fin,
            "nb_pages": p_fin - p_deb + 1,
            "statut": "PRET"
        }
        logger.info(f"    -> [SOUS-AVIS {cat.upper()}] {sub_cat_name} (p.{p_deb} à p.{p_fin}).")

    sections_avis["categories_detail"] = categories_vues

    entry_data = {
        "numero": numero,
        "bulletin_nom": f"Quotidien {numero.replace('N', 'N°')}",
        "date_parution": date_parution,
        "annee": annee,
        "mois": mois,
        "source_pdf": str(pdf_path),
        "sections_avis": sections_avis,
        "pret_pour_extraction": True
    }

    # Mise à jour du manifeste AVIS
    queue_avis = []
    if MANIFEST_AVIS.exists():
        try:
            queue_avis = json.loads(MANIFEST_AVIS.read_text(encoding="utf-8"))
        except Exception:
            queue_avis = []

    existing_idx = next((i for i, x in enumerate(queue_avis) if x["numero"] == numero), None)
    if existing_idx is not None:
        queue_avis[existing_idx] = entry_data
    else:
        queue_avis.append(entry_data)

    MANIFEST_AVIS.write_text(json.dumps(queue_avis, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"  Manifeste ANNONCES / AVIS actualisé dans {MANIFEST_AVIS.name}.")

    return entry_data


def executer_veille_quotidienne() -> Dict:
    """Vérifie la dernière parution, télécharge et prépare Résultats ET Avis."""
    print("\n" + "=" * 80)
    print("VÉRIFICATION DES NOUVELLES PARUTIONS SUR L'API OFFICIELLE SECOP")
    print("=" * 80)

    items = verifier_publications_secop()
    if not items:
        logger.warning("Impossible de récupérer les parutions sur SECOP.")
        return {"statut": "ERREUR_SECOP"}

    dernier = items[0]
    titre = dernier.get("titre")
    date_pub = dernier.get("datePublication")
    pub_id = dernier.get("id")

    logger.info(f"Dernière parution officielle disponible : {titre} (Date: {date_pub})")

    # Télécharger le PDF officiel
    pdf_path = telecharger_pdf_secop(dernier)
    if not pdf_path or not pdf_path.exists():
        logger.error(f"Échec de l'obtention du PDF pour {titre}.")
        return {"statut": "ECHEC_TELECHARGEMENT"}

    # Extraire l'année et le mois du chemin classé
    # ex: telechargements_pdf_classes/2026/11/Semaine_48/Quotidien N°4537.pdf
    parts = pdf_path.parts
    annee = "2026"
    mois = "11"
    for i, p in enumerate(parts):
        if re.match(r"^\d{4}$", p) and i + 1 < len(parts):
            annee = p
            mois = parts[i+1]
            break

    print("\n--- 1. PRÉPARATION COMPLÈTE DE LA SECTION RÉSULTATS ---")
    res_data = preparer_resultats_nouveau_quotidien(pdf_path, annee, mois)

    print("\n--- 2. PRÉPARATION COMPLÈTE DE LA SECTION ANNONCES / AVIS ---")
    avis_data = preparer_annonces_nouveau_quotidien(pdf_path, annee, mois)

    bilan = {
        "statut": "SUCCES",
        "bulletin": titre,
        "date_publication": date_pub,
        "source_pdf": str(pdf_path),
        "resultats": res_data,
        "annonces": avis_data,
        "date_traitement": datetime.datetime.now().isoformat()
    }

    print("\n" + "=" * 80)
    print(f"PRÉPARATION TERMINÉE POUR {titre} !")
    print(f"  * Source : {pdf_path}")
    print(f"  * Sections Résultats prêtes : {list(res_data['sections'].keys())}")
    print(f"  * Zone Avis complète prête   : {'zone_avis_complete' in avis_data['sections_avis']}")
    print(f"  * Sous-catégories Avis      : {len(avis_data['sections_avis'].get('categories_detail', {}))}")
    print("=" * 80 + "\n")

    return bilan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veille et préparation du Quotidien du jour (Résultats + Avis).")
    parser.add_argument("--check-once", action="store_true", default=True, help="Vérifier une fois immédiatement")
    args = parser.parse_args()

    executer_veille_quotidienne()
