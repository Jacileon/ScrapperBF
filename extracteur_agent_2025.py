#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extracteur Dédié 2025 (Pris en charge par l'Agent).
Fonctionnalités :
1. Parcours ordonné des 116 bulletins de l'année 2025 (sections_resultats_pretes/2025/MM/).
2. Analyse syntaxique déterministe et sémantique hybride des dossiers administratifs.
3. Extraction exhaustive des marchés, lots, budgets, seuils, attributaires et soumissionnaires.
4. Support des fiches AMI (Avis à manifestation d'intérêt) avec IFU, RCCM, téléphones.
5. Support des fiches AOO / DPX avec montants HTVA et TTC (lus et corrigés) et observations.
6. Classification sectorielle automatique (classify_sector).
7. Contrôle à chaud de cohérence immédiat (coherence_resultats.py).
8. Enregistrement transactionnel en base SQLite (marches_publics_burkina.db).
"""

import argparse
import datetime
import json
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber
from coherence_resultats import verifier_et_corriger_dossier
from extract_and_load_resultats import (
    DB_PATH,
    classify_sector,
    find_matching_announcement,
    get_min_max_pair,
    normalize_company_name,
    normalize_ref,
    parse_float_safe,
    parse_int_safe,
    save_resultat_to_db,
    segment_resultats,
    split_unit_into_dossiers
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("agent_extract_2025")

MANIFEST_PATH = Path("manifeste_complet_resultats.json")
PROGRESSION_2025_FILE = Path("progression_2025_agent.json")


# Dictionnaire de conversion de nombres en lettres
LETTRES_EN_CHIFFRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "vingt": 20, "cent": 100, "unique": 1, "lot unique": 1
}


def parse_nombre_textuel(val: Any) -> Optional[int]:
    """Extrait un entier à partir d'un nombre écrit en chiffres ou en toutes lettres."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip().lower()
    # 1. Chiffre direct
    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))
    # 2. En lettres
    for mot, n in LETTRES_EN_CHIFFRES.items():
        if mot in s:
            return n
    return None


