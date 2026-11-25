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
bloquer_si_file_centralisee_active("workflow_extraction_2026_parallel")
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

log("=== DÉMARRAGE DU POOL DE 5 AGENTS COGNITIFS SUR L'ANNÉE 2026 ===")

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

total_marches_globaux = 0

for q_idx, q in enumerate(a_traiter, 1):
    num = q["numero"]
    b_nom = q.get("bulletin_nom") or f"Quotidien {num}"
    sections = q.get("sections", {})
    date_parution = q.get("date_parution")
    
    log(f"\n>>> [{q_idx}/{len(a_traiter)}] Bulletin {b_nom} ({len(sections)} sections)")
    marches_ce_bulletin = 0
    
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
                item = {"prompt": p, "role": f"{num} - {emetteur[:30]}"}
                unit_meta_list.append({"type": "single", "unit": u, "emetteur": emetteur})
                tasks_to_run.append(extract_one_task(item, sem))
            else:
                chunks = chunk_unit(u, max_chars=1800)
                sub_coros = []
                for c_idx, ch in enumerate(chunks, 1):
                    p = f"Extrais ce tableau de résultats de marchés publics en JSON compact :\n\n{build_resultats_prompt(ch)}"
                    item = {"prompt": p, "role": f"{num} - {emetteur[:25]} (p.{c_idx}/{len(chunks)})"}
                    sub_coros.append(extract_one_task(item, sem))
                unit_meta_list.append({"type": "chunked", "unit": u, "emetteur": emetteur, "count": len(chunks)})
                tasks_to_run.append(asyncio.gather(*sub_coros))
                
        if tasks_to_run:
            log(f"  -> Lancement parallèle de {len(tasks_to_run)} dossiers 2026 via les 10 agents...")
            raw_results = await asyncio.gather(*tasks_to_run)
            
            for meta, res in zip(unit_meta_list, raw_results):
                final_res = None
                if meta["type"] == "single":
                    final_res = res
                else:
                    valid_chunks = [c for c in res if c and isinstance(c, dict)]
                    if valid_chunks:
                        final_res = merge_lot_results(valid_chunks)
                        
                if final_res and isinstance(final_res, dict):
                    res_id = save_resultat_to_db(
                        conn=conn,
                        data=final_res,
                        unit=meta["unit"],
                        bulletin_name=b_nom,
                        date_parution=date_parution,
                        source_pdf=q.get("source_pdf")
                    )
                    conn.commit()
                    verifier_et_corriger_dossier(conn, res_id)
                    conn.commit()
                    marches_ce_bulletin += 1
                    total_marches_globaux += 1
                    log(f"    [2026 ENREGISTRÉ] {meta['emetteur'][:40]} -> {res_id}")
                    
    try:
        export_resultats_to_front.main()
    except Exception:
        pass
        
    try:
        with open("statut_live_2026.json", "w", encoding="utf-8") as f_st:
            json.dump({
                "bulletin": b_nom,
                "marches_bulletin": marches_ce_bulletin,
                "total_globaux": total_marches_globaux,
                "timestamp": time.strftime("%H:%M:%S"),
                "mtime": time.time()
            }, f_st)
    except Exception:
        pass

conn.close()
log(f"=== EXTRACTION 2026 TERMINÉE : +{total_marches_globaux} marchés ===")
