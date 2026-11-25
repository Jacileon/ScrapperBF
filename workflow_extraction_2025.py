import sys
import os
import json
import sqlite3
import re
import time
import asyncio
from pathlib import Path

# Ajouter le répertoire de travail et les packages Python utilisateur
sys.path.insert(0, os.getcwd())
user_site = r"C:\Users\DANIEL\AppData\Local\Programs\Python\Python313\Lib\site-packages"
if user_site not in sys.path:
    sys.path.append(user_site)

from pdf_resultats_extract import segment_resultats
from resultats_chunker import chunk_unit, merge_lot_results
from resultats_llm import RESULTATS_SCHEMA, RESULTATS_SYSTEM_PROMPT, build_resultats_prompt
from extract_and_load_resultats import save_resultat_to_db, DB_PATH, bloquer_si_file_centralisee_active
from coherence_resultats import verifier_et_corriger_dossier

# Verrou pipeline : ancien pipeline PDF neutralisé tant que la file .md contient du travail.
bloquer_si_file_centralisee_active("workflow_extraction_2025")

def parse_json_agent_res(res):
    """Extrait et désérialise un JSON de manière tolérante (code blocks, liste ou objet)."""
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

async def safe_agent_call(prompt, role, model="inherit", retries=2, timeout_sec=180, type_name="extracteur_cognitif"):
    instruction_finish = (
        "\n\nINSTRUCTION CRITIQUE : Tu DOIS appeler l'outil 'finish' en lui passant comme argument 'result' "
        "la chaîne de texte contenant l'objet JSON extrait structuré (avec clés autorite_contractante, reference, objet, lots, soumissionnaires...). "
        "Va droit au but : appelle directement 'finish' avec le JSON sans longue dissertation."
    )
    prompt_complet = prompt + instruction_finish
    for att in range(1, retries + 1):
        try:
            raw_res = await asyncio.wait_for(
                agent(prompt=prompt_complet, schema={"type": "string"}, role=role, type_name=type_name, model=model),
                timeout=timeout_sec
            )
            parsed = parse_json_agent_res(raw_res)
            if parsed:
                return parsed
            else:
                log(f"    [JSON Invalide] tentative {att}/{retries} pour {role}")
        except asyncio.TimeoutError:
            log(f"    [Timeout {timeout_sec}s] tentative {att}/{retries} pour {role}")
        except Exception as err:
            log(f"    [Erreur {err}] tentative {att}/{retries} pour {role}")
    return None

# Lecture des arguments
batch_size = args.get("batch_size", 2) if "args" in globals() else 2
target_mois = args.get("mois", None) if "args" in globals() else None

log(f"=== Lancement de l'extraction cognitive 2025 (batch={batch_size}, mois={target_mois}) ===")

# 1. Charger le manifeste
with open("manifeste_complet_resultats.json", "r", encoding="utf-8") as f:
    manifeste = json.load(f)

queue_2025 = manifeste.get("queue_2025", [])
if target_mois:
    queue_2025 = [q for q in queue_2025 if q.get("mois") == target_mois]

# 2. Vérifier les bulletins déjà extraits
conn = sqlite3.connect(DB_PATH)
deja_extraits = set()
for r in conn.execute("SELECT DISTINCT bulletin FROM resultats_marches").fetchall():
    if r[0]:
        deja_extraits.add(r[0].strip().upper())
        m = re.search(r"N\s*(\d{4})", r[0], re.I)
        if m:
            deja_extraits.add(f"N{m.group(1)}".upper())

# Filtrer la file d'attente
a_traiter = []
for q in queue_2025:
    num = q.get("numero", "").strip().upper()
    nom = q.get("bulletin_nom", "").strip().upper()
    if num not in deja_extraits and nom not in deja_extraits:
        a_traiter.append(q)

log(f"Quotidiens 2025 restants à traiter : {len(a_traiter)} sur {len(queue_2025)}")

# Sélectionner le lot
lot = a_traiter[:batch_size]
if not lot:
    log("Tous les quotidiens ciblés de 2025 sont déjà extraits !")
    print("Tous les quotidiens 2025 sont déjà extraits.")

total_marches_lot = 0

