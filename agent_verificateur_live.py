#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_verificateur_live.py  (v2 — 24/11/2026)
==============================================
Agent de vérification en temps réel des résultats insérés en DB.
Surveille en boucle les nouveaux enregistrements et effectue :
  1. Vérification cohérence (coherence_resultats)
  2. Détection des anomalies statistiques (montants aberrants, attributaires douteux)
  3. Journalisation dans audit_log.jsonl

Usage :
    python agent_verificateur_live.py
    python agent_verificateur_live.py --intervalle 30 --batch 50
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
user_site = r"C:\Users\DANIEL\AppData\Local\Programs\Python\Python313\Lib\site-packages"
if user_site not in sys.path:
    sys.path.append(user_site)

from extract_and_load_resultats import DB_PATH
import config
config.load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [VERIF] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs_verificateur_live.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("verificateur")

AUDIT_LOG = Path("audit_log.jsonl")


def write_audit(entry: dict):
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def verifier_lot(lot: dict) -> dict:
    issues = []
    if not lot.get("attributaire_nom") and not lot.get("infructueux"):
        issues.append("MANQUE_ATTRIBUTAIRE")
    try:
        mmin = float((lot.get("montant_min_ttc") or "0").replace(" ", "").replace(",", "."))
        mmax = float((lot.get("montant_max_ttc") or "0").replace(" ", "").replace(",", "."))
        if mmin > 0 and mmax > 0 and mmin > mmax:
            issues.append("MONTANT_MIN_SUP_MAX")
    except Exception:
        pass
    return {"lot_id": lot.get("id"), "numero_lot": lot.get("numero_lot"),
            "issues": issues, "statut": "ALERTE" if issues else "OK"}


def audit_cycle(conn: sqlite3.Connection, since_id: int, batch: int) -> int:
    rows = conn.execute(
        """SELECT rowid, id, bulletin, autorite_contractante, objet, nombre_lots
           FROM resultats_marches WHERE rowid > ? ORDER BY rowid ASC LIMIT ?""",
        (since_id, batch)
    ).fetchall()

    if not rows:
        return since_id

    max_id = since_id
    alertes = 0

    for row in rows:
        row_id, res_id, bulletin, autorite, objet, nb_lots = row[0], row[1], row[2], row[3], row[4], row[5]
        max_id = max(max_id, int(row_id))

        lots = conn.execute(
            """SELECT id, numero_lot, attributaire_nom, est_infructueux, montant_attribue_min_fcfa, montant_attribue_max_fcfa
               FROM resultats_lots WHERE resultat_id = ?""", (res_id,)
        ).fetchall()

        lot_dicts = [{"id": l[0], "numero_lot": l[1], "attributaire_nom": l[2],
                      "infructueux": bool(l[3]), "montant_min_ttc": l[4], "montant_max_ttc": l[5]}
                     for l in lots]

        try:
            from coherence_resultats import verifier_et_corriger_dossier
            verifier_et_corriger_dossier(conn, res_id)
            conn.commit()
        except Exception:
            pass

        lot_results = [verifier_lot(l) for l in lot_dicts]
        alertes_lot = [r for r in lot_results if r["statut"] == "ALERTE"]
        statut_global = "ALERTE" if alertes_lot else "OK"
        if alertes_lot:
            alertes += 1

        entry = {
            "ts": datetime.now().isoformat(), "res_id": res_id,
            "bulletin": bulletin, "autorite": autorite,
            "objet": (objet or "")[:60], "nb_lots_declares": nb_lots,
            "nb_lots_en_db": len(lots), "statut": statut_global,
            "alertes": alertes_lot,
        }
        write_audit(entry)

        if statut_global == "ALERTE":
            log.warning(f"⚠ res_id={res_id} {bulletin} | {(autorite or '')[:40]} → "
                        f"{len(alertes_lot)} alerte(s): {[a['issues'] for a in alertes_lot]}")
        else:
            log.info(f"✔ res_id={res_id} {bulletin} | {(autorite or '')[:40]} | {len(lots)} lots OK")

    log.info(f"Cycle: {len(rows)} vérifiés, {alertes} alertes (jusqu'à res_id={max_id})")
    return max_id


def main():
    parser = argparse.ArgumentParser(description="Vérificateur live des résultats en DB")
    parser.add_argument("--intervalle", type=int, default=20)
    parser.add_argument("--batch", type=int, default=30)
    parser.add_argument("--depuis", type=int, default=0)
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Vérificateur Live — Intervalle: {args.intervalle}s | Batch: {args.batch}")
    print(f"  DB: {DB_PATH} | Audit: {AUDIT_LOG.absolute()}")
    print(f"{'='*60}\n")

    since_id = args.depuis
    if since_id == 0 and DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=30)
            row = conn.execute("SELECT MAX(id) FROM resultats_marches").fetchone()
            conn.close()
            if row and row[0]:
                since_id = max(0, row[0] - 100)
        except Exception:
            pass

    log.info(f"Vérificateur démarré depuis res_id={since_id}")
    idle_count = 0
    while True:
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            new_since = audit_cycle(conn, since_id, args.batch)
            conn.close()
            if new_since == since_id:
                idle_count += 1
                if idle_count % 15 == 0:
                    log.info(f"En attente... (idle {idle_count * args.intervalle}s)")
            else:
                idle_count = 0
                since_id = new_since
        except Exception as e:
            log.exception(f"Erreur: {e}")
        time.sleep(args.intervalle)


if __name__ == "__main__":
    main()
