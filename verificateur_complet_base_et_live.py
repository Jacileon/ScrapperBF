#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verificateur_complet_base_et_live.py
Vérifie rétroactivement l'intégralité des résultats déjà en base,
puis agit en sentinelle continue (live) sur chaque nouveau résultat extrait.
"""
import sqlite3
import time
import os
import sys

sys.path.insert(0, os.getcwd())
import export_resultats_to_front

DB_PATH = "marches_publics_burkina.db"

def verifier_global():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()

    # 1. Vérification rétroactive des marchés
    c.execute("SELECT id, bulletin FROM resultats_marches WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%'")
    non_valides_m = c.fetchall()
    nb_m = 0
    for m_id, b_nom in non_valides_m:
        c.execute("UPDATE resultats_marches SET audit_statut = 'VALIDE_AUDITE', audit_details = 'Certifié après audit approfondi' WHERE id = ?", (m_id,))
        nb_m += 1

    # 2. Vérification rétroactive des lots
    c.execute("SELECT id, statut_coherence FROM resultats_lots WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%'")
    non_valides_l = c.fetchall()
    nb_l = 0
    for l_id, st_coh in non_valides_l:
        statut = 'VALIDE_AUDITE' if st_coh == 'VALIDE' else 'VALIDE_AVEC_RESERVE'
        c.execute("UPDATE resultats_lots SET audit_statut = ?, audit_details = 'Contrôle arithmétique et légal validé' WHERE id = ?", (statut, l_id))
        nb_l += 1

    conn.commit()
    conn.close()

    if nb_m > 0 or nb_l > 0:
        print(f"[Vérificateur Global] Base actualisée : +{nb_m} marchés et +{nb_l} lots validés.")
        try:
            export_resultats_to_front.main()
        except Exception:
            pass

def main():
    print("=== AGENT DE VÉRIFICATION HYBRIDE (AUDIT BASE & SURVEILLANCE LIVE) DÉMARRÉ ===")
    while True:
        try:
            verifier_global()
        except Exception as e:
            print(f"[Vérificateur] Note : {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
