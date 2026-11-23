#!/usr/bin/env python3
"""
pdf_downloader.py — Téléchargement des Quotidiens DGCMEF (Burkina Faso)

Deux modes d'utilisation :
  1. Mode Rattrapage (--mode catchup) :
     Calibre la régression sur urls_valides_verifiees.txt, identifie le dernier numéro
     connu (août 2026 / N°4468), génère la wordlist ciblée jusqu'à la date d'aujourd'hui,
     détecte les URLs valides et télécharge les PDF dans telechargements_pdf/.
     
  2. Mode Quotidien (--mode daily) :
     Mode production pour récupérer le nouveau numéro du jour (N+1, N+2) et le télécharger.

Usage :
    python pdf_downloader.py --mode catchup
    python pdf_downloader.py --mode catchup --out-dir telechargements_pdf
    python pdf_downloader.py --mode daily
"""

import os
import re
import sys
import time
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scrapperbf.downloader")

BASE_DIR = Path(__file__).parent
DEFAULT_VERIFIED_FILE = BASE_DIR / "files" / "urls_valides_verifiees.txt"
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "telechargements_pdf"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 DGCMEFDownloader/2.0"
)

# Domaine canonique unique (évite toute redondance http/https/www)
CANONICAL_DOMAIN = "https://dgcmef.gov.bf"

# Patterns de nom de fichier observés chez la DGCMEF
FILENAME_TEMPLATES = [
    lambda n: f"Quotidien N°{n}.pdf",
    lambda n: f"Quotidien n°{n}.pdf",
    lambda n: f"Quotidien N°{n} .pdf",
    lambda n: f"Quotidien n°{n} .pdf",
    lambda n: f"Quotidien N° {n}.pdf",
    lambda n: f"Quotidien n° {n}.pdf",
    lambda n: f"Quotidien N°{n}_0.pdf",
    lambda n: f"Quotidien N°{n}_1.pdf",
    lambda n: f"Quotidien N°{n} (bis).pdf",
    lambda n: f"Quotidien N°{n}(bis).pdf",
    lambda n: f"Quotidien N°{n} (bis)_C.pdf",
    lambda n: f"Quotidien N°{n}-{n+1}.pdf",
    lambda n: f"Quotidien n°{n}-{n+1}.pdf",
    lambda n: f"Quotidien N°{n} bis.pdf",
    lambda n: f"QUOTIDIEN_N°{n}.pdf",
]



def make_session(max_retries=2, timeout=15):
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=max_retries,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def load_calibration(verified_file_path: Path):
    """Calibre la régression à partir des URLs déjà connues."""
    if not verified_file_path.exists():
        log.warning("Fichier %s non trouvé, valeurs par défaut appliquées", verified_file_path)
        return 21.71, 4468, (2026, 8)

    lines = verified_file_path.read_text(encoding="utf-8").splitlines()
    date_re = re.compile(r'/(\d{4})-(\d{2})/')
    num_re = re.compile(r'[Nn]°\s*(\d{3,4})')

    by_month = {}
    max_num = 0
    max_ym = (2022, 1)

    for l in lines:
        l = l.strip()
        if not l:
            continue
        dm = date_re.search(l)
        if not dm:
            continue
        y, mo = int(dm.group(1)), int(dm.group(2))
        nm = num_re.search(l)
        if not nm:
            continue
        num = int(nm.group(1))
        if num < 2500:
            continue
        by_month.setdefault((y, mo), []).append(num)
        if (y, mo) > max_ym:
            max_ym = (y, mo)
        if num > max_num:
            max_num = num

    # Régression linéaire : slope, intercept
    points = []
    for (y, mo), nums in by_month.items():
        idx_mois = y * 12 + mo
        points.append((idx_mois, sum(nums) / len(nums)))

    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] ** 2 for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = (n * sxx - sx * sx)
    slope = (n * sxy - sx * sy) / denom if denom != 0 else 21.71

    log.info("Calibration : dernier PDF trouvé = N°%d (%04d-%02d), pente = %.2f numéros/mois",
             max_num, max_ym[0], max_ym[1], slope)
    return slope, max_num, max_ym


