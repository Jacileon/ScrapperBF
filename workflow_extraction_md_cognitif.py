import sys
import os
import json
import sqlite3
import re
import asyncio
from pathlib import Path

sys.path.insert(0, os.getcwd())
user_site = r"C:\Users\DANIEL\AppData\Local\Programs\Python\Python313\Lib\site-packages"
if user_site not in sys.path:
    sys.path.append(user_site)

from resultats_llm import build_resultats_prompt
from extract_and_load_resultats import save_resultat_to_db, DB_PATH
from coherence_resultats import verifier_et_corriger_dossier
from resultats_md_splitter import claim_next_md, complete_md, release_md, parse_md_to_unit
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
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(s[start:end + 1])
                if isinstance(data, list):
                    data = data[0] if data and isinstance(data[0], dict) else {}
                return data if isinstance(data, dict) else None
            except Exception:
                pass
    return None


async def worker_loop(worker_id: int, annee: str, sem: asyncio.Semaphore):
    instruction_finish = (
        "\n\nINSTRUCTION CRITIQUE : Tu DOIS appeler l'outil 'finish' en lui passant comme argument 'result' "
        "la chaîne de texte contenant l'objet JSON compact extrait structuré (avec clés autorite_contractante, "
        "reference, objet, lots, soumissionnaires...). Va droit au but : appelle directement 'finish' avec le JSON."
    )
    empty_streak = 0
    blocked_streak = 0
    en_attente_dir = Path("resultats_decoupes_md") / annee / "en_attente"
    while True:
        md_path = claim_next_md(annee)
        if md_path is None:
            # Distinguer "file vide" de "fichiers présents mais non claimables"
            # (chunks de lot en attente de leur prédécesseur → traitement en série).
            reste = len(list(en_attente_dir.glob("*.md"))) if en_attente_dir.exists() else 0
            if reste > 0:
                blocked_streak += 1
                if blocked_streak >= 60:
                    log(f"[W{worker_id}] File bloquée depuis {blocked_streak} tours → arrêt (vérifier en_cours/)")
                    break
                await asyncio.sleep(5)
                continue
            empty_streak += 1
            if empty_streak >= 6:
                break
            await asyncio.sleep(5)
            continue

        empty_streak = 0
        blocked_streak = 0
        try:
            unit = parse_md_to_unit(md_path)
            prompt = f"Extrais ce tableau de résultats de marchés publics en JSON compact :\n\n{build_resultats_prompt(unit)}{instruction_finish}"
            parsed = None
            async with sem:
                for att in range(1, 3):
                    try:
                        raw_res = await asyncio.wait_for(
                            agent(
                                prompt=prompt,
                                schema={"type": "string"},
                                role=f"MD{annee}-W{worker_id}-{md_path.stem[:20]}",
                                type_name="extracteur_cognitif",
                                model="inherit",
                            ),
                            timeout=150,
                        )
                        parsed = parse_json_agent_res(raw_res)
                        if parsed:
                            break
                    except Exception as e:
                        log(f"[W{worker_id}] {md_path.name} tentative {att}/2: {e}")
                        await asyncio.sleep(3)

            if parsed:
                c = sqlite3.connect(DB_PATH, timeout=60)
                c.execute("PRAGMA journal_mode=WAL;")
                try:
                    res_id = save_resultat_to_db(
                        conn=c,
                        data=parsed,
                        unit=unit,
                        bulletin_name=unit.get("_bulletin_nom") or f"Quotidien {unit.get('_bulletin_numero', '')}",
                        date_parution=unit.get("_date_parution"),
                        source_pdf=unit.get("_source_pdf") or str(md_path),
                    )
                    c.commit()
                    verifier_et_corriger_dossier(c, res_id)
                    c.commit()
                    complete_md(md_path, annee)
                    log(f"✔ [W{worker_id}] {md_path.name} -> {res_id}")
                finally:
                    c.close()
            else:
                release_md(md_path, annee, to_error=False)
        except Exception as e:
            log(f"✖ [W{worker_id}] Erreur sur {md_path.name}: {e}")
            release_md(md_path, annee, to_error=False)


async def main():
    num_agents = 15
    sem = asyncio.Semaphore(num_agents)
    log(f"=== DÉMARRAGE DE {num_agents} AGENTS COGNITIFS SUR LES .MD 2025 ===")
    workers = [worker_loop(i + 1, "2025", sem) for i in range(num_agents)]
    await asyncio.gather(*workers)
    try:
        export_resultats_to_front.main()
    except Exception:
        pass
    log("=== FIN DE LA FILE .MD 2025 ===")


await main()
