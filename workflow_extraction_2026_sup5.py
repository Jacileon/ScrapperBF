import sys
import os
import json
import sqlite3
import re
import time
import asyncio
from pathlib import Path

sys.path.insert(0, os.getcwd())
user_site = r"C:\Users\DANIEL\AppData\Local\Programs\Python\Python313\Lib\site-packages"
if user_site not in sys.path:
    sys.path.append(user_site)

from pdf_resultats_extract import segment_resultats
from resultats_chunker import chunk_unit, merge_lot_results
from resultats_llm import build_resultats_prompt
from extract_and_load_resultats import save_resultat_to_db, DB_PATH, bloquer_si_file_centralisee_active
from coherence_resultats import verifier_et_corriger_dossier

# Verrou pipeline : ancien pipeline PDF neutralisé tant que la file .md contient du travail.
bloquer_si_file_centralisee_active("workflow_extraction_2026_sup5")
import export_resultats_to_front

def parse_json_agent_res(res):
    if isinstance(res, dict):
        return res
    if not res or not isinstance(res, str):
        return None
    s = res.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if m:
        s = m.group(1).strip()
    try:
        data = json.loads(s)
        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else {}
        return data if isinstance(data, dict) else None
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(s[start:end+1])
                if isinstance(data, list):
                    data = data[0] if data and isinstance(data[0], dict) else {}
                return data if isinstance(data, dict) else None
            except Exception:
                pass
    return None

async def extract_one_task(item, sem):
    async with sem:
        instruction_finish = (
            "\n\nINSTRUCTION CRITIQUE : Tu DOIS appeler l'outil 'finish' en lui passant comme argument 'result' "
            "la chaîne de texte contenant l'objet JSON compact extrait structuré (avec clés autorite_contractante, reference, objet, lots, soumissionnaires...). "
            "Va droit au but : appelle directement 'finish' avec le JSON sans longue dissertation."
        )
        prompt_complet = item["prompt"] + instruction_finish
        role = item["role"]
        for att in range(1, 3):
            try:
                raw_res = await asyncio.wait_for(
                    agent(
                        prompt=prompt_complet,
                        schema={"type": "string"},
                        role=role,
                        type_name="extracteur_cognitif",
                        model="inherit"
                    ),
                    timeout=150
                )
                parsed = parse_json_agent_res(raw_res)
                if parsed:
                    return parsed
            except Exception as e:
                log(f"    [Agent {role}] tentative {att}/2: {e}")
        return None

sem = asyncio.Semaphore(5)

log("=== DÉMARRAGE DU POOL SUPPLÉMENTAIRE DE 5 AGENTS COGNITIFS SUR L'ANNÉE 2026 ===")

with open("manifeste_complet_resultats.json", "r", encoding="utf-8") as f:
    manifeste = json.load(f)

queue_2026 = manifeste.get("queue_2026", [])

conn = sqlite3.connect(DB_PATH)
deja_extraits = set()
for r in conn.execute("SELECT DISTINCT bulletin FROM resultats_marches").fetchall():
    if r[0]:
        deja_extraits.add(r[0].strip().upper())
        m = re.search(r"N\s*(\d{4})", r[0], re.I)
        if m:
            deja_extraits.add(f"N{m.group(1)}".upper())

a_traiter = []
for q in queue_2026:
    num = q["numero"]
    b_nom = q.get("bulletin_nom") or f"Quotidien {num}"
    if b_nom.upper() not in deja_extraits and f"N{num}".upper() not in deja_extraits:
        a_traiter.append(q)

log(f"Quotidiens 2026 restants à traiter : {len(a_traiter)} (Déjà en base : {len(deja_extraits)})")

for q_idx, q in enumerate(a_traiter, 1):
    num = q["numero"]
    b_nom = q.get("bulletin_nom") or f"Quotidien {num}"
    sections = q.get("sections", {})
    date_parution = q.get("date_parution")
    
    log(f"\n>>> [Pool Sup 2026] [{q_idx}/{len(a_traiter)}] Bulletin {b_nom} ({len(sections)} sections)")
    
    for sec_name, sec_info in sections.items():
        pdf_path = Path(sec_info["pdf_path"])
        if not pdf_path.exists():
            continue
            
        units = segment_resultats(str(pdf_path))
        if not units:
            continue
            
        log(f"  Section {sec_name.upper()} : {len(units)} unités d'attribution détectées")
        
        tasks_to_run = []
        unit_meta_list = []
        
        for u_idx, u in enumerate(units, 1):
            flat = u.get("flat_text", "")
            if len(flat.strip()) < 80:
                continue
                
            emetteur = u.get("emetteur") or f"Unite_{u_idx}"
            
            if len(flat) <= 1800:
                p = f"Extrais ce tableau de résultats de marchés publics en JSON compact :\n\n{build_resultats_prompt(u)}"
                item = {"prompt": p, "role": f"Sup26-{num} - {emetteur[:25]}"}
                unit_meta_list.append({"type": "single", "unit": u, "emetteur": emetteur})
                tasks_to_run.append(extract_one_task(item, sem))
            else:
                chunks = chunk_unit(u)
                lot_tasks = []
                for ch_idx, ch in enumerate(chunks, 1):
                    p = f"Extrais ce lot/dossier de résultats de marchés publics en JSON compact :\n\n{build_resultats_prompt(ch)}"
                    item = {"prompt": p, "role": f"Sup26-{num} - {emetteur[:20]}_L{ch_idx}"}
                    lot_tasks.append(extract_one_task(item, sem))
                unit_meta_list.append({"type": "chunked", "unit": u, "emetteur": emetteur, "tasks": lot_tasks})
                tasks_to_run.extend(lot_tasks)
                
        if tasks_to_run:
            results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
            res_cursor = 0
            for meta in unit_meta_list:
                parsed_data = None
                if meta["type"] == "single":
                    res = results[res_cursor]
                    res_cursor += 1
                    if isinstance(res, dict) and res:
                        parsed_data = res
                else:
                    nb_ch = len(meta["tasks"])
                    ch_res = results[res_cursor:res_cursor+nb_ch]
                    res_cursor += nb_ch
                    val_res = [r for r in ch_res if isinstance(r, dict) and r]
                    if val_res:
                        parsed_data = merge_lot_results(val_res)
                        
                if parsed_data:
                    c = sqlite3.connect(DB_PATH)
                    c.execute("PRAGMA journal_mode=WAL;")
                    try:
                        res_id = save_resultat_to_db(
                            conn=c,
                            data=parsed_data,
                            unit=meta["unit"],
                            bulletin_name=b_nom,
                            date_parution=date_parution,
                            source_pdf=str(pdf_path)
                        )
                        c.commit()
                        verifier_et_corriger_dossier(c, res_id)
                        c.commit()
                        log(f"    ✔ Marché enregistré : {res_id} ({meta['emetteur']})")
                    except Exception as e_db:
                        log(f"    ✖ Erreur enregistrement : {e_db}")
                    finally:
                        c.close()
                        
    try:
        export_resultats_to_front.main()
    except Exception:
        pass
