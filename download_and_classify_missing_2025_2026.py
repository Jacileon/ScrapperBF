#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_and_classify_missing_2025_2026.py
=========================================
Télécharge et classe par Année/Mois/Semaine tous les bulletins PDF
de Mai 2025 à aujourd'hui qui ne sont pas encore présents.
"""

import os
import re
import ssl
import time
from pathlib import Path
from urllib.parse import unquote, quote
from datetime import datetime, date
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber

DEST_ROOT = Path("telechargements_pdf_classes")
RAW_DIR = Path("telechargements_pdf")
URLS_FILE = Path("files/urls_valides_verifiees.txt")

MOIS_FR = {
    'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12, 'décembre': 12
}

def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    })
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

def extraire_date_du_pdf(pdf_path: Path, default_year: int, default_month: int) -> date:
    """Extrait la date exacte depuis la page 1 du PDF."""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            txt = pdf.pages[0].extract_text() or ""
            m = re.search(r'(?:–|-)\s*([A-Za-zÀ-ÿ]+)\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})', txt)
            if m:
                jour = int(m.group(2))
                mois_nom = m.group(3).lower()
                annee = int(m.group(4))
                mois = MOIS_FR.get(mois_nom, default_month)
                return date(annee, mois, jour)
            m2 = re.search(r'(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})', txt)
            if m2:
                jour = int(m2.group(1))
                mois_nom = m2.group(2).lower()
                annee = int(m2.group(3))
                mois = MOIS_FR.get(mois_nom, default_month)
                return date(annee, mois, jour)
    except Exception:
        pass
    # Repli : premier jour du mois par défaut
    return date(default_year, default_month, 1)

def classer_fichier(src_path: Path, default_year: int, default_month: int) -> Path:
    """Classe le fichier dans telechargements_pdf_classes/YYYY/MM/Semaine_WW/"""
    dt = extraire_date_du_pdf(src_path, default_year, default_month)
    week_num = dt.isocalendar()[1]
    target_dir = DEST_ROOT / f"{dt.year}" / f"{dt.month:02d}" / f"Semaine_{week_num:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    clean_stem = src_path.stem.strip()
    target_file = target_dir / f"{clean_stem}.pdf"
    
    if not target_file.exists():
        import shutil
        shutil.copy2(src_path, target_file)
    return target_file

def telecharger_url(url: str, session: requests.Session) -> bytes:
    """Télécharge le PDF avec gestion des encodages d'URL."""
    # Sécuriser l'URL avec encodage correct
    base_part, fname_part = url.rsplit('/', 1)
    clean_url = f"{base_part}/{quote(unquote(fname_part))}"
    
    r = session.get(clean_url, timeout=25, verify=False)
    if r.status_code == 200 and len(r.content) > 1000:
        return r.content
    # Essai avec http simple si https échoue
    if clean_url.startswith("https://"):
        http_url = clean_url.replace("https://", "http://", 1)
        r2 = session.get(http_url, timeout=25)
        if r2.status_code == 200 and len(r2.content) > 1000:
            return r2.content
    raise ValueError(f"HTTP {r.status_code} - taille {len(r.content)}")

def main():
    import urllib3
    urllib3.disable_warnings()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    lines = URLS_FILE.read_text(encoding="utf-8").splitlines()
    target_items = []
    for l in lines:
        l = l.strip()
        if not l: continue
        m = re.search(r'/(\d{4})-(\d{2})/', l)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            if year > 2025 or (year == 2025 and month >= 5):
                target_items.append((year, month, l))

    print(f"Total bulletins cibles (Mai 2025 à Aujourd'hui) : {len(target_items)}")
    
    # 1. Traitement des fichiers déjà présents dans telechargements_pdf
    raw_files = {p.name.lower(): p for p in RAW_DIR.glob("*.pdf")}
    classes_files = {p.name.lower(): p for p in DEST_ROOT.rglob("*.pdf")}
    
    session = get_session()
    nb_classes_locaux = 0
    nb_telecharges = 0
    nb_echecs = 0

    print("\n--- PHASE 1 : Classification des fichiers locaux non encore classés ---")
    for y, m, u in target_items:
        fn = unquote(u.split('/')[-1]).strip()
        fn_low = fn.lower()
        if fn_low not in classes_files:
            if fn_low in raw_files:
                src = raw_files[fn_low]
                dest = classer_fichier(src, y, m)
                classes_files[fn_low] = dest
                nb_classes_locaux += 1

    print(f"  -> {nb_classes_locaux} bulletins locaux classés.")

    print("\n--- PHASE 2 : Téléchargement des bulletins manquants ---")
    to_download = []
    for y, m, u in target_items:
        fn = unquote(u.split('/')[-1]).strip()
        fn_low = fn.lower()
        if fn_low not in classes_files:
            to_download.append((y, m, fn, u))

    print(f"  Bulletins à télécharger : {len(to_download)}")

    for i, (y, m, fn, u) in enumerate(to_download, 1):
        print(f"[{i}/{len(to_download)}] Téléchargement : {fn} ({y}-{m:02d})...", end="", flush=True)
        raw_dest = RAW_DIR / fn
        try:
            content = telecharger_url(u, session)
            raw_dest.write_bytes(content)
            class_dest = classer_fichier(raw_dest, y, m)
            classes_files[fn.lower()] = class_dest
            nb_telecharges += 1
            print(" [OK]")
        except Exception as e:
            nb_echecs += 1
            print(f" [FAIL: {e}]")

    print(f"\n{'='*70}")
    print(f" SYNTHÈSE DU RATTRAPAGE (Mai 2025 -> Maintenant)")
    print(f" Bulletins locaux nouvellement classés : {nb_classes_locaux}")
    print(f" Bulletins nouvellement téléchargés     : {nb_telecharges}")
    print(f" Échecs                                : {nb_echecs}")
    total_actuel = len(list(DEST_ROOT.rglob("*.pdf")))
    print(f" Total global bulletins classés en local : {total_actuel}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
