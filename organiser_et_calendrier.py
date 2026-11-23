import os
import re
import shutil
import glob
from pathlib import Path
from datetime import datetime, date, timedelta
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

# Numéro depuis le nom de fichier
num_file_re = re.compile(r'[Nn][°o]\s*(\d{3,4})')

# Index URLs validées
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
    """Extrait la date exacte correspondant au numéro du bulletin."""
    basename = os.path.basename(filepath)
    nm = num_file_re.search(basename)
    target_num = nm.group(1) if nm else None

    try:
        with pdfplumber.open(filepath) as pdf:
            txt = pdf.pages[0].extract_text() or ""
            
            # 1. Si on a le numéro de bulletin, chercher la date sur la même ligne ou immédiatement après
            if target_num:
                # Chercher la ligne contenant le numéro du bulletin
                for line in txt.splitlines():
                    if target_num in line:
                        m = date_pattern.search(line)
                        if m:
                            jour = int(m.group(1))
                            mois_nom = m.group(2).lower()
                            annee = int(m.group(3))
                            mois = MOIS_FR.get(mois_nom)
                            if mois and 1 <= jour <= 31:
                                return date(annee, mois, jour)

            # 2. Chercher dans l'ensemble des 15 premières lignes les couples (N°xxxx, date)
            matches = re.findall(r'N[°o]\s*(\d{4}).*?(\d{1,2}(?:er)?\s+[a-zéûë]+\s+\d{4})', txt, re.IGNORECASE)
            for n_found, d_found in matches:
                if target_num and n_found == target_num:
                    m = date_pattern.search(d_found)
                    if m:
                        jour = int(m.group(1))
                        mois_nom = m.group(2).lower()
                        annee = int(m.group(3))
                        mois = MOIS_FR.get(mois_nom)
                        if mois:
                            return date(annee, mois, jour)

            # 3. Prendre la date la plus récente mentionnée avec 2026
            dates_2026 = []
            for line in txt.splitlines()[:15]:
                m = date_pattern.search(line)
                if m:
                    annee = int(m.group(3))
                    if annee == 2026:
                        jour = int(m.group(1))
                        mois_nom = m.group(2).lower()
                        mois = MOIS_FR.get(mois_nom)
                        if mois and 1 <= jour <= 31:
                            dates_2026.append(date(annee, mois, jour))
            if dates_2026:
                return dates_2026[-1]

    except Exception:
        pass

    # Fallback par l'index des URLs connues
    if basename in name_to_ym:
        y, m = name_to_ym[basename]
        return date(y, m, 1)

    return None

def classer_et_analyser_calendrier(source_dir="telechargements_pdf", dest_root="telechargements_pdf_classes"):
    pdf_files = glob.glob(f"{source_dir}/*.pdf")
    print(f"Total fichiers PDF à traiter : {len(pdf_files)}")

    dest_path = Path(dest_root)
    # Nettoyer l'ancien dossier pour éviter les résidus
    if dest_path.exists():
        shutil.rmtree(dest_path)
    dest_path.mkdir(parents=True, exist_ok=True)

    date_to_files = {}
    stats_dossiers = {}

    for p in pdf_files:
        d = extract_date_from_pdf(p)
        fname = os.path.basename(p)

        if d:
            isocal = d.isocalendar()
            week_num = isocal[1]
            folder = dest_path / f"{d.year}" / f"{d.month:02d}" / f"Semaine_{week_num:02d}"
            date_to_files.setdefault(d, []).append(fname)
        else:
            folder = dest_path / "Non_classes"
            date_to_files.setdefault("inconnu", []).append(fname)

        folder.mkdir(parents=True, exist_ok=True)
        target = folder / fname
        shutil.copy2(p, target)
        rel_key = str(folder.relative_to(dest_path))
        stats_dossiers[rel_key] = stats_dossiers.get(rel_key, 0) + 1

    print("\nClassement physique terminé avec succès !")

    # Calendrier complet jour par jour (du 01/01/2026 au 31/10/2026)
    start_date = date(2026, 1, 1)
    end_date = date(2026, 10, 31)

    current = start_date
    jours_ouvres_total = 0
    jours_avec_pdf = 0
    jours_sans_pdf = []

    rapport_lignes = []
    rapport_lignes.append("# Calendrier Quotidien DGCMEF 2026 - Disponibilité Jour par Jour\n")
    rapport_lignes.append("| Date | Jour | Semaine | Statut | Fichier(s) Téléchargé(s) |")
    rapport_lignes.append("|:---|:---|:---:|:---:|:---|")

    jours_semaine_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

    while current <= end_date:
        weekday = current.weekday()
        jour_nom = jours_semaine_fr[weekday]
        iso_semaine = current.isocalendar()[1]
        date_str = current.strftime("%Y-%m-%d")

        is_weekend = (weekday >= 5)
        files = date_to_files.get(current, [])

        if not is_weekend:
            jours_ouvres_total += 1
            if files:
                jours_avec_pdf += 1
                statut = "✅ **DISPONIBLE**"
                fichiers_str = "<br>".join(files)
            else:
                jours_sans_pdf.append((date_str, jour_nom))
                statut = "❌ *ABSENT*"
                fichiers_str = "—"
        else:
            if files:
                statut = "⚠️ **WEEK-END (Publié)**"
                fichiers_str = "<br>".join(files)
            else:
                statut = "⚪ *Week-end*"
                fichiers_str = "—"

        rapport_lignes.append(f"| {date_str} | {jour_nom} | S{iso_semaine:02d} | {statut} | {fichiers_str} |")
        current += timedelta(days=1)

    calendrier_path = Path("calendrier_bulletins_2026.md")
    calendrier_path.write_text("\n".join(rapport_lignes), encoding="utf-8")
    print(f"\nCalendrier enregistré dans : {calendrier_path}")

    taux_presence = (jours_avec_pdf / jours_ouvres_total) * 100 if jours_ouvres_total else 0
    print(f"\n=== STATISTIQUES CALENDRIER 2026 ===")
    print(f"Jours ouvrés théoriques (01/01 au 31/10) : {jours_ouvres_total}")
    print(f"Jours ouvrés avec PDF : {jours_avec_pdf} ({taux_presence:.1f}%)")
    print(f"Jours ouvrés sans PDF : {len(jours_sans_pdf)}")

if __name__ == "__main__":
    classer_et_analyser_calendrier()