for idx, q in enumerate(lot, 1):
    b_nom = q.get("bulletin_nom", f"Quotidien {q['numero']}")
    num = q.get("numero")
    phase(f"[{idx}/{len(lot)}] {b_nom}")
    log(f"Traitement cognitif de {b_nom} ({num})")
    
    sections = q.get("sections", {})
    marches_bulletin = 0
    
    for sec_name in ["mimod", "region"]:
        sec_info = sections.get(sec_name)
        if not sec_info or not sec_info.get("pdf_path"):
            continue
            
        pdf_path = sec_info["pdf_path"]
        if not os.path.exists(pdf_path):
            log(f"Fichier introuvable: {pdf_path}")
            continue
            
        # Segmentation de la section
        try:
            units = segment_resultats(pdf_path, numero=num, label=b_nom)
        except Exception as e:
            log(f"Erreur de segmentation sur {pdf_path}: {e}")
            continue
            
        log(f"  Section {sec_name.upper()} : {len(units)} unités découpées")
        
        for u_idx, u in enumerate(units, 1):
            u["_numero"] = u_idx
            emetteur = u.get("emetteur", "Inconnu")[:40]
            flat = u.get("flat_text", "")
            
            if len(flat.strip()) < 80:
                continue
                
            try:
                # Signal live pour dashboard
                try:
                    with open("statut_live_2025.json", "w", encoding="utf-8") as f_st:
                        json.dump({
                            "bulletin": b_nom,
                            "section": sec_name.upper(),
                            "unite": f"{u_idx}/{len(units)}",
                            "emetteur": emetteur[:45],
                            "marches_bulletin": marches_bulletin,
                            "total_lot": total_marches_lot,
                            "timestamp": time.strftime("%H:%M:%S"),
                            "mtime": time.time()
                        }, f_st)
                except Exception:
                    pass

                if len(flat) <= 1800:
                    p = f"Extrais ce tableau de résultats de marchés publics en JSON compact (autorite_contractante, reference, objet, lots avec soumissionnaires, montants, statut):\n\n{build_resultats_prompt(u)}"
                    res = await safe_agent_call(
                        prompt=p,
                        role=f"{num} - {emetteur}",
                        model="inherit"
                    )
                else:
                    # Découpage par lots si volumineux (seuil 1800 pour rapidité sous-agent ~30-40s)
                    chunks = chunk_unit(u, max_chars=1800)
                    chunk_results = []
                    for c_idx, chunk in enumerate(chunks, 1):
                        p = f"Extrais ce tableau de résultats de marchés publics en JSON compact (autorite_contractante, reference, objet, lots avec soumissionnaires, montants, statut):\n\n{build_resultats_prompt(chunk)}"
                        c_res = await safe_agent_call(
                            prompt=p,
                            role=f"{num} - {emetteur} (p.{c_idx}/{len(chunks)})",
                            model="inherit"
                        )
                        if c_res:
                            chunk_results.append(c_res)
                    res = merge_lot_results(chunk_results) if chunk_results else None
                    
                if not res or not isinstance(res, dict):
                    log(f"    Echec analyse pour unité {u_idx} ({emetteur})")
                    continue
                    
                # Sauvegarde en base SQLite
                res_id = save_resultat_to_db(
                    conn=conn,
                    data=res,
                    unit=u,
                    bulletin_name=b_nom,
                    date_parution=q.get("date_parution"),
                    source_pdf=q.get("source_pdf")
                )
                conn.commit()
                
                # Contrôle de cohérence à chaud
                anom = verifier_et_corriger_dossier(conn, res_id)
                conn.commit()
                
                nb_lots = len(res.get("lots", []))
                marches_bulletin += 1
                total_marches_lot += 1
                
                status_str = "VALIDE" if not anom.get("anomalies") else "ANOMALIE"
                log(f"    -> Enregistré : {res_id} ({nb_lots} lots, {status_str})")

                # Mise à jour immédiate du statut live pour le dashboard (--watch)
                try:
                    with open("statut_live_2025.json", "w", encoding="utf-8") as f_st:
                        json.dump({
                            "bulletin": b_nom,
                            "section": sec_name.upper(),
                            "unite": f"{u_idx}/{len(units)}",
                            "emetteur": emetteur[:45],
                            "marches_bulletin": marches_bulletin,
                            "total_lot": total_marches_lot,
                            "dernier_res_id": res_id,
                            "timestamp": time.strftime("%H:%M:%S"),
                            "mtime": time.time()
                        }, f_st)
                except Exception:
                    pass
                
            except Exception as e:
                log(f"    Erreur extraction unité {u_idx}: {e}")
                
    log(f"Fin {b_nom} : +{marches_bulletin} marchés enregistrés")

conn.close()
log(f"=== Lot terminé : +{total_marches_lot} marchés ajoutés en base SQLite ===")
print(f"Extraction terminée : +{total_marches_lot} marchés ajoutés.")
