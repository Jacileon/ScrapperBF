#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_sample_5.py
===================
Script d'extraction structurée basée sur les règles officielles (extraction_rules_reference.md)
via FreeLLMAPI en mode JSON strict pour 5 annonces issues de 5 bulletins distincts.
"""

import os
import json
import time
import urllib.request
from pathlib import Path

API_KEY = "freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8"
BASE_URL = "http://127.0.0.1:3001/v1/chat/completions"
MODEL = "qwen3.8-27b"  # Rapide (0.3s) et 100% conforme JSON strict, bascule sur auto si besoin

SYSTEM_PROMPT = """Tu es un expert analyste de la commande publique au Burkina Faso (DGCMEF).
Ta mission est d'extraire les informations clés d'un avis d'appel d'offres en te conformant STRICTEMENT aux 29 règles et mots-clés ci-dessous :

RÈGLES D'OR :
1. Ne JAMAIS inventer, déduire ou extrapoler. Si une information n'apparaît pas formellement dans le texte, mets STRICTEMENT null (qui vaut None).
2. Montants financiers : UNIQUEMENT des entiers numériques purs en FCFA (sans devise, ex: 18923644).
3. Dates : format JJ/MM/AAAA. Heures : format HH:MM TU.
4. Champ 'remarque' (OBLIGATOIRE) :
   - null : annonce claire et complète sans anomalie.
   - "a verifier" : doute sur une date/montant ou texte tronqué.
   - "plusieurs valeurs non dispo" : dates ou montants manquants.
   - "double annonce sur la meme page" : deux avis différents détectés.
   - "presence de metadonnees tableau" : présence de fragments de tableaux complexes.
   - Ou toute observation pertinente non couverte par les autres champs.

SCHÉMA JSON STRICT À RETOURNER :
{
  "numero_bulletin": "ex: Quotidien N°4359",
  "date_parution": "ex: Mercredi 18 mars 2026",
  "pages": "ex: p. 85",
  "categorie_marche": "Travaux | Fournitures et Services courants | Prestations intellectuelles | null",
  "secteur_activite": "BTP, Génie Civil & Construction | Santé, Médical & Pharmacie | Informatique & Télécoms | Eau, Forages & Assainissement | ...",
  "type_procedure": "Demande de prix | Appel d’offres ouvert | Manifestation d’intérêt | null",
  "reference_dossier": "ex: N° 2026-16/MS/SG/... ou null",
  "autorite_contractante": "Entité émettrice complète (Tutelle + Structure rattachée) ou null",
  "ministere_tutelle": "ex: Ministère de la Santé ou null",
  "objet_marche": "Libellé fidèle de l'objet",
  "allotissement_type": "Lot unique | Lots multiples | null",
  "nombre_lots": 1,
  "detail_lots": [
    {"numero_lot": "Lot 1", "titre": "...", "description": "...", "montant_fcfa": null, "caution_fcfa": null}
  ],
  "budget_previsionnel_fcfa": null,
  "garantie_soumission_fcfa": null,
  "cout_acquisition_dossier_fcfa": null,
  "source_financement": "ex: Budget de l'Etat, Budget communal, Fonds propres, etc. ou null",
  "exercice_budgetaire": "ex: 2026 ou null",
  "date_limite_depot": "JJ/MM/AAAA ou null",
  "heure_limite_depot": "ex: 09:00 TU ou null",
  "delai_execution_jours": null,
  "delai_validite_offres_jours": null,
  "lieu_depot_offres": "ex: Secrétariat de la Direction... ou null",
  "date_heure_ouverture_plis": "ex: 27/03/2026 à 09:00 TU ou null",
  "lieu_ouverture_plis": "ex: Salle de réunion... ou null",
  "marche_reserve": "ex: Réservé aux PME / moyennes entreprises ou null",
  "qualifications_ou_agrement": "ex: Agrément technique BTP catégorie B ou null",
  "contacts_renseignements": "ex: BP, Tel, Email ou null",
  "signataire_nom_fonction": "ex: Le Président de la commission / Nom ou null",
  "remarque": null
}
"""

def extraire_annonce(md_content: str, model_name: str = MODEL) -> dict:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Voici l'annonce découpée à analyser et extraire :\n\n{md_content}"}
        ],
        "response_format": {"type": "json_object"}
    }
    
    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

def main():
    with open("scratch/lot_5_annonces_test.json", "r", encoding="utf-8") as f:
        annonces_paths = json.load(f)

    print(f"Lancement de l'extraction sur {len(annonces_paths)} annonces de référence...")
    extractions = []
    
    for i, a_path in enumerate(annonces_paths, 1):
        p = Path(a_path)
        print(f"\n[{i}/{len(annonces_paths)}] Traitement de : {p.name}")
        md_text = p.read_text(encoding="utf-8")
        
        t0 = time.time()
        try:
            result = extraire_annonce(md_text, model_name="qwen3.8-27b")
            dt = round(time.time() - t0, 2)
            print(f"  [OK] Extraction réussie en {dt}s")
            print(f"       Autorité  : {result.get('autorite_contractante')}")
            print(f"       Objet     : {result.get('objet_marche')[:60]}...")
            print(f"       Budget    : {result.get('budget_previsionnel_fcfa')} FCFA")
            print(f"       Garantie  : {result.get('garantie_soumission_fcfa')} FCFA")
            print(f"       Dépôt     : {result.get('date_limite_depot')} à {result.get('heure_limite_depot')}")
            print(f"       Remarque  : {result.get('remarque')}")
            result["_source_file"] = str(p)
            extractions.append(result)
        except Exception as e:
            print(f"  [Tentative repli auto] Échec avec qwen3.8-27b: {e}")
            try:
                result = extraire_annonce(md_text, model_name="auto")
                dt = round(time.time() - t0, 2)
                print(f"  [OK] Repli réussi en {dt}s")
                result["_source_file"] = str(p)
                extractions.append(result)
            except Exception as e2:
                print(f"  [ERREUR FINALE] : {e2}")

    out_file = Path("scratch/resultats_extraction_5_annonces.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(extractions, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"Résultats complets sauvegardés dans : {out_file}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
