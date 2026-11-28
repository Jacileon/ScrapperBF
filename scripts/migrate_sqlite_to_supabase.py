#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration ponctuelle SQLite -> Supabase (Postgres).

Usage (PowerShell) :
    $env:PG_DSN = "host=... port=5432 user=postgres.<ref> password=<pwd> dbname=postgres sslmode=require"
    python scripts/migrate_sqlite_to_supabase.py [chemin.db]

- Copie chaque table SQLite vers Postgres dans l'ordre des clés étrangères.
- Coerce chaque valeur vers le vrai type de la colonne Postgres (SQLite est typé
  dynamiquement : une colonne « entière » peut contenir du texte -> mis à NULL).
- Préserve les id explicites puis réaligne les séquences IDENTITY.
- Idempotent : ON CONFLICT DO NOTHING (ré-exécutable sans doublon).
- Robuste : FK orphelines nullables -> NULL ; repli ligne par ligne via SAVEPOINT
  (un seul commit par lot) en sautant les lignes fautives.
"""
import os
import sys
import sqlite3

import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = sys.argv[1] if len(sys.argv) > 1 else "marches_publics_burkina.db"
PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    sys.exit("PG_DSN manquant.")

BATCH = 2000

ORDER = [
    "plans", "users", "subscriptions", "payments", "usage_counters", "api_keys",
    "team_members", "profils_candidature", "groupement_profils", "radar_concurrents",
    "coffre_documents", "alertes", "user_details", "support_tickets", "support_messages",
    "annonces_avis", "detail_lots", "resultats_marches", "resultats_lots",
    "resultats_soumissionnaires", "entreprises", "communiques",
    "suivis", "dossiers", "dossier_pieces", "notifications",
]
IDENTITY = {
    "users", "subscriptions", "payments", "api_keys", "team_members", "radar_concurrents",
    "coffre_documents", "alertes", "support_tickets", "support_messages", "detail_lots",
    "resultats_lots", "resultats_soumissionnaires", "suivis", "dossiers", "dossier_pieces",
    "notifications",
}
INT_TYPES = {"smallint", "integer", "bigint"}
FLOAT_TYPES = {"double precision", "real", "numeric"}


def coerce(val, t):
    if val is None or val == "":
        return None
    if t in INT_TYPES:
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, int):
            return val
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return None
    if t in FLOAT_TYPES:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    # timestamptz / text / autres : tel quel
    return val


def sqlite_cols(scur, table):
    scur.execute(f'PRAGMA table_info("{table}")')
    return [r[1] for r in scur.fetchall()]


def main():
    sconn = sqlite3.connect(SQLITE_PATH)
    scur = sconn.cursor()
    pconn = psycopg2.connect(PG_DSN)
    pconn.autocommit = False
    pcur = pconn.cursor()

    def idset(table, col="id"):
        try:
            scur.execute(f'SELECT "{col}" FROM "{table}"')
            return {r[0] for r in scur.fetchall()}
        except Exception:
            return set()

    users_ids = idset("users")
    annonces_ids = idset("annonces_avis")
    resultats_ids = idset("resultats_marches")
    rlots_ids = idset("resultats_lots")
    dossiers_ids = idset("dossiers")
    subs_ids = idset("subscriptions")
    tickets_ids = idset("support_tickets")

    FK = {
        "subscriptions": [("user_id", users_ids, "skip")],
        "payments": [("user_id", users_ids, "skip"), ("subscription_id", subs_ids, "null")],
        "usage_counters": [("user_id", users_ids, "skip")],
        "api_keys": [("user_id", users_ids, "skip")],
        "team_members": [("owner_user_id", users_ids, "skip"), ("member_user_id", users_ids, "skip")],
        "profils_candidature": [("user_id", users_ids, "skip")],
        "groupement_profils": [("user_id", users_ids, "skip")],
        "radar_concurrents": [("user_id", users_ids, "skip")],
        "coffre_documents": [("user_id", users_ids, "skip")],
        "alertes": [("user_id", users_ids, "null")],
        "user_details": [("user_id", users_ids, "skip")],
        "support_tickets": [("user_id", users_ids, "skip")],
        "support_messages": [("ticket_id", tickets_ids, "skip")],
        "detail_lots": [("annonce_id", annonces_ids, "null")],
        "resultats_marches": [("annonce_avis_id", annonces_ids, "null")],
        "resultats_lots": [("resultat_id", resultats_ids, "null")],
        "resultats_soumissionnaires": [("resultat_id", resultats_ids, "null"), ("lot_id", rlots_ids, "null")],
        "suivis": [("user_id", users_ids, "skip")],
        "dossiers": [("user_id", users_ids, "skip")],
        "dossier_pieces": [("dossier_id", dossiers_ids, "skip")],
        "notifications": [("user_id", users_ids, "skip")],
    }

    total_ins = 0
    for table in ORDER:
        cols = sqlite_cols(scur, table)
        if not cols:
            print(f"  (absente) {table}")
            continue
        pcur.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='public' and table_name=%s", (table,))
        ptypes = {r[0]: r[1] for r in pcur.fetchall()}

        scur.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in cols)} FROM "{table}"')
        rows = scur.fetchall()
        fk = FK.get(table, [])
        idx = {c: i for i, c in enumerate(cols)}

        cleaned, skipped = [], 0
        for r in rows:
            r = [coerce(v, ptypes.get(cols[i], "text")) for i, v in enumerate(r)]
            drop = False
            for col, parent, action in fk:
                v = r[idx[col]]
                if v is not None and v not in parent:
                    if action == "skip":
                        drop = True
                        break
                    r[idx[col]] = None
            if drop:
                skipped += 1
                continue
            cleaned.append(tuple(r))

        collist = ", ".join('"' + c + '"' for c in cols)
        sql = f'INSERT INTO "{table}" ({collist}) VALUES %s ON CONFLICT DO NOTHING'
        one = f'INSERT INTO "{table}" ({collist}) VALUES ({", ".join(["%s"] * len(cols))}) ON CONFLICT DO NOTHING'
        ins = 0
        for i in range(0, len(cleaned), BATCH):
            batch = cleaned[i:i + BATCH]
            try:
                execute_values(pcur, sql, batch, page_size=BATCH)
                pconn.commit()
                ins += len(batch)
            except Exception:
                pconn.rollback()
                for row in batch:  # repli tolérant via savepoint (un seul commit)
                    try:
                        pcur.execute("SAVEPOINT sp")
                        pcur.execute(one, row)
                        pcur.execute("RELEASE SAVEPOINT sp")
                        ins += 1
                    except Exception:
                        pcur.execute("ROLLBACK TO SAVEPOINT sp")
                        skipped += 1
                pconn.commit()
        total_ins += ins
        print(f"  {table:<28} {ins:>7} / {len(rows):>7}" + (f"  ({skipped} sautées)" if skipped else ""), flush=True)

        if table in IDENTITY:
            try:
                pcur.execute(
                    f"SELECT setval(pg_get_serial_sequence('public.\"{table}\"','id'),"
                    f" (SELECT COALESCE(MAX(id),1) FROM \"{table}\"), true)")
                pconn.commit()
            except Exception as e:
                pconn.rollback()
                print(f"    (séquence {table} non réalignée: {e})", flush=True)

    print(f"\nTotal inséré : {total_ins} lignes.", flush=True)
    pcur.close(); pconn.close(); sconn.close()


if __name__ == "__main__":
    main()
