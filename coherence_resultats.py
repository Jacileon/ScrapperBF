#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de vérification à chaud et audit de cohérence des RÉSULTATS.
Effectue les contrôles réglementaires et arithmétiques :
1. Cohérence Min <= Max (budgets, seuils, offres lues et corrigées).
2. Seuil de tolérance légale 5% (calcul ou inversion d'en-tête).
3. Détection et journalisation des alertes d'incertitude remontées par l'extracteur.
4. Attribution du statut de cohérence ('VALIDE', 'ALERTE_INCERTITUDE', 'A_VERIFIER').
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("coherence_resultats")
ALERT_LOG_FILE = Path("alertes_extraction.log")


def verifier_et_corriger_dossier(conn: sqlite3.Connection, resultat_id: str) -> Dict:
    """
    Vérifie la cohérence arithmétique et réglementaire d'un dossier de résultat,
    corrige automatiquement les seuils si applicable, et met à jour les statuts en base.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, bulletin, autorite_contractante, reference_dossier,
               budget_previsionnel_min_fcfa, budget_previsionnel_max_fcfa,
               remarques_extracteur
        FROM resultats_marches
        WHERE id = ?
    """, (resultat_id,))
    row_m = cur.fetchone()
    if not row_m:
        return {"id": resultat_id, "statut": "INTROUVABLE", "anomalies": []}

    res_id, bulletin, autorite, ref_dos, b_min, b_max, rem_marche = row_m

    anomalies = []
    alertes = []
    corrections = []

    # 1. Vérification arithmétique du budget prévisionnel
    if b_min is not None and b_max is not None and b_min > b_max:
        anomalies.append(f"Budget marché incohérent: min ({b_min}) > max ({b_max})")

    # Si le marché a une remarque d'incertitude
    if rem_marche and rem_marche.strip():
        alertes.append(f"Marché: {rem_marche.strip()}")

    # 2. Vérification des lots
    cur.execute("""
        SELECT id, numero_lot, budget_lot_min_fcfa, budget_lot_max_fcfa,
               borne_inf_basse_fcfa, seuil_tolerance_5pct_fcfa, borne_sup_elevee_fcfa,
               montant_attribue_min_fcfa, montant_attribue_max_fcfa,
               remarques_extracteur
        FROM resultats_lots
        WHERE resultat_id = ?
    """, (resultat_id,))
    lots = cur.fetchall()

    for lot in lots:
        l_id, num_lot, b_lot_min, b_lot_max, b_inf, tol, b_sup, attr_min, attr_max, rem_lot = lot
        lot_anomalies = []
        lot_alertes = []

        if b_lot_min is not None and b_lot_max is not None and b_lot_min > b_lot_max:
            lot_anomalies.append(f"Lot {num_lot}: budget min ({b_lot_min}) > max ({b_lot_max})")

        if attr_min is not None and attr_max is not None and attr_min > attr_max:
            lot_anomalies.append(f"Lot {num_lot}: montant attribué min ({attr_min}) > max ({attr_max})")

        # Vérification et régularisation du seuil de tolérance 5%
        if b_inf is not None and tol is not None and tol > b_inf:
            # Inversion manifeste des colonnes borne inf / tolérance
            cur.execute("""
                UPDATE resultats_lots
                SET borne_inf_basse_fcfa = ?, seuil_tolerance_5pct_fcfa = ?
                WHERE id = ?
            """, (tol, b_inf, l_id))
            corrections.append(f"Lot {num_lot}: inversion rectifiée entre borne_inf ({b_inf}) et tolérance ({tol})")
            b_inf, tol = tol, b_inf

        elif b_inf is not None and tol is None:
            # Calcul automatique du seuil légal 5%
            tol_calcule = round(b_inf * 0.95)
            cur.execute("""
                UPDATE resultats_lots
                SET seuil_tolerance_5pct_fcfa = ?
                WHERE id = ?
            """, (tol_calcule, l_id))
            corrections.append(f"Lot {num_lot}: seuil de tolérance 5% calculé ({tol_calcule})")

        if b_inf is not None and b_sup is not None and b_inf > b_sup:
            lot_anomalies.append(f"Lot {num_lot}: borne_inf ({b_inf}) > borne_sup ({b_sup})")

        if rem_lot and rem_lot.strip():
            lot_alertes.append(f"Lot {num_lot}: {rem_lot.strip()}")

        # 3. Vérification des soumissionnaires du lot
        cur.execute("""
            SELECT id, nom_soumissionnaire,
                   montant_lu_htva_min, montant_lu_htva_max,
                   montant_lu_ttc_min, montant_lu_ttc_max,
                   montant_corrige_htva_min, montant_corrige_htva_max,
                   montant_corrige_ttc_min, montant_corrige_ttc_max
            FROM resultats_soumissionnaires
            WHERE lot_id = ?
        """, (l_id,))
        soums = cur.fetchall()

        for s in soums:
            s_id, s_nom, l_ht_min, l_ht_max, l_ttc_min, l_ttc_max, c_ht_min, c_ht_max, c_ttc_min, c_ttc_max = s
            if l_ht_min is not None and l_ht_max is not None and l_ht_min > l_ht_max:
                lot_anomalies.append(f"Soumissionnaire {s_nom}: lu HT min > max")
            if l_ttc_min is not None and l_ttc_max is not None and l_ttc_min > l_ttc_max:
                lot_anomalies.append(f"Soumissionnaire {s_nom}: lu TTC min > max")
            if c_ht_min is not None and c_ht_max is not None and c_ht_min > c_ht_max:
                lot_anomalies.append(f"Soumissionnaire {s_nom}: corrigé HT min > max")
            if c_ttc_min is not None and c_ttc_max is not None and c_ttc_min > c_ttc_max:
                lot_anomalies.append(f"Soumissionnaire {s_nom}: corrigé TTC min > max")

        # Mise à jour statut lot
        if lot_anomalies:
            statut_lot = "A_VERIFIER"
        elif lot_alertes:
            statut_lot = "ALERTE_INCERTITUDE"
        else:
            statut_lot = "VALIDE"

        cur.execute("UPDATE resultats_lots SET statut_coherence = ? WHERE id = ?", (statut_lot, l_id))
        anomalies.extend(lot_anomalies)
        alertes.extend(lot_alertes)

    # 4. Statut global du marché
    if anomalies:
        statut_marche = "A_VERIFIER"
    elif alertes:
        statut_marche = "ALERTE_INCERTITUDE"
    else:
        statut_marche = "VALIDE"

    cur.execute("UPDATE resultats_marches SET statut_coherence = ? WHERE id = ?", (statut_marche, resultat_id))
    conn.commit()

    # Si alertes ou anomalies, enregistrer dans le fichier journal des alertes
    if alertes or anomalies:
        with open(ALERT_LOG_FILE, "a", encoding="utf-8") as f:
            for alt in alertes:
                f.write(f"[{bulletin}] [ALERTE] Dossier {resultat_id} ({autorite}): {alt}\n")
            for ano in anomalies:
                f.write(f"[{bulletin}] [ANOMALIE] Dossier {resultat_id} ({autorite}): {ano}\n")

    return {
        "id": resultat_id,
        "bulletin": bulletin,
        "statut": statut_marche,
        "anomalies": anomalies,
        "alertes": alertes,
        "corrections": corrections
    }


def verifier_tous_les_resultats(conn: sqlite3.Connection) -> Dict:
    """Audit global de cohérence sur l'ensemble de la base."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM resultats_marches")
    ids = [r[0] for r in cur.fetchall()]

    stats = {"total": len(ids), "VALIDE": 0, "ALERTE_INCERTITUDE": 0, "A_VERIFIER": 0, "corrections": 0}
    for res_id in ids:
        audit = verifier_et_corriger_dossier(conn, res_id)
        st = audit["statut"]
        stats[st] = stats.get(st, 0) + 1
        stats["corrections"] += len(audit["corrections"])

    return stats


if __name__ == "__main__":
    conn = sqlite3.connect("marches_publics_burkina.db")
    stats = verifier_tous_les_resultats(conn)
    conn.close()
    print("=== RAPPORT D'AUDIT DE COHÉRENCE DES RÉSULTATS ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
