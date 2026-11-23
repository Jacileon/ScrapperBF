import os
import re
import shutil
import glob
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote
import pdfplumber

MOIS_FR = {
    'janvier': 1, 'fevrier': 2, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'aout': 8, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12, 'décembre': 12
}

date_pattern = re.compile(
    r'(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*(\d{1,2})(?:er)?\s+([a-zéûë]+)\s+(\d{4})',
    re.IGNORECASE
)

# 1. Charger la table d'index URLs pour correspondance mois/an si la une a une ambiguïté
name_to_ym = {}
date_url_re = re.compile(r'/(\d{4})-(\d{2})/')
if os.path.exists("files/urls_valides_verifiees.txt"):
    with open("files/urls_valides_verifiees.txt", "r", encoding="utf-8") as f:
        for l in f:
            canon = unquote(l.strip())
            fname = canon.split("/")[-1]
            clean_name = re.sub(r'[\\/*?:\"<>|]', '_', fname).strip()
            dm = date_url_re.search(canon)
            if dm:
                name_to_ym[clean_name] = (int(dm.group(1)), int(dm.group(2)))

def extract_date_from_pdf(filepath):
    try:
        with pdfplumber.open(filepath) as pdf:
            txt = pdf.pages[0].extract_text() or ""
            # On cherche sur les 6 premières lignes
            first_lines = "\n".join(txt.splitlines()[:10])
            m = date_pattern.search(first_lines)
            if m:
                jour = int(m.group(1))
                mois_nom = m.group(2).lower()
                annee = int(m.group(3))
                mois = MOIS_FR.get(mois_nom)
                if mois and 1 <= jour <= 31:
                    return datetime(annee, mois, jour)
    except Exception as e:
        pass

    # Fallback par le nom et index url
    basename = os.path.basename(filepath)
    if basename in name_to_ym:
        y, m = name_to_ym[basename]
        return datetime(y, m, 1)

    return None

def classer_pdfs(source_dir="telechargements_pdf", dest_root="telechargements_pdf_classes"):
    pdf_files = glob.glob(f"{source_dir}/*.pdf")
    print(f"Total fichiers PDF à classer : {len(pdf_files)}")

    dest_path = Path(dest_root)
    dest_path.mkdir(parents=True, exist_ok=True)

    classement_stats = {}
    for p in pdf_files:
        dt = extract_date_from_pdf(p)
        fname = os.path.basename(p)

        if dt:
            year = dt.year
            month = dt.month
            # Semaine ISO : ex Semaine_01, Semaine_02
            isocal = dt.isocalendar()
            week_num = isocal[1]
            folder = dest_path / f"{year}" / f"{month:02d}" / f"Semaine_{week_num:02d}"
        else:
            folder = dest_path / "Non_classes"

        folder.mkdir(parents=True, exist_ok=True)
        target_file = folder / fname
        shutil.copy2(p, target_file)

        key = str(folder.relative_to(dest_path))
        classement_stats[key] = classement_stats.get(key, 0) + 1

    print("\n=== CLASSEMENT TERMINÉ ===")
    total_copies = sum(classement_stats.values())
    print(f"Total fichiers classés avec succès : {total_copies}")
    print("\nArborescence générée (Dossiers et nombre de PDFs) :")
    for k in sorted(classement_stats.keys()):
        print(f"  {k} : {classement_stats[k]} PDF(s)")

if __name__ == "__main__":
    classer_pdfs()
