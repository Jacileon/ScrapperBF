#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_saas.py
===============
Prépare la base pour le SaaS Veille BF :
  1. Crée les tables SaaS (users, plans, subscriptions, payments, ...).
  2. Insère/actualise les 3 offres (Gratuit / Pro / Entreprise) depuis backend/plans.py.
  3. (Optionnel) crée un compte administrateur de départ.

Idempotent : peut être relancé sans danger.

Usage :
    python migrate_saas.py
    python migrate_saas.py --admin admin@veillebf.bf --admin-pass MotDePasseFort
"""

import argparse
import json
import sys

from backend.db import get_db, init_saas_schema
from backend.plans import PLANS, PLAN_ORDER
from backend.security import hash_password


def seed_plans(conn) -> None:
    c = conn.cursor()
    for pid in PLAN_ORDER:
        p = PLANS[pid]
        c.execute(
            """
            INSERT INTO plans (id, nom, sous_titre, prix_mensuel_fcfa, prix_annuel_fcfa,
                               features_json, ordre, actif)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                nom=excluded.nom,
                sous_titre=excluded.sous_titre,
                prix_mensuel_fcfa=excluded.prix_mensuel_fcfa,
                prix_annuel_fcfa=excluded.prix_annuel_fcfa,
                features_json=excluded.features_json,
                ordre=excluded.ordre,
                actif=1
            """,
            (
                p["id"], p["nom"], p["sous_titre"],
                p["prix_mensuel_fcfa"], p["prix_annuel_fcfa"],
                json.dumps(p["features"], ensure_ascii=False), p["ordre"],
            ),
        )
    conn.commit()


def ensure_admin(conn, email: str, password: str) -> None:
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email.lower(),))
    if c.fetchone():
        print(f"[=] Admin déjà existant : {email}")
        return
    c.execute(
        """INSERT INTO users (email, password_hash, nom, plan_id, role, email_verifie)
           VALUES (?, ?, ?, 'entreprise', 'admin', 1)""",
        (email.lower(), hash_password(password), "Administrateur"),
    )
    conn.commit()
    print(f"[OK] Compte administrateur créé : {email}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Migration SaaS Veille BF")
    ap.add_argument("--admin", help="Email de l'administrateur à créer")
    ap.add_argument("--admin-pass", help="Mot de passe de l'administrateur")
    args = ap.parse_args()

    conn = get_db()
    try:
        init_saas_schema(conn)
        print("[OK] Tables SaaS créées / vérifiées.")
        seed_plans(conn)
        print(f"[OK] {len(PLAN_ORDER)} offres insérées : {', '.join(PLAN_ORDER)}")

        if args.admin and args.admin_pass:
            ensure_admin(conn, args.admin, args.admin_pass)
        elif args.admin or args.admin_pass:
            print("[!] --admin et --admin-pass doivent être fournis ensemble.", file=sys.stderr)

        # Récapitulatif
        c = conn.cursor()
        c.execute("SELECT id, nom, prix_mensuel_fcfa FROM plans ORDER BY ordre")
        print("\nOffres en base :")
        for row in c.fetchall():
            print(f"  - {row['id']:<12} {row['nom']:<12} {row['prix_mensuel_fcfa']:>8} FCFA/mois")
        c.execute("SELECT COUNT(*) AS n FROM users")
        print(f"\nUtilisateurs enregistrés : {c.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")
    finally:
        conn.close()

    print("\n[OK] Migration terminée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
