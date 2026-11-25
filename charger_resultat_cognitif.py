import json
import sqlite3
import sys
from pathlib import Path
from extract_and_load_resultats import save_resultat_to_db
from coherence_resultats import verifier_et_corriger_dossier

DB_PATH = Path("marches_publics_burkina.db")

def inserer_dossier_cognitif(dossier_dict: dict, bulletin_nom: str, source_pdf: str, date_parution=None):
    """Insère un résultat analysé cognitivement dans la base de données SQLite."""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Construire une unité minimale pour les métadonnées de page
        unit = {
            "_numero": dossier_dict.get("index_resultat", 1),
            "emetteur": dossier_dict.get("autorite_contractante", "Inconnu"),
            "page_debut": dossier_dict.get("page_debut", 1),
            "page_fin": dossier_dict.get("page_fin", 1),
            "macro_section": dossier_dict.get("macro_section", "MINISTERES")
        }
        
        # Enregistrer dans la base de données
        resultat_id = save_resultat_to_db(
            conn=conn,
            data=dossier_dict,
            unit=unit,
            bulletin_name=bulletin_nom,
            date_parution=date_parution,
            source_pdf=source_pdf
        )
        conn.commit()
        
        # Vérification et correction de la cohérence arithmétique / réglementaire
        anomalies = verifier_et_corriger_dossier(conn, resultat_id)
        conn.commit()
        
        print(f"[SUCCES] Dossier inséré: {resultat_id} | Lots: {len(dossier_dict.get('lots', []))} | Anomalies: {len(anomalies)}")
        if anomalies:
            for a in anomalies:
                print(f"   [ANOMALIE] {a}")
        return resultat_id
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python charger_resultat_cognitif.py <fichier_json> <bulletin_nom> <source_pdf>")
        sys.exit(1)
        
    json_file = sys.argv[1]
    bulletin = sys.argv[2]
    source_pdf = sys.argv[3]
    
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if isinstance(data, list):
        for item in data:
            inserer_dossier_cognitif(item, bulletin, source_pdf)
    else:
        inserer_dossier_cognitif(data, bulletin, source_pdf)