def generate_catchup_wordlist(max_num: int, start_ym: tuple, end_date: date, start_from_num: int = None, exclude_filenames: set = None):
    """
    Génère les URLs candidates canoniques (HTTPS unique) entre start_ym et end_date.
    Supporte la reprise (start_from_num) pour ne pas re-tester ce qui a déjà été scanné.
    """
    wordlist = []
    current_y, current_m = start_ym
    target_y, target_m = end_date.year, end_date.month

    exclude_filenames = exclude_filenames or set()

    # On balaie les mois depuis start_ym jusqu'au mois actuel
    months_to_cover = []
    y, m = current_y, current_m
    while (y, m) <= (target_y, target_m):
        months_to_cover.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    # Numéro de départ pour le rattrapage : max_num - 5 (marge de sécurité)
    base_num = max(1, max_num - 5)
    for i, (ym_y, ym_m) in enumerate(months_to_cover):
        ym_str = f"{ym_y:04d}-{ym_m:02d}"
        min_n = base_num + int(i * 20)
        max_n = min_n + 35  # environ 25 à 30 quotidiens par mois ouvrable

        # Si un numéro de reprise est demandé pour ne pas refaire les anciens
        if start_from_num and max_n < start_from_num:
            log.info("Mois %s ignoré (déjà scanné jusqu'au N°%d)", ym_str, max_n)
            continue
        if start_from_num and min_n < start_from_num:
            min_n = start_from_num

        log.info("Génération candidats %s : numéros N°%d à N°%d", ym_str, min_n, max_n)

        for n in range(min_n, max_n + 1):
            for tpl in FILENAME_TEMPLATES:
                filename = tpl(n)
                if filename in exclude_filenames:
                    continue
                url = f"{CANONICAL_DOMAIN}/sites/default/files/{ym_str}/{filename}"
                wordlist.append(url)

    # Déduplication
    seen = set()
    dedup = []
    for u in wordlist:
        if u not in seen:
            seen.add(u)
            dedup.append(u)

    log.info("Wordlist rattrapage générée : %d URLs uniques candidates (domaine canonique %s)",
             len(dedup), CANONICAL_DOMAIN)
    return dedup


