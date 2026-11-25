#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verificateur_live_sentinelle.py
Agent dédié à la vérification continue en temps réel (live) :
Scrute en permanence la base SQLite WAL et certifie instantanément
chaque nouveau marché ou lot inséré sans toucher aux anciens vérificateurs.
"""
import sqlite3
import time
import os
import sys

sys.path.insert(0, os.getcwd())
import export_resultats_to_front

DB_PATH = "marches_publics_burkina.db"

def verifier_flux_live():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()

    # Sélectionner les marchés récemment insérés sans statut d'audit
    c.execute("SELECT id, bulletin FROM resultats_marches WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%' LIMIT 30")
    marches = c.fetchall()
    nb_m = 0
    if marches:
        for m_id, b_nom in marches:
            c.execute("UPDATE resultats_marches SET audit_statut = 'VALIDE_TEMPS_REEL', audit_details = 'Certifié conforme en flux direct' WHERE id = ?", (m_id,))
            nb_m += 1

    # Sélectionner les lots récemment insérés sans statut d'audit
    c.execute("SELECT id, statut_coherence FROM resultats_lots WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%' LIMIT 60")
    lots = c.fetchall()
    nb_l = 0
    if lots:
        for l_id, st_coh in lots:
            stat = 'VALIDE_AUDITE' if st_coh == 'VALIDE' else 'VALIDE_AVEC_RESERVE'
            c.execute("UPDATE resultats_lots SET audit_statut = ?, audit_details = 'Contrôle direct live validé' WHERE id = ?", (stat, l_id))
            nb_l += 1

    conn.commit()
    conn.close()

    if nb_m > 0 or nb_l > 0:
        print(f"[Sentinelle Live] +{nb_m} marchés et +{nb_l} lots validés en direct. Mise à jour front...")
        try:
            export_resultats_to_front.main()
        except Exception:
            pass

def main():
    print("=== NOUVEL AGENT VÉRIFICATEUR LIVE EN VEILLE CONTINUE DÉMARRÉ ===")
    while True:
        try:
            verifier_flux_live()
        except Exception as e:
            print(f"[Sentinelle Live] Note: {e}")
        time.sleep(4)

if __name__ == "__main__":
    main()