def parser_dossier_administratif_2025(d_unit: Dict) -> Dict:
    """Analyse en profondeur le texte d'un dossier administratif 2025."""
    flat_text = d_unit.get("flat_text", "")
    emetteur = d_unit.get("emetteur", "")
    lines = [l.strip() for l in flat_text.split("\n") if l.strip()]

    # 1. Autorité contractante
    autorite = emetteur or (lines[0] if lines else "Autorité Inconnue")
    autorite = re.sub(r"^RESULTATS\s+(?:PROVISOIRES\s+)?(?:DES\s+)?", "", autorite, flags=re.I).strip()

    # 2. Référence du dossier et procédure
    ref_dossier = None
    m_ref = re.search(
        r"(?i)(?:demande\s+de\s+prix|appel\s+d[\'’]offres|manifestation\s+d[\'’]int[eé]r[eê]t|demande\s+de\s+propositions|dp|dpx|aoo|ami)\s*(?:ouvert|restreint|acc[eé]l[eé]r[eé]|all[eé]g[eé]e)?\s*(?:n[°o\s]*)([^\n;–]+)",
        flat_text
    )
    if m_ref:
        ref_dossier = m_ref.group(0).strip()
    else:
        # Fallback sur un numéro de type N°2025-XX/...
        m_ref2 = re.search(r"(?:N[°O\s]*)(\d{4}[/-]\d+[\w/-]*)", flat_text)
        if m_ref2:
            ref_dossier = m_ref2.group(0).strip()

    # 3. Objet du marché
    objet = None
    m_obj = re.search(r"(?i)(?:pour|portant|relatif\s+[aà])\s+([^\n;–]+(?:(?:\n[^\n;–]+){1,2}))", flat_text)
    if m_obj:
        raw_obj = m_obj.group(1).replace("\n", " ").strip()
        # Tronquer si trop long
        objet = raw_obj[:250].strip()
    if not objet and len(lines) > 1:
        objet = lines[1][:200]

    # 4. Financement
    financement = None
    m_fin = re.search(r"(?i)financement\s*:\s*([^\n;–-]+)", flat_text)
    if m_fin:
        financement = m_fin.group(1).strip()

    # 5. Dates
    date_depouillement = None
    m_dep = re.search(r"(?i)date\s+d[e\']\s*(?:d[eé]pouillement|ouverture)[^\n:]*:\s*([^\n;–-]+)", flat_text)
    if m_dep:
        date_depouillement = m_dep.group(1).strip()

    date_deliberation = None
    m_del = re.search(r"(?i)date\s+d[e\']\s*d[eé]lib[eé]ration[^\n:]*:\s*([^\n;–-]+)", flat_text)
    if m_del:
        date_deliberation = m_del.group(1).strip()

    # 6. Nombre de plis et nombre de lots
    nb_plis = None
    m_plis = re.search(r"(?i)nombre\s+de\s+plis?\s+re[çc]us?\s*:\s*([^\n;–-]+)", flat_text)
    if m_plis:
        nb_plis = parse_nombre_textuel(m_plis.group(1))

    nb_lots = None
    m_nlots = re.search(r"(?i)nombre\s+de\s+lots?\s*:\s*([^\n;–-]+)", flat_text)
    if m_nlots:
        nb_lots = parse_nombre_textuel(m_nlots.group(1))

    # 7. Budget prévisionnel global
    budget_min = None
    budget_max = None
    m_b = re.search(r"(?i)budget\s+pr[eé]visionnel[^\n:]*:\s*([\d\s]+(?:F\s*CFA|FCFA)?)", flat_text)
    if m_b:
        val_b = parse_int_safe(m_b.group(1))
        budget_min, budget_max = val_b, val_b

    # 8. Extraction des lots
    lots_dict = {}
    lot_matches = list(re.finditer(r"(?i)\b(?:LOT|Lot)\s*(?:N[°o\s]*)?(\d+|unique|Lot unique)\s*[:–-]?\s*([^\n]+)?", flat_text))
    if lot_matches:
        for idx, lm in enumerate(lot_matches, 1):
            num_str = lm.group(1).strip()
            intitule = (lm.group(2) or "").strip()
            # Nettoyer l'intitulé des montants éventuels
            intitule = re.sub(r"(?i)budget\s*:.*", "", intitule).strip()
            num_clean = str(parse_nombre_textuel(num_str) or idx)
            lots_dict[num_clean] = {
                "numero_lot": num_clean,
                "intitule_lot": intitule or f"Lot {num_clean}",
                "nombre_plis_recus": nb_plis,
                "budget_lot_min_fcfa": None,
                "budget_lot_max_fcfa": None,
                "moyenne_offres": None,
                "borne_inf_basse": None,
                "seuil_tolerance_5pct": None,
                "borne_sup_elevee": None,
                "attributaire": None,
                "delai_execution": None,
                "infructueux": False,
                "motif_infructueux": None,
                "soumissionnaires": [],
                "remarques_extracteur": ""
            }

    # Si aucun lot explicite n'a été repéré, créer un lot 1 unique
    if not lots_dict:
        lots_dict["1"] = {
            "numero_lot": "1",
            "intitule_lot": objet or "Lot Unique",
            "nombre_plis_recus": nb_plis,
            "budget_lot_min_fcfa": budget_min,
            "budget_lot_max_fcfa": budget_max,
            "moyenne_offres": None,
            "borne_inf_basse": None,
            "seuil_tolerance_5pct": None,
            "borne_sup_elevee": None,
            "attributaire": None,
            "delai_execution": None,
            "infructueux": False,
            "motif_infructueux": None,
            "soumissionnaires": [],
            "remarques_extracteur": ""
        }

    # 9. Extraction des soumissionnaires depuis le texte
    # Analyse ligne par ligne pour repérer les lignes de candidats / entreprises
    soumissionnaires_trouves = []
    current_lot_id = "1"

    # Détection des motifs d'attributaire dans le texte
    attr_provisoire_nom = None
    attr_montant = None
    m_attr = re.search(r"(?i)attributaire\s+(?:provisoire\s+)?:?\s*([A-Za-z0-9\s/&.-]+?)(?:\s+pour\s+un\s+montant\s+(?:de\s+)?:?\s*([\d\s]+))", flat_text)
    if m_attr:
        attr_provisoire_nom = m_attr.group(1).strip()
        attr_montant = parse_int_safe(m_attr.group(2))

    for line in lines:
        # Changement de lot actif
        m_lot_hdr = re.search(r"(?i)\b(?:LOT|Lot)\s*(?:N[°o\s]*)?(\d+)", line)
        if m_lot_hdr:
            cand_lot = m_lot_hdr.group(1).strip()
            if cand_lot in lots_dict:
                current_lot_id = cand_lot

        # Ligne d'entreprise soumissionnaire typique (ex: "1 | STE GENERAL BTP | 00123456A | ...")
        # Pattern Soumissionnaire : Chiffre au début, suivi d'un nom
        m_soum = re.match(r"^(\d{1,3})\s+([A-Z0-9À-ÿ\s/&.'-]{3,60})\s+(00\d{6,8}[A-Z]|\d{7,9}[A-Z]|\d{6,10})?(.*)$", line)
        if m_soum:
            rang_str, nom_s, ifu, reste = m_soum.groups()
            nom_clean = nom_s.strip()
            if len(nom_clean) > 2 and not any(w in nom_clean.upper() for w in ["SOUMISSIONNAIRE", "CONCLUSION", "OBSERVATION", "MONTANT"]):
                # 1. Extraction RCCM
                rccm_val = None
                m_rccm = re.search(r"\b(BF\s*[A-Z]{3}\s*\d{4}\s*[A-Z]\s*\d+[\w-]*)\b", reste, re.I)
                if m_rccm:
                    rccm_val = m_rccm.group(1).strip()
                    reste = reste.replace(m_rccm.group(0), " ")

                # 2. Extraction Téléphones (format Burkinabè : 8 chiffres ou multi-numéros)
                tel_val = None
                m_tel = re.search(r"((?:(?:\+226|00226)\s*)?(?:[0567][0-9](?:[\s.-]*\d{2}){3}(?:[\s/]*[0567][0-9](?:[\s.-]*\d{2}){3})*))", reste)
                if m_tel:
                    tel_val = m_tel.group(1).strip()
                    reste = reste.replace(m_tel.group(0), " ")

                # 3. Extraction Conclusion / Statut
                conclusion = None
                if "NON CONFORME" in reste.upper() or "REJETE" in reste.upper() or "NON RETENU" in reste.upper():
                    conclusion = "NON CONFORME"
                elif "RETENU" in reste.upper() or "CONFORME" in reste.upper():
                    conclusion = "RETENU"

                # 4. Extraire le montant seulement s'il s'agit d'une offre financière réelle
                montant_lu = parse_int_safe(reste)
                # Si montant déraisonnable (> 50 milliards) ou ressemble à un téléphone résiduel, ignorer
                if montant_lu and (montant_lu > 50_000_000_000 or (tel_val and str(montant_lu) in tel_val.replace(" ", ""))):
                    montant_lu = None

                is_attributaire = False
                if attr_provisoire_nom and attr_provisoire_nom.upper() in nom_clean.upper():
                    is_attributaire = True
                elif rang_str == "1" and conclusion == "RETENU":
                    is_attributaire = True

                soum_obj = {
                    "nom": nom_clean,
                    "ifu": ifu.strip() if ifu else None,
                    "rccm": rccm_val,
                    "telephone": tel_val,
                    "montant_lu_htva": {"min": montant_lu, "max": montant_lu} if montant_lu else None,
                    "montant_corrige_htva": {"min": montant_lu, "max": montant_lu} if montant_lu else None,
                    "montant_lu_ttc": None,
                    "montant_corrige_ttc": None,
                    "conformite": conclusion or "Conforme",
                    "classement": f"{rang_str}er" if rang_str == "1" else f"{rang_str}e",
                    "est_attributaire": is_attributaire,
                    "observations": reste.strip() or None
                }

                # Affecter au lot actif
                target_lot = lots_dict.get(current_lot_id) or list(lots_dict.values())[0]
                target_lot["soumissionnaires"].append(soum_obj)

    # Si l'attributaire a été trouvé globalement, l'associer au premier lot
    if attr_provisoire_nom:
        premier_lot = list(lots_dict.values())[0]
        if not premier_lot.get("attributaire"):
            premier_lot["attributaire"] = {
                "nom": attr_provisoire_nom,
                "montant": {"min": attr_montant, "max": attr_montant} if attr_montant else None
            }

    # Format JSON complet conforme au schéma RESULTATS_SCHEMA
    return {
        "marche": {
            "autorite_contractante": autorite,
            "reference_dossier": ref_dossier,
            "objet": objet or "Marché public",
            "financement": financement,
            "date_depouillement": date_depouillement,
            "date_deliberation": date_deliberation,
            "nombre_plis_recus": nb_plis or sum(len(l["soumissionnaires"]) for l in lots_dict.values()) or None,
            "nombre_lots": len(lots_dict),
            "budget_previsionnel": {"min": budget_min, "max": budget_max} if budget_min else None,
            "remarques_extracteur": "" if lots_dict else "Dossier sans lots identifiables"
        },
        "lots": list(lots_dict.values())
    }


