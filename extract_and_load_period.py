#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_and_load_period.py
==========================
Extraction structurée haute fidélité via FreeLLMAPI (routage auto intelligent)
et insertion directe dans SQLite marches_publics_burkina.db.
Cible : Toutes les annonces découpées uniques du 1er Octobre 2026 à aujourd'hui.
"""

import os
import re
import sys
import json
import time
import sqlite3
import threading
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from sector_classifier import classify_sector

DB_PATH = Path("marches_publics_burkina.db")
API_KEY = "freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8"
BASE_URL = "http://127.0.0.1:3001/v1/chat/completions"

# Routage automatique adaptatif pour garantir 0 saturation
PRIMARY_MODEL = "auto"
FALLBACK_MODELS = ["qwen3.8-27b", "plugsky-micro", "auto-route", "free-router"]

SYSTEM_PROMPT = """Tu es un expert analyste de la commande publique au Burkina Faso (DGCMEF).
Extrais les informations de l'avis d'appel d'offres en te conformant STRICTEMENT au schéma JSON ci-dessous :

RÈGLES D'OR :
1. Ne JAMAIS inventer. Si une information n'apparaît pas formellement dans le texte, mets STRICTEMENT null (qui vaut None).
2. Montants financiers : UNIQUEMENT des entiers numériques purs en FCFA (sans devise, ex: 18923644).
3. Dates : format JJ/MM/AAAA. Heures : format HH:MM TU.
4. Champ 'secteur_activite' (OBLIGATOIRE - choisir EXACTEMENT parmi la liste suivante) :
   - "BTP, Génie Civil & Construction"
   - "Santé, Médical & Pharmacie"
   - "Eau, Forages & Assainissement"
   - "Informatique & Télécoms"
   - "Véhicules, Transports & Hydrocarbures"
   - "Énergie & Électricité"
   - "Mobilier & Fournitures de Bureau"
   - "Agréments & Répertoires Fournisseurs"
   - "Gardiennage & Sécurité"
   - "Études, Audit & Conseil"
   - "Agriculture, Élevage & Forêt"
   - "Restauration & Événementiel"
   - "Services Généraux & Divers"
5. Champ 'remarque' (OBLIGATOIRE) :
   - null : annonce claire et complète.
   - "a verifier" : doute sur une date/montant ou texte tronqué.
   - "plusieurs valeurs non dispo" : dates ou montants manquants.
   - "presence de metadonnees tableau" : fragments de tableaux complexes.

