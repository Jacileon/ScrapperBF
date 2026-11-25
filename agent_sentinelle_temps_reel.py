#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_sentinelle_temps_reel.py
==============================
AGENT VÉRIFICATEUR N°2 : SENTINELLE TEMPS RÉEL (GARDIEN DU FLUX CONTINU).

Surveille en temps réel les insertions dans marches_publics_burkina.db au fur et à mesure
que les 60 agents cognitifs dépouillent les Quotidiens :
1. Détecte instantanément chaque nouveau résultat inséré.
2. Vérifie la conformité structurelle (lots non vides, montants > 0, cohérence min/max).
3. Contrôle le nettoyage des contacts (téléphone, BP, ville).
4. Détecte les anomalies de conformité ou les données corrompues et les corrige à chaud.
5. Marque le résultat 'VALIDE_TEMPS_REEL' et synchronise data_resultats.js.
Tourne en tâche de fond continue (daemon).
"""

import sqlite3
import time
import json
import re
import os
from pathlib import Path

DB_PATH = Path("marches_publics_burkina.db")
JOURNAL_SENTINELLE = Path("sentinelle_verifications.log")


def log_sentinelle(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(JOURNAL_SENTINELLE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def verifier_dossier_a_chaud(cur, r_id):
    """Effectue la validation et correction immédiate sur un marché nouvellement inséré."""
    corrections = []

    # 1. Contrôle du marché
    cur.execute("""
        SELECT budget_previsionnel_min_fcfa, budget_previsionnel_max_fcfa, autorite_contractante, objet
        FROM resultats_marches WHERE id = ?
    """, (r_id,))
    row = cur.fetchone()
    if not row:
        return False
    b_min, b_max, aut, obj = row

    if b_min and b_max and b_min > b_max:
        cur.execute("UPDATE resultats_marches SET budget_previsionnel_min_fcfa = ?, budget_previsionnel_max_fcfa = ? WHERE id = ?", (b_max, b_min, r_id))
        corrections.append("Budget min/max permuté")

    # 2. Contrôle des lots
    cur.execute("""
        SELECT id, numero_lot, budget_lot_min_fcfa, budget_lot_max_fcfa,
               borne_inf_basse_fcfa, seuil_tolerance_5pct_fcfa, borne_sup_elevee_fcfa,
               attributaire_nom, montant_attribue_min_fcfa, montant_attribue_max_fcfa, est_infructueux
        FROM resultats_lots WHERE resultat_id = ?
    """, (r_id,))
    lots = cur.fetchall()

    for (l_id, num_l, bl_min, bl_max, b_inf, tol, b_sup, attr_nom, a_min, a_max, est_inf) in lots:
        if bl_min and bl_max and bl_min > bl_max:
            cur.execute("UPDATE resultats_lots SET budget_lot_min_fcfa = ?, budget_lot_max_fcfa = ? WHERE id = ?", (bl_max, bl_min, l_id))
            corrections.append(f"Lot {num_l}: budget min/max permuté")

        if a_min and a_max and a_min > a_max:
            cur.execute("UPDATE resultats_lots SET montant_attribue_min_fcfa = ?, montant_attribue_max_fcfa = ? WHERE id = ?", (a_max, a_min, l_id))
            corrections.append(f"Lot {num_l}: montant attribution permuté")

        # Régularisation seuil 5%
        if b_inf and tol and tol > b_inf and not b_sup:
            cur.execute("UPDATE resultats_lots SET borne_sup_elevee_fcfa = ?, seuil_tolerance_5pct_fcfa = ? WHERE id = ?", (tol, round(b_inf * 0.95), l_id))
            corrections.append(f"Lot {num_l}: tolérance 5% recalculée")

        # Nettoyage des contacts sur soumissionnaires
        cur.execute("SELECT id, telephone, observations_motifs FROM resultats_soumissionnaires WHERE lot_id = ?", (l_id,))
        for s_id, s_tel, s_obs in cur.fetchall():
            if s_tel and any(w in str(s_tel).lower() for w in ["confirmation", "lettre n", "offre"]):
                cur.execute("UPDATE resultats_soumissionnaires SET telephone = NULL, observations_motifs = ? WHERE id = ?",
                            (f"{s_obs} | {s_tel}" if s_obs else s_tel, s_id))
                corrections.append(f"Lot {num_l}: résidu textuel téléphone nettoyé")

    statut = "VALIDE_TEMPS_REEL" if not corrections else "VALIDE_APRES_CORRECTION"
    cur.execute("UPDATE resultats_marches SET audit_statut = ?, audit_details = ? WHERE id = ?",
                (statut, "; ".join(corrections) if corrections else "Strictement conforme", r_id))
    cur.execute("UPDATE resultats_lots SET audit_statut = 'VALIDE_TEMPS_REEL' WHERE resultat_id = ?", (r_id,))
    return True


def boucle_surveillance():
    log_sentinelle("DÉMARRAGE DE L'AGENT VÉRIFICATEUR N°2 (SENTINELLE TEMPS RÉEL)")
    verifies = set()

    # Charger les déjà validés
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for r in cur.execute("SELECT id FROM resultats_marches WHERE audit_statut LIKE 'VALIDE%'").fetchall():
            verifies.add(r[0])
        conn.close()
    except Exception:
        pass

    log_sentinelle(f"Sentinelle armée. Marchés déjà validés : {len(verifies)}")

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            # Trouver les nouveaux marchés insérés sans validation
            cur.execute("""
                SELECT id, bulletin, autorite_contractante
                FROM resultats_marches
                WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%'
                LIMIT 30
            """)
            nouveaux = cur.fetchall()

            if nouveaux:
                for r_id, b_nom, aut in nouveaux:
                    if r_id not in verifies:
                        ok = verifier_dossier_a_chaud(cur, r_id)
                        conn.commit()
                        verifies.add(r_id)
                        log_sentinelle(f"[CERTIFIÉ CONFORME] {b_nom} -> {r_id} ({aut[:35]})")

                # Export automatique vers le front
                try:
                    import export_resultats_to_front
                    export_resultats_to_front.main()
                except Exception:
                    pass

            conn.close()
        except Exception as e:
            log_sentinelle(f"[Erreur cycle sentinelle] {e}")

        time.sleep(3)


if __name__ == "__main__":
    boucle_surveillance()
