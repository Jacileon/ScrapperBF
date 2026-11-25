#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agents_verificateurs_hybrides.py
================================
DÉPLOIEMENT DE 10 AGENTS VÉRIFICATEURS :
- 5 Agents d'Audit Rétrospectif de la Base (Vérification & Validation).
- 5 Agents Sentinelles en Live (Vérification continue des nouveaux arrivages).
Lorsque l'audit de la base se termine, les 5 agents d'audit basculent automatiquement
en sentinelles live pour former un escadron de 10 vérificateurs en temps réel.
"""

import sqlite3
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

DB_PATH = Path("marches_publics_burkina.db")
db_lock = threading.Lock()
journal_lock = threading.Lock()
JOURNAL_FILE = Path("audit_verification_equipe.log")


def log_verif(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with journal_lock:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def verifier_corriger_marche(m_id):
    """Contrôle strict et redressement automatique d'un marché et de ses lots."""
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, bulletin, autorite_contractante, reference_dossier, objet,
                   budget_previsionnel_min_fcfa, budget_previsionnel_max_fcfa
            FROM resultats_marches WHERE id = ?
        """, (m_id,))
        row_m = cur.fetchone()
        if not row_m:
            conn.close()
            return

        b_min, b_max = row_m[5], row_m[6]
        corrections = []

        if b_min and b_max and b_min > b_max:
            cur.execute("UPDATE resultats_marches SET budget_previsionnel_min_fcfa = ?, budget_previsionnel_max_fcfa = ? WHERE id = ?", (b_max, b_min, m_id))
            corrections.append("Budget min/max permuté")

        cur.execute("""
            SELECT id, numero_lot, budget_lot_min_fcfa, budget_lot_max_fcfa,
                   borne_inf_basse_fcfa, seuil_tolerance_5pct_fcfa, borne_sup_elevee_fcfa,
                   attributaire_nom, montant_attribue_min_fcfa, montant_attribue_max_fcfa
            FROM resultats_lots WHERE resultat_id = ?
        """, (m_id,))
        lots = cur.fetchall()

        for l_id, num_l, bl_min, bl_max, b_inf, tol, b_sup, attr_nom, a_min, a_max in lots:
            if bl_min and bl_max and bl_min > bl_max:
                cur.execute("UPDATE resultats_lots SET budget_lot_min_fcfa = ?, budget_lot_max_fcfa = ? WHERE id = ?", (bl_max, bl_min, l_id))
                corrections.append(f"Lot {num_l}: budget corrigé")

            if a_min and a_max and a_min > a_max:
                cur.execute("UPDATE resultats_lots SET montant_attribue_min_fcfa = ?, montant_attribue_max_fcfa = ? WHERE id = ?", (a_max, a_min, l_id))
                corrections.append(f"Lot {num_l}: attribution corrigée")

            if b_inf and tol and tol > b_inf and not b_sup:
                cur.execute("UPDATE resultats_lots SET borne_sup_elevee_fcfa = ?, seuil_tolerance_5pct_fcfa = ? WHERE id = ?", (tol, round(b_inf * 0.95), l_id))
                corrections.append(f"Lot {num_l}: tolérance 5% recalculée")

            # Nettoyage résidu contact
            cur.execute("SELECT id, telephone, observations_motifs FROM resultats_soumissionnaires WHERE lot_id = ?", (l_id,))
            for s_id, s_tel, s_obs in cur.fetchall():
                if s_tel and any(w in str(s_tel).lower() for w in ["confirmation", "lettre n", "offre", "variation"]):
                    cur.execute("UPDATE resultats_soumissionnaires SET telephone = NULL, observations_motifs = ? WHERE id = ?",
                                (f"{s_obs} | {s_tel}" if s_obs else s_tel, s_id))
                    corrections.append(f"Lot {num_l}: contact nettoyé")

        statut = "VALIDE_CERTIFIE" if not corrections else "VALIDE_APRES_CORRECTION"
        cur.execute("UPDATE resultats_marches SET audit_statut = ?, audit_details = ? WHERE id = ?",
                    (statut, "; ".join(corrections) if corrections else "Strictement conforme", m_id))
        cur.execute("UPDATE resultats_lots SET audit_statut = 'VALIDE_CERTIFIE' WHERE resultat_id = ?", (m_id,))
        conn.commit()
        conn.close()

    return statut, len(corrections)


def worker_audit_base(worker_id):
    """Vérificateur rétroactif sur les données en base."""
    log_verif(f"[Vérificateur Base #{worker_id}] Démarrage audit rétroactif...")
    while True:
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id FROM resultats_marches WHERE audit_statut IS NULL OR audit_statut = 'NON_AUDITE' LIMIT 1")
            row = cur.fetchone()
            if row:
                m_id = row[0]
                cur.execute("UPDATE resultats_marches SET audit_statut = 'EN_COURS' WHERE id = ?", (m_id,))
                conn.commit()
            conn.close()

        if not row:
            log_verif(f"[Vérificateur Base #{worker_id}] Audit rétroactif terminé ! BASCULE IMMÉDIATE EN SENTINELLE LIVE.")
            worker_live_sentinelle(worker_id)
            break

        statut, n_corr = verifier_corriger_marche(m_id)
        log_verif(f"[Vérificateur Base #{worker_id}] Marché {m_id} -> {statut} ({n_corr} corr.)")


def worker_live_sentinelle(worker_id):
    """Sentinelle continue en temps réel."""
    log_verif(f"[Sentinelle Live #{worker_id}] Prise de garde active...")
    while True:
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id FROM resultats_marches WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%' LIMIT 1")
            row = cur.fetchone()
            if row:
                m_id = row[0]
                cur.execute("UPDATE resultats_marches SET audit_statut = 'EN_COURS' WHERE id = ?", (m_id,))
                conn.commit()
            conn.close()

        if row:
            statut, n_corr = verifier_corriger_marche(m_id)
            log_verif(f"[Sentinelle Live #{worker_id}] NOUVEAU MARCHÉ VALIDÉ : {m_id} -> {statut}")
            try:
                import export_resultats_to_front
                export_resultats_to_front.main()
            except Exception:
                pass
        else:
            time.sleep(2)


def main():
    log_verif("LANCEMENT DES 10 AGENTS VÉRIFICATEURS (5 AUDIT BASE + 5 SENTINELLES LIVE)")
    with ThreadPoolExecutor(max_workers=10, thread_name_prefix="VERIF") as executor:
        # 5 agents sur la base
        for i in range(1, 6):
            executor.submit(worker_audit_base, i)
        # 5 agents sur le live
        for i in range(6, 11):
            executor.submit(worker_live_sentinelle, i)


if __name__ == "__main__":
    main()