SCHÉMA JSON STRICT À RETOURNER :
{
  "numero_bulletin": "ex: Quotidien N°4532",
  "date_parution": "ex: Lundi 16 novembre 2026",
  "pages": "ex: p. 30 ou p. 32 à 33",
  "categorie_marche": "Travaux | Fournitures et Services courants | Prestations intellectuelles | null",
  "secteur_activite": "BTP, Génie Civil & Construction | Santé, Médical & Pharmacie | Informatique & Télécoms | ...",
  "type_procedure": "Demande de prix | Appel d’offres ouvert | Manifestation d’intérêt | null",
  "reference_dossier": "ex: N° 2026-16/MS/SG/... ou null",
  "autorite_contractante": "Entité émettrice complète ou null",
  "ministere_tutelle": "ex: Ministère de la Santé ou null",
  "objet_marche": "Libellé fidèle de l'objet",
  "allotissement_type": "Lot unique | Lots multiples | null",
  "nombre_lots": 1,
  "detail_lots": [
    {"numero_lot": "Lot 1", "titre": null, "description": null, "montant_fcfa": null, "caution_fcfa": null}
  ],
  "budget_previsionnel_fcfa": null,
  "garantie_soumission_fcfa": null,
  "cout_acquisition_dossier_fcfa": null,
  "source_financement": "ex: Budget de l'Etat ou null",
  "exercice_budgetaire": "ex: 2026 ou null",
  "date_limite_depot": "JJ/MM/AAAA ou null",
  "heure_limite_depot": "ex: 09:00 TU ou null",
  "delai_execution_jours": null,
  "delai_validite_offres_jours": null,
  "lieu_depot_offres": "ex: Secrétariat... ou null",
  "date_heure_ouverture_plis": "ex: 27/11/2026 à 09:00 TU ou null",
  "lieu_ouverture_plis": "ex: Salle de réunion... ou null",
  "marche_reserve": "ex: PME ou null",
  "qualifications_ou_agrement": "ex: Agrément technique ou null",
  "contacts_renseignements": "ex: BP, Tel ou null",
  "signataire_nom_fonction": "ex: Le Président de la commission ou null",
  "remarque": null
}"""

db_lock = threading.Lock()

def extraire_avec_llm(md_content: str, model_name: str) -> dict:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Avis à extraire :\n\n{md_content}"}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 2048,
        "temperature": 0.1
    }
    
    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        raw_text = data["choices"][0]["message"]["content"]
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.MULTILINE)
        raw_text = re.sub(r"```$", "", raw_text.strip(), flags=re.MULTILINE)
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(0)
        return json.loads(raw_text)

def extraire_annonce_robuste(md_path: Path) -> dict:
    md_text = md_path.read_text(encoding="utf-8")
    models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS
    last_err = None
    for m in models_to_try:
        for attempt in range(2):
            try:
                res = extraire_avec_llm(md_text, m)
                res["_modele_utilise"] = m
                return res
            except Exception as e:
                last_err = e
                time.sleep(2)
                continue
    raise RuntimeError(f"Échec après repli multi-modèles sur {md_path.name}: {last_err}")

def sauvegarder_en_base(annonce_id: str, source_path: Path, data: dict):
    with db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=60)
        c = conn.cursor()
        
        # Déterminer ou valider le secteur d'activité selon les règles métier
        sector_val = data.get("secteur_activite")
        if not sector_val or sector_val.strip() == "" or sector_val.lower() == "null":
            sector_val = classify_sector(
                objet=data.get("objet_marche"),
                categorie=data.get("categorie_marche"),
                autorite=data.get("autorite_contractante")
            )
        data["secteur_activite"] = sector_val

        # Insertion annonce principale
        c.execute("""
        INSERT OR REPLACE INTO annonces_avis (
            id, source_file, numero_bulletin, date_parution, pages,
            categorie_marche, type_procedure, reference_dossier, autorite_contractante,
            ministere_tutelle, objet_marche, allotissement_type, nombre_lots,
            budget_previsionnel_fcfa, garantie_soumission_fcfa, cout_acquisition_dossier_fcfa,
            source_financement, exercice_budgetaire, date_limite_depot, heure_limite_depot,
            delai_execution_jours, delai_validite_offres_jours, lieu_depot_offres,
            date_heure_ouverture_plis, lieu_ouverture_plis, marche_reserve,
            qualifications_ou_agrement, contacts_renseignements, signataire_nom_fonction,
            remarque, secteur_activite, json_brut
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """, (
            annonce_id,
            str(source_path),
            data.get("numero_bulletin"),
            data.get("date_parution"),
            data.get("pages"),
            data.get("categorie_marche"),
            data.get("type_procedure"),
            data.get("reference_dossier"),
            data.get("autorite_contractante"),
            data.get("ministere_tutelle"),
            data.get("objet_marche"),
            data.get("allotissement_type"),
            data.get("nombre_lots"),
            data.get("budget_previsionnel_fcfa"),
            data.get("garantie_soumission_fcfa"),
            data.get("cout_acquisition_dossier_fcfa"),
            data.get("source_financement"),
            str(data.get("exercice_budgetaire")) if data.get("exercice_budgetaire") else None,
            data.get("date_limite_depot"),
            data.get("heure_limite_depot"),
            data.get("delai_execution_jours"),
            data.get("delai_validite_offres_jours"),
            data.get("lieu_depot_offres"),
            data.get("date_heure_ouverture_plis"),
            data.get("lieu_ouverture_plis"),
            data.get("marche_reserve"),
            data.get("qualifications_ou_agrement"),
            data.get("contacts_renseignements"),
            data.get("signataire_nom_fonction"),
            data.get("remarque"),
            sector_val,
            json.dumps(data, ensure_ascii=False)
        ))

        # Suppression anciens lots si mise à jour
        c.execute("DELETE FROM detail_lots WHERE annonce_id = ?", (annonce_id,))
        
        # Insertion des lots multiples
        lots = data.get("detail_lots", [])
        if isinstance(lots, list):
            for lot in lots:
                if isinstance(lot, dict):
                    c.execute("""
                    INSERT INTO detail_lots (annonce_id, numero_lot, titre, description, montant_fcfa, caution_fcfa)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        annonce_id,
                        lot.get("numero_lot"),
                        lot.get("titre"),
                        lot.get("description"),
                        lot.get("montant_fcfa"),
                        lot.get("caution_fcfa")
                    ))
        conn.commit()
        conn.close()

