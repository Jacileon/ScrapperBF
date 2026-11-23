import os
import re
import ssl
import json
import urllib.request
from datetime import datetime, date
from pathlib import Path
import shutil

MOIS_FR = {
    'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12, 'décembre': 12
}

date_pattern = re.compile(
    r'(\d{1,2})(?:er)?\s+([a-zéûë]+)\s+(\d{3,4})',
    re.IGNORECASE
)

num_pattern = re.compile(r'[Nn][°o\s]+(\d{3,4})')

def parse_titre_secop(titre, date_pub=None):
    """Extrait le numéro et la date depuis le titre SECOP avec fallback sur datePublication."""
    num_m = num_pattern.search(titre)
    num = num_m.group(1) if num_m else "Inconnu"

    dt_m = date_pattern.search(titre)
    dt = None
    if dt_m:
        jour = int(dt_m.group(1))
        mois_str = dt_m.group(2).lower()
        annee_str = dt_m.group(3)
        # Gestion des coquilles de saisie éventuelles comme "202" au lieu de "2026"
        if len(annee_str) == 3:
            annee = int(annee_str + "6")
        else:
            annee = int(annee_str)
            
        mois = MOIS_FR.get(mois_str)
        if mois:
            dt = date(annee, mois, jour)

    if not dt and date_pub:
        try:
            parsed = datetime.fromisoformat(date_pub)
            dt = parsed.date()
        except Exception:
            pass

    return num, dt

def download_and_classify_secop():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    }

    list_url = 'https://secop-gateway.finances.bf/api/revue/publications/quotidiens?page=0&size=50&service=revue-ms'
    req = urllib.request.Request(list_url, headers=headers)
    
    print("1. Récupération de la liste des publications SECOP...")
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    items = data.get('content', [])
    print(f"   {len(items)} parutions trouvées sur SECOP.")

    download_dir = Path("telechargements_pdf")
    download_dir.mkdir(parents=True, exist_ok=True)

    dest_root = Path("telechargements_pdf_classes")
    dest_root.mkdir(parents=True, exist_ok=True)

    downloaded = []
    skipped = []

    for item in items:
        pub_id = item.get('id')
        titre = item.get('titre', '')
        date_pub = item.get('datePublication')
        num, dt = parse_titre_secop(titre, date_pub)
        pdfs = item.get('pdfs', [])

        for pdf_info in pdfs:
            rang = pdf_info.get('rang', 1)
            nom_base = f"Quotidien N°{num}.pdf" if rang == 1 else f"Quotidien N°{num}_rang{rang}.pdf"
            
            local_raw_path = download_dir / nom_base

            # Calcul du chemin classé
            if dt:
                isocal = dt.isocalendar()
                week_num = isocal[1]
                target_folder = dest_root / f"{dt.year}" / f"{dt.month:02d}" / f"Semaine_{week_num:02d}"
            else:
                target_folder = dest_root / "Non_classes"

            target_folder.mkdir(parents=True, exist_ok=True)
            classified_path = target_folder / nom_base

            # Vérifier si déjà téléchargé et non vide
            if local_raw_path.exists() and local_raw_path.stat().st_size > 0:
                if not classified_path.exists() or classified_path.stat().st_size == 0:
                    shutil.copy2(local_raw_path, classified_path)
                skipped.append(nom_base)
                continue

            # Téléchargement
            pdf_url = f"https://secop-gateway.finances.bf/api/revue/publications/quotidiens/{pub_id}/pdfs/{rang}?service=revue-ms"

            print(f"\nTéléchargement : {titre} (ID: {pub_id}, Rang: {rang})")
            print(f"  URL : {pdf_url}")
            
            pdf_req = urllib.request.Request(pdf_url, headers=headers)
            try:
                with urllib.request.urlopen(pdf_req, context=ctx, timeout=60) as p_resp:
                    content = p_resp.read()
                    with open(local_raw_path, 'wb') as f:
                        f.write(content)
                    print(f"  -> Sauvegardé dans telechargements_pdf/{nom_base} ({len(content)} octets)")
            except Exception as e:
                print(f"  ERREUR téléchargement : {e}")
                continue

            # Classement
            shutil.copy2(local_raw_path, classified_path)
            print(f"  -> Classé dans : {classified_path}")

            downloaded.append({
                'num': num,
                'titre': titre,
                'date': str(dt) if dt else 'Inconnue',
                'raw_path': str(local_raw_path),
                'classified_path': str(classified_path),
                'size': len(content)
            })

    print("\n=== BILAN DU TÉLÉCHARGEMENT ET CLASSEMENT SECOP ===")
    print(f"Fichiers déjà présents (ignorés) : {len(skipped)}")
    print(f"Nouveaux fichiers téléchargés et classés : {len(downloaded)}")
    for d in downloaded:
        print(f" - Quotidien N°{d['num']} ({d['date']}) : {d['size']} octets -> {d['classified_path']}")

if __name__ == '__main__':
    download_and_classify_secop()