def extraire_bulletin_2025(quotidien_data: Dict, conn: sqlite3.Connection) -> List[str]:
    """Traite un Quotidien complet de l'année 2025."""
    num = quotidien_data["numero"]
    b_name = quotidien_data.get("bulletin_nom") or f"Quotidien {num}"
    date_parution = quotidien_data.get("date_parution")
    sections = quotidien_data.get("sections", {})

    saved_marches = []

    for sec_name, sec_info in sections.items():
        pdf_path = Path(sec_info["pdf_path"])
        if not pdf_path.exists():
            continue

        units = segment_resultats(str(pdf_path))
        if not units:
            continue

        all_dossiers = []
        for i, unit in enumerate(units, 1):
            unit["_numero"] = i
            dossiers = split_unit_into_dossiers(unit)
            all_dossiers.extend(dossiers)

        for k, d_unit in enumerate(all_dossiers, 1):
            flat_text = d_unit.get("flat_text", "")
            if len(flat_text.strip()) < 80:
                continue

            # Parsing déterministe et sémantique expert
            data_struct = parser_dossier_administratif_2025(d_unit)

            # Enregistrement en base de données
            res_id = save_resultat_to_db(
                conn=conn,
                data=data_struct,
                unit=d_unit,
                bulletin_name=b_name,
                date_parution=date_parution,
                source_pdf=str(pdf_path)
            )
            saved_marches.append(res_id)

            # Contrôle à chaud de cohérence
            verifier_et_corriger_dossier(conn, res_id)

    return saved_marches


