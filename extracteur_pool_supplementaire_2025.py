#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extracteur_pool_supplementaire_2025.py
Pool additionnel de 70 agents pour l'année 2025.
Fonctionne en parallèle des tâches déjà existantes avec commit direct en SQLite.
"""
import sys
import os
import time
import json
import sqlite3
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.insert(0, os.getcwd())

from extract_and_load_resultats import (
    segment_resultats,
    split_unit_into_dossiers,
    chunk_unit,
    build_resultats_prompt,
    call_freellm_api,
    merge_lot_results,
    save_resultat_to_db,
    DB_PATH
)
from coherence_resultats import verifier_et_corriger_dossier
import export_resultats_to_front

MANIFEST_PATH = Path("manifeste_complet_resultats.json")
db_lock = threading.Lock()

def get_existing_bulletins():
    with db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=60)
        cur = conn.cursor()
        deja = set()
        for r in cur.execute("SELECT DISTINCT bulletin FROM resultats_marches").fetchall():
            if r[0]:
                deja.add(r[0].strip().upper())
                m = re.search(r"N\s*(\d{4})", r[0], re.I)
                if m:
                    deja.add(f"N{m.group(1)}".upper())
        conn.close()
        return deja

def process_bulletin_task(q_data):
    num = q_data.get("numero")
    b_nom = q_data.get("bulletin_nom") or f"Quotidien {num}"
    sections = q_data.get("sections", {})
    t0 = time.time()
    marches_ce_bulletin = 0

    print(f"[Agent Sup 2025 - {threading.current_thread().name}] Démarrage {b_nom} ({len(sections)} sections)")

    for sec_name, sec_info in sections.items():
        pdf_path = Path(sec_info.get("pdf_path", ""))
        if not pdf_path.exists():
            continue

        try:
            units = segment_resultats(str(pdf_path))
        except Exception as e_seg:
            continue

        if not units:
            continue

        all_dossiers = []
        for u in units:
            dossiers = split_unit_into_dossiers(u)
            all_dossiers.extend(dossiers)

        for d_idx, dossier in enumerate(all_dossiers, 1):
            flat = dossier.get("flat_text", "")
            if len(flat.strip()) < 80:
                continue

            parsed_data = None
            if len(flat) <= 12000:
                prompt = build_resultats_prompt(dossier)
                parsed_data = call_freellm_api(prompt, timeout=120)
            else:
                chunks = chunk_unit(dossier)
                lot_res_list = []
                for ch in chunks:
                    p = build_resultats_prompt(ch)
                    res = call_freellm_api(p, timeout=120)
                    if res:
                        lot_res_list.append(res)
                if lot_res_list:
                    parsed_data = merge_lot_results(lot_res_list)

            if parsed_data:
                try:
                    with db_lock:
                        conn = sqlite3.connect(DB_PATH, timeout=60)
                        conn.execute("PRAGMA journal_mode=WAL;")
                        res_id = save_resultat_to_db(
                            conn=conn,
                            data=parsed_data,
                            unit=dossier, bulletin_name=b_nom,
                            date_parution=q_data.get("date_parution"),
                            source_pdf=q_data.get("source_pdf")
                        )
                        conn.commit()
                        verifier_et_corriger_dossier(conn, res_id)
                        conn.commit()
                        conn.close()
                    marches_ce_bulletin += 1
                except Exception as e_db:
                    print(f"[{b_nom}] Erreur DB : {e_db}")

    dur = round(time.time() - t0, 1)
    print(f"[Agent Sup 2025 - {threading.current_thread().name}] Terminé {b_nom} : +{marches_ce_bulletin} marchés en {dur}s.")
    return b_nom, marches_ce_bulletin

def main():
    max_workers = 70
    if not MANIFEST_PATH.exists():
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifeste = json.load(f)

    queue = manifeste.get("queue_2025", [])
    deja = get_existing_bulletins()

    a_traiter = [q for q in queue if (q.get("bulletin_nom") or f"Quotidien {q['numero']}") not in deja
                 and f"N{q['numero']}" not in deja]

    print(f"=== POOL SUPPLÉMENTAIRE 2025 : {max_workers} AGENTS (Restants: {len(a_traiter)}) ===")

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Sup2025") as executor:
        futures = {executor.submit(process_bulletin_task, q): q for q in a_traiter}
        for future in as_completed(futures):
            pass

if __name__ == "__main__":
    main()