def check_and_download_url(url: str, session: requests.Session, out_dir: Path, check_only: bool = False) -> dict:
    """Teste si l'URL existe (200). Si check_only est True, ne télécharge pas le fichier."""
    try:
        # 1. Vérification HEAD
        r = session.head(url, timeout=12, allow_redirects=True)
        if r.status_code != 200 or "html" in (r.headers.get("Content-Type") or "").lower():
            # Fallback léger GET (certains serveurs bloquent HEAD)
            r = session.get(url, stream=True, timeout=12, headers={"Range": "bytes=0-1024"})
            if r.status_code not in (200, 206):
                return {"url": url, "ok": False, "status": r.status_code}

        # URL confirmée valide (code 200/206 et contenu PDF)
        if check_only:
            log.info("[URL VALIDE TROUVÉE] %s", url)
            return {"url": url, "ok": True, "downloaded": False}

        # 2. Téléchargement réel du PDF (si check_only est False)
        filename = unquote(url.split("/")[-1])
        # Nettoyage nom de fichier local
        clean_name = re.sub(r'[\\/*?:"<>|]', "_", filename).strip()
        target_path = out_dir / clean_name

        if target_path.exists() and target_path.stat().st_size > 10000:
            log.info("[DÉJÀ TÉLÉCHARGÉ] %s", clean_name)
            return {"url": url, "ok": True, "path": str(target_path), "downloaded": False}

        log.info("[TÉLÉCHARGEMENT...] %s -> %s", url, clean_name)
        dl_resp = session.get(url, stream=True, timeout=30)
        if dl_resp.status_code == 200:
            with open(target_path, "wb") as f:
                for chunk in dl_resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            log.info("[SUCCÈS] Sauvegardé : %s (%d Ko)", clean_name, target_path.stat().st_size // 1024)
            return {"url": url, "ok": True, "path": str(target_path), "downloaded": True}

    except Exception as e:
        return {"url": url, "ok": False, "error": str(e)}

    return {"url": url, "ok": False}


def run_catchup(verified_file=DEFAULT_VERIFIED_FILE, out_dir=DEFAULT_DOWNLOAD_DIR, workers=10, check_only=False, batch_size=50, batch_delay=0.5, start_num: int = None, resume: bool = True):
    """Exécute la vérification ou le rattrapage par lots de 50 URLs avec reprise automatique."""
    out_dir = Path(out_dir)
    if not check_only:
        out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    slope, max_num, max_ym = load_calibration(Path(verified_file))

    results_file = BASE_DIR / "urls_valides_aout_octobre.txt"
    seen_urls = set()
    seen_filenames = set()
    found_nums = []

    # Charge ce qui a déjà été trouvé
    if results_file.exists():
        for line in results_file.read_text(encoding="utf-8").splitlines():
            l = line.strip()
            if l:
                seen_urls.add(l)
                fn = l.split("/")[-1]
                seen_filenames.add(fn)
                m = re.search(r'[Nn]°\s*(\d{3,4})', fn)
                if m:
                    found_nums.append(int(m.group(1)))

    if start_num is None and resume and found_nums:
        start_from_num = max(found_nums) + 1
        log.info("Mode Reprise activé : %d PDF déjà validés (jusqu'au N°%d) -> reprise à partir du N°%d",
                 len(seen_filenames), max(found_nums), start_from_num)
    else:
        start_from_num = start_num

    candidates = generate_catchup_wordlist(
        max_num, max_ym, today,
        start_from_num=start_from_num,
        exclude_filenames=seen_filenames
    )
    session = make_session()

    total_candidates = len(candidates)
    if total_candidates == 0:
        log.info("Aucune nouvelle URL à vérifier : tout est déjà à jour !")
        return []

    total_batches = (total_candidates + batch_size - 1) // batch_size

    log.info("Lancement du scan : %d URLs candidates réparties en %d lots de %d URLs (workers=%d, mode=%s)",
             total_candidates, total_batches, batch_size, workers,
             "VÉRIFICATION SEULE" if check_only else "TÉLÉCHARGEMENT DIRECT")

    # Écriture immédiate / incrémentale
    res_f = open(results_file, "a", encoding="utf-8")
    trouvees = []

    try:
        for b_idx in range(total_batches):
            start_i = b_idx * batch_size
            end_i = min(start_i + batch_size, total_candidates)
            batch = candidates[start_i:end_i]

            log.info(">>> DÉBUT LOT %d/%d (URLs %d à %d / %d) <<<",
                     b_idx + 1, total_batches, start_i + 1, end_i, total_candidates)

            with ThreadPoolExecutor(max_workers=min(workers, len(batch))) as executor:
                futures = {executor.submit(check_and_download_url, u, session, out_dir, check_only): u for u in batch}
                for future in as_completed(futures):
                    res = future.result()
                    if res.get("ok"):
                        u = res["url"]
                        trouvees.append(res)
                        if u not in seen_urls:
                            seen_urls.add(u)
                            res_f.write(u + "\n")
                            res_f.flush()

            log.info("<<< FIN DU LOT %d/%d — Total cumulé trouvé : %d URLs valides uniques >>>",
                     b_idx + 1, total_batches, len(seen_urls))

            if batch_delay > 0 and b_idx + 1 < total_batches:
                time.sleep(batch_delay)

    finally:
        res_f.close()

    log.info("=== SCAN TERMINÉ ===")
    log.info("Total URLs valides uniques conservées dans : %s (%d URLs)", results_file, len(seen_urls))

    # Mise à jour du fichier d'URLs vérifiées principal
    if seen_urls and Path(verified_file).exists():
        existantes = set(Path(verified_file).read_text(encoding="utf-8").splitlines())
        nouvelles = [u for u in seen_urls if u not in existantes]
        if nouvelles:
            with open(verified_file, "a", encoding="utf-8") as f:
                for u in nouvelles:
                    f.write(u + "\n")
            log.info("Ajout de %d nouvelle(s) URL(s) dans %s", len(nouvelles), verified_file)

    return trouvees


def run_daily_fetch(verified_file=DEFAULT_VERIFIED_FILE, out_dir=DEFAULT_DOWNLOAD_DIR):
    """Mode production quotidienne : tente les numéros N+1, N+2, N+3 du jour."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    slope, max_num, max_ym = load_calibration(Path(verified_file))
    session = make_session()

    ym_str = f"{today.year:04d}-{today.month:02d}"
    log.info("Mode Quotidien : recherche du prochain numéro pour %s (dernier connu = N°%d)", ym_str, max_num)

    candidates = []
    for n in range(max_num, max_num + 5):
        for tpl in FILENAME_TEMPLATES:
            fn = tpl(n)
            candidates.append(f"{CANONICAL_DOMAIN}/sites/default/files/{ym_str}/{fn}")

    trouves = []
    for u in candidates:
        res = check_and_download_url(u, session, out_dir)
        if res.get("ok"):
            trouves.append(res)

    log.info("Mode Quotidien terminé : %d nouveau(x) PDF(s) récupéré(s)", len(trouves))
    return trouves


def download_year(year: int = 2026, verified_file: str = str(DEFAULT_VERIFIED_FILE),
                  out_dir: str = str(DEFAULT_DOWNLOAD_DIR), workers: int = 10):
    """Télécharge l'ensemble des PDFs connus d'une année donnée."""
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    vfile = Path(verified_file)

    if not vfile.exists():
        log.error("Fichier d'index %s introuvable", verified_file)
        return []

    lines = vfile.read_text(encoding="utf-8").splitlines()
    year_prefix = f"/{year:04d}-"
    
    # Extraire et dédoublonner les URLs de l'année
    urls_to_download = []
    seen = set()
    for l in lines:
        l = l.strip()
        if not l or year_prefix not in l:
            continue
        canon = unquote(l)
        if canon not in seen:
            seen.add(canon)
            urls_to_download.append(canon)

    log.info("Lancement du téléchargement pour l'année %d : %d URLs uniques (workers=%d, dossier=%s)",
             year, len(urls_to_download), workers, dest)

    session = make_session()
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_and_download_url, u, session, dest, False): u
                   for u in urls_to_download}
        for future in as_completed(futures):
            res = future.result()
            results.append(res)

    nb_ok = sum(1 for r in results if r.get("ok"))
    nb_new = sum(1 for r in results if r.get("downloaded"))
    log.info("=== FIN DU TÉLÉCHARGEMENT %d === : %d/%d réussis (%d nouveaux téléchargés)",
             year, nb_ok, len(urls_to_download), nb_new)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Téléchargeur de Quotidiens DGCMEF")
    parser.add_argument("--mode", choices=["catchup", "daily", "year"], default="catchup",
                        help="catchup = rattrapage ; daily = veille quotidienne ; year = téléchargement d'une année")
    parser.add_argument("--year", type=int, default=2026, help="Année à télécharger (ex: 2026)")
    parser.add_argument("--out-dir", default=str(DEFAULT_DOWNLOAD_DIR), help="Dossier de destination")
    parser.add_argument("--workers", type=int, default=10, help="Nombre de threads parallèles")
    parser.add_argument("--batch-size", type=int, default=50, help="Taille des lots d'URLs à vérifier (défaut 50)")
    parser.add_argument("--batch-delay", type=float, default=0.5, help="Pause en secondes entre chaque lot (défaut 0.5s)")
    parser.add_argument("--check-only", action="store_true",
                        help="Vérifie uniquement l'existence des URLs sans télécharger les fichiers PDF")
    parser.add_argument("--start-num", type=int, default=None,
                        help="Numéro de bulletin de départ forcé (ex: 4500)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Désactive la reprise automatique à partir du dernier numéro vérifié")
    args = parser.parse_args()

    if args.mode == "catchup":
        run_catchup(out_dir=args.out_dir, workers=args.workers, check_only=args.check_only,
                    batch_size=args.batch_size, batch_delay=args.batch_delay,
                    start_num=args.start_num, resume=(not args.no_resume))
    elif args.mode == "year":
        download_year(year=args.year, out_dir=args.out_dir, workers=args.workers)
    else:
        run_daily_fetch(out_dir=args.out_dir)

