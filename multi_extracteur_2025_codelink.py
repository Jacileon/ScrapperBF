#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multi_extracteur_2025_codelink.py
=================================
Orchestrateur multi-threads pour extraire en parallèle les Quotidiens de 2025
via la clé Codelink (deepseek-v4.1-flash & glm-5.3-flash).
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
        conn = sqlite3.connect(DB_PATH)
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
    num = q_data["numero"]
    b_nom = q_data.get("bulletin_nom") or f"Quotidien {num}"
    date_parution = q_data.get("date_parution")
    sections = q_data.get("sections", {})

    print(f"\n[Worker 2025-{threading.current_thread().name}] Démarrage {b_nom} ({len(sections)} sections)...")

    marches_ce_bulletin = 0
    t0 = time.time()

    for sec_name, sec_info in sections.items():
        pdf_path = Path(sec_info["pdf_path"])
        if not pdf_path.exists():
            continue

        units = segment_resultats(str(pdf_path))
        if not units:
            continue

        all_dossiers = []
        for i, unit in enumerate(units, 1):
            unit["_numero"] = i
            all_dossiers.extend(split_unit_into_dossiers(unit))

        for k, d_unit in enumerate(all_dossiers, 1):
            emetteur = d_unit.get("emetteur", f"Dossier_{k}")
            flat_text = d_unit.get("flat_text", "")

            if len(flat_text.strip()) < 80:
                continue

            if len(flat_text) > 4200:
                chunks = chunk_unit(d_unit, max_chars=4200)
                chunk_results = []
                for ch in chunks:
                    prompt = build_resultats_prompt(ch)
                    res = call_freellm_api(prompt)
                    if res:
                        chunk_results.append(res)
                extracted_data = merge_lot_results(chunk_results) if chunk_results else None
            else:
                prompt = build_resultats_prompt(d_unit)
                extracted_data = call_freellm_api(prompt)

            if not extracted_data or not isinstance(extracted_data, dict):
                continue

            with db_lock:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    res_id = save_resultat_to_db(
                        conn=conn,
                        data=extracted_data,
                        unit=d_unit,
                        bulletin_name=b_nom,
                        date_parution=date_parution,
                        source_pdf=q_data.get("source_pdf")
                    )
                    conn.commit()
                    verifier_et_corriger_dossier(conn, res_id)
                    conn.commit()
                    conn.close()
                    marches_ce_bulletin += 1
                except Exception as e_db:
                    print(f"[{b_nom}] Erreur DB : {e_db}")

    with db_lock:
        try:
            export_resultats_to_front.main()
        except Exception:
            pass

    dur = round(time.time() - t0, 1)
    print(f"[Worker 2025-{threading.current_thread().name}] FIN {b_nom} : +{marches_ce_bulletin} marchés en {dur}s.")
    return b_nom, marches_ce_bulletin


def main():
    annee = "2025"
    max_workers = 4

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifeste = json.load(f)

    queue = manifeste.get(f"queue_{annee}", [])
    deja = get_existing_bulletins()

    a_traiter = [q for q in queue if (q.get("bulletin_nom") or f"Quotidien {q['numero']}") not in deja
                 and f"N{q['numero']}" not in deja]

    print("=" * 80)
    print(f"LANCEMENT DU MULTI-EXTRACTEUR 2025 VIA CODELINK [{annee}]")
    print(f"Quotidiens 2025 restants à traiter : {len(a_traiter)} | Workers : {max_workers}")
    print("=" * 80)

    total_ajoutes = 0
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="CDL25") as executor:
        futures = {executor.submit(process_bulletin_task, q): q for q in a_traiter}
        for future in as_completed(futures):
            q_info = futures[future]
            try:
                b_nom, count = future.result()
                total_ajoutes += count
            except Exception as e:
                print(f"[ERREUR 2025] Échec pour {q_info.get('numero')} : {e}")

    print(f"\nEXTRACTION 2025 TERMINÉE ! Total marchés ajoutés : {total_ajoutes}")


if __name__ == "__main__":
    main()