def traiter_fichier_worker(aid: str, p: Path):
    try:
        time.sleep(0.4)  # Rythme régulier pour éviter tout pic de TPM
        extracted = extraire_annonce_robuste(p)
        sauvegarder_en_base(aid, p, extracted)
        return (True, aid, p, extracted, None)
    except Exception as e:
        return (False, aid, p, None, str(e))

def collecter_fichiers_cibles():
    base_oct = Path("telechargements_pdf_classes/2026/10")
    base_nov = Path("telechargements_pdf_classes/2026/11")
    
    all_files = []
    for base in [base_oct, base_nov]:
        if base.exists():
            for p in base.rglob("*.md"):
                if p.name.startswith("_"):
                    continue
                if "02_sections" in str(p) or "01_pages" in str(p):
                    continue
                if p.stat().st_size > 15000:
                    continue
                if "03_avis" not in str(p):
                    continue
                all_files.append(p)
    return all_files

def main():
    print("=" * 75)
    print(" EXTRACTION DE MASSE & ALIMENTATION SQLITE (1er Octobre -> Aujourd'hui)")
    print("=" * 75)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM annonces_avis;")
    deja_faits = set(row[0] for row in c.fetchall())
    conn.close()
    
    all_files = collecter_fichiers_cibles()
    print(f"Total fichiers .md unitaires identifiés : {len(all_files)}")
    print(f"Déjà enregistrées en base : {len(deja_faits)}")

    # Dédoublonnage par ID unique
    a_traiter_dict = {}
    for p in all_files:
        lines = p.read_text(encoding="utf-8").splitlines()[:10]
        aid = None
        for ln in lines:
            if ln.startswith("id:"):
                aid = ln.split(":", 1)[1].strip().replace('"', '').replace("'", "")
                break
        if not aid:
            aid = p.stem
        if aid not in deja_faits and aid not in a_traiter_dict:
            a_traiter_dict[aid] = p

    a_traiter = list(a_traiter_dict.items())
    total_uniques = len(deja_faits) + len(a_traiter)
    print(f"Total annonces uniques dans le corpus : {total_uniques}")
    print(f"Restantes à extraire : {len(a_traiter)}")
    
    if not a_traiter:
        print("[OK] Toutes les annonces de la période sont déjà en base !")
        return

    MAX_WORKERS = 2
    succes = 0
    erreurs = 0
    t0 = time.time()

    print(f"\nDémarrage du pool d'extraction (parallélisme={MAX_WORKERS})...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(traiter_fichier_worker, aid, p): (aid, p) for aid, p in a_traiter}
        
        for i, future in enumerate(as_completed(futures), 1):
            ok, aid, p, data, err = future.result()
            if ok:
                succes += 1
                budget = data.get("budget_previsionnel_fcfa")
                budget_str = f"{budget:,} FCFA".replace(",", " ") if budget else "Non précisé"
                autorite = (data.get("autorite_contractante") or "Inconnue")[:32]
                modele = data.get("_modele_utilise", "auto")
                print(f"[{i}/{len(a_traiter)}] [OK] {aid} | {autorite} | {budget_str} ({modele})", flush=True)
            else:
                erreurs += 1
                print(f"[{i}/{len(a_traiter)}] [FAIL] {aid} : {err}", flush=True)

    dt = round(time.time() - t0, 2)
    print("\n" + "=" * 75)
    print(f" BILAN FINAL DE L'EXTRACTION")
    print(f" Succès insérés en base : {succes}")
    print(f" Échecs                 : {erreurs}")
    print(f" Temps total            : {dt} s (moyenne {round(dt/max(1, len(a_traiter)), 2)} s/avis)")
    print(f" Base SQLite mise à jour: {DB_PATH.resolve()}")
    print("=" * 75)

if __name__ == "__main__":
    main()
