import sqlite3
import re

def clean_contact_field(raw_tel, raw_bp, raw_obs):
    """
    Nettoie et sépare:
    - telephone (vrais numéros ex: +226 xx xx xx xx ou 70 22 86 79)
    - adresse_bp (ex: 01 BP 02 Saaba 01, 11 BP 1564 Ouagadougou 11)
    - observations (ex: Confirmation des prix unitaires par lettre n°...)
    """
    tel_out = raw_tel or ""
    bp_out = raw_bp or ""
    obs_out = raw_obs or ""

    if not tel_out:
        return tel_out, bp_out, obs_out

    # Cas 1: Détection de notes administratives/procédurales dans le téléphone
    admin_patterns = [
        r"confirmation.*",
        r"lettre\s+n[°o].*",
        r"offre\s+(?:financière|technique|conforme|rejetée).*",
        r"rabais.*",
        r"sous\s+réserve.*"
    ]
    is_admin = False
    for pat in admin_patterns:
        if re.search(pat, tel_out, re.IGNORECASE):
            is_admin = True
            break
            
    if is_admin:
        # Déplacer vers observations
        if obs_out:
            obs_out = f"{obs_out} | {tel_out}"
        else:
            obs_out = tel_out
        tel_out = ""
        return tel_out, bp_out, obs_out

    # Cas 2: Tel contient à la fois BP/adresse et Téléphone (ex: "01BP 02 SAABA 01, Tel : +226 70 22 86 79/ 78 07 48 83")
    # Extraire BP ou adresse
    bp_match = re.search(r"((?:s/c\s*)?\d+\s*BP\s*\d+[^,\n]+)", tel_out, re.IGNORECASE)
    if bp_match:
        found_bp = bp_match.group(1).strip()
        if not bp_out:
            bp_out = found_bp
        tel_out = tel_out.replace(bp_match.group(0), "")

    # Nettoyer préfixes "Tel :", "Tél :", "Tel:", etc.
    tel_out = re.sub(r"^(?:,\s*)?(?:t[eé]l\s*[:\.]?\s*)+", "", tel_out, flags=re.IGNORECASE).strip()
    tel_out = tel_out.strip(" ,;:-")

    return tel_out, bp_out, obs_out


def detect_ville(text):
    if not text:
        return None
    t = text.lower()
    villes = [
        "ouagadougou", "ouaga", "bobo-dioulasso", "bobo", "koudougou",
        "ouahigouya", "fada n'gourma", "fada", "dédougou", "dedougou",
        "banfora", "kaya", "tenkodogo", "ziniaré", "ziniare", "manga",
        "dori", "gaoua", "saaba", "pô", "po", "koupéla", "koupela"
    ]
    for v in villes:
        if v in t:
            if v in ["ouaga", "ouagadougou"]:
                return "Ouagadougou"
            if v in ["bobo", "bobo-dioulasso"]:
                return "Bobo-Dioulasso"
            if v in ["dédougou", "dedougou"]:
                return "Dédougou"
            if v in ["ziniaré", "ziniare"]:
                return "Ziniaré"
            if v in ["koupéla", "koupela"]:
                return "Koupéla"
            return v.capitalize()
    return None


def run():
    con = sqlite3.connect('marches_publics_burkina.db')
    c = con.cursor()
    c.execute("SELECT id, nom_soumissionnaire, telephone, adresse_bp, observations_motifs FROM resultats_soumissionnaires WHERE telephone IS NOT NULL AND length(telephone) > 0")
    rows = c.fetchall()

    cleaned_count = 0
    for rid, nom, tel, bp, obs in rows:
        c_tel, c_bp, c_obs = clean_contact_field(tel, bp, obs)
        if c_tel != tel or c_bp != bp or c_obs != obs:
            c.execute("""
                UPDATE resultats_soumissionnaires 
                SET telephone = ?, adresse_bp = ?, observations_motifs = ?
                WHERE id = ?
            """, (c_tel if c_tel else None, c_bp if c_bp else None, c_obs if c_obs else None, rid))
            cleaned_count += 1

    con.commit()
    print(f"Lignes mises à jour dans resultats_soumissionnaires : {cleaned_count}")

    # Vérification pour ABM Expertises Africa
    c.execute("SELECT id, nom_soumissionnaire, telephone, observations_motifs FROM resultats_soumissionnaires WHERE nom_soumissionnaire LIKE '%ABM%'")
    print("Vérification ABM:", c.fetchall())
    con.close()

if __name__ == "__main__":
    run()