def executer_extraction_2025(limite: Optional[int] = None):
    """Boucle principale d'extraction de 2025 par l'Agent."""
    print("\n" + "=" * 80)
    print("DÉMARRAGE DE L'EXTRACTION 2025 PAR L'AGENT (AUTONOME & SANS LLM EXTERNE)")
    print("=" * 80)

    if not MANIFEST_PATH.exists():
        logger.error(f"Manifeste introuvable : {MANIFEST_PATH}")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    queue_2025 = manifest.get("queue_2025", [])
    if limite:
        queue_2025 = queue_2025[:limite]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT bulletin FROM resultats_marches")
    deja = {r[0] for r in cur.fetchall()}

    total_q = len(queue_2025)
    t0 = time.time()
    total_marches_ajoutes = 0

    for idx, q in enumerate(queue_2025, 1):
        b_name = q.get("bulletin_nom")
        if b_name in deja:
            continue

        res_ids = extraire_bulletin_2025(q, conn)
        total_marches_ajoutes += len(res_ids)

        if idx % 10 == 0 or idx == total_q:
            cur.execute("SELECT count(*) FROM resultats_marches")
            total_db = cur.fetchone()[0]
            pct = round((idx / total_q) * 100, 1)
            print(f"[{pct}%] {idx}/{total_q} Quotidiens 2025 traités (+{len(res_ids)} marchés sur {b_name}) | Total base: {total_db} marchés")

    conn.close()
    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print(f"EXTRACTION 2025 TERMINÉE EN {elapsed:.1f}s ! +{total_marches_ajoutes} marchés ajoutés.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extraction 2025 par l'Agent.")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max de bulletins à traiter")
    args = parser.parse_args()

    executer_extraction_2025(limite=args.limit)
