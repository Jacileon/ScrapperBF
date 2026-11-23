#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
progression.py
==============
Script utilitaire rapide pour afficher l'état d'avancement de l'extraction
et les statistiques de la base de données marches_publics_burkina.db.

Usage :
    python progression.py
    python progression.py --suivi    (rafraîchissement automatique toutes les 5 secondes)
"""

import sys
import time
import sqlite3
from pathlib import Path

DB_PATH = Path("marches_publics_burkina.db")
TOTAL_CIBLE = 472  # Nombre d'avis unitaires uniques dédoublonnés sur 1er Octobre -> 22 Novembre 2026

def afficher_statistiques():
    if not DB_PATH.exists():
        print("[!] La base de données n'existe pas encore.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM annonces_avis;")
    nb_annonces = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM detail_lots;")
    nb_lots = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT numero_bulletin) FROM annonces_avis;")
    nb_bulletins = c.fetchone()[0]

    c.execute("SELECT SUM(budget_previsionnel_fcfa) FROM annonces_avis WHERE budget_previsionnel_fcfa IS NOT NULL;")
    total_budget = c.fetchone()[0] or 0

    pct = round((nb_annonces / TOTAL_CIBLE) * 100, 1) if TOTAL_CIBLE else 0
    bar_len = 30
    filled = int(bar_len * nb_annonces / TOTAL_CIBLE) if TOTAL_CIBLE else 0
    bar = "█" * filled + "░" * (bar_len - filled)

    budget_fmt = f"{total_budget:,} FCFA".replace(",", " ")

    print(f"\r[{bar}] {pct}% | {nb_annonces}/{TOTAL_CIBLE} annonces | {nb_lots} lots | Budget: {budget_fmt}", end="", flush=True)
    conn.close()

def afficher_detail_complet():
    if not DB_PATH.exists():
        print("[!] La base de données n'existe pas.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM annonces_avis;")
    nb_annonces = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM detail_lots;")
    nb_lots = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT numero_bulletin) FROM annonces_avis;")
    nb_bulletins = c.fetchone()[0]
    c.execute("SELECT SUM(budget_previsionnel_fcfa) FROM annonces_avis WHERE budget_previsionnel_fcfa IS NOT NULL;")
    total_budget = c.fetchone()[0] or 0

    pct = round((nb_annonces / TOTAL_CIBLE) * 100, 1) if TOTAL_CIBLE else 0

    print("=" * 70)
    print(" SUIVI DE PROGRESSION DE L'EXTRACTION (1er Octobre -> Aujourd'hui)")
    print("=" * 70)
    print(f" Progression globale   : {nb_annonces} / {TOTAL_CIBLE} annonces ({pct} %)")
    print(f" Lots multiples créés  : {nb_lots} lots détaillés")
    print(f" Bulletins finalisés   : {nb_bulletins} quotidiens")
    print(f" Volume financier total: {total_budget:,} FCFA".replace(",", " "))
    print("-" * 70)
    print(" 5 dernières annonces insérées :")
    c.execute("""
        SELECT id, autorite_contractante, budget_previsionnel_fcfa, date_limite_depot, remarque 
        FROM annonces_avis 
        ORDER BY date_extraction DESC, rowid DESC 
        LIMIT 5;
    """)
    for r in c.fetchall():
        b_str = f"{r[2]:,} FCFA".replace(",", " ") if r[2] else "Sans objet / Non précisé"
        rem_str = f" [Remarque: {r[4]}]" if r[4] else ""
        aut = (r[1] or "Inconnue")[:35]
        print(f" • {r[0]} | {aut} | {b_str} | Dépôt: {r[3]}{rem_str}")
    print("=" * 70)
    conn.close()

def main():
    if "--suivi" in sys.argv or "-w" in sys.argv:
        print("Suivi en direct de l'extraction (Ctrl+C pour quitter) :\n")
        try:
            while True:
                afficher_statistiques()
                time.sleep(3)
        except KeyboardInterrupt:
            print("\nFin du suivi.")
    else:
        afficher_detail_complet()

if __name__ == "__main__":
    main()
