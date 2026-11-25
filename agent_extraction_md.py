#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_extraction_md.py
======================
Agent autonome d'extraction des résultats de marchés publics depuis les fichiers .md.
Utilise DeepSeek (ou FreeLLMAPI en fallback) via call_with_rotation.

Usage :
    python agent_extraction_md.py --annee 2025 --workers 8
    python agent_extraction_md.py --annee 2026 --workers 6

Chaque worker tourne en boucle :
  1. claim_next_md() → prend atomiquement 1 fichier .md depuis en_attente/
  2. Envoie le texte à DeepSeek via call_with_rotation (layer3)
  3. Sauvegarde en DB (save_resultat_to_db avec upsert par lot)
  4. complete_md() → déplace vers termine/
  En cas d'erreur → release_md() → retour en en_attente/ ou erreur/
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
user_site = r"C:\Users\DANIEL\AppData\Local\Programs\Python\Python313\Lib\site-packages"
if user_site not in sys.path:
    sys.path.append(user_site)

from resultats_md_splitter import claim_next_md, complete_md, release_md, parse_md_to_unit
from resultats_llm import build_resultats_prompt, RESULTATS_SCHEMA, RESULTATS_SYSTEM_PROMPT
from extract_and_load_resultats import save_resultat_to_db, DB_PATH
from layer3_extract_llm import call_with_rotation, build_providers
import config

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs_agent_extraction_{os.getpid()}.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("agent_md")


def parse_json_flexible(raw) -> Optional[dict]:
    """Parse la réponse LLM en JSON, tolère les fences markdown et listes."""
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    # Enlever les fences ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if m:
        s = m.group(1).strip()
    try:
        data = json.loads(s)
        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else {}
        return data if isinstance(data, dict) else None
    except Exception:
        # Extraire le premier objet {...}
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(s[start:end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                pass
    return None


def process_one_md(md_path: Path, annee: str, providers: list,
                   worker_id: int, max_attempts: int = 2) -> dict:
    """Traite un fichier .md : parse → prompt → LLM → DB → complete/release."""
    result = {"file": md_path.name, "status": "SKIPPED", "res_id": None, "error": None}
    try:
        unit = parse_md_to_unit(md_path)
        flat = (unit.get("flat_text") or "").strip()
        if len(flat) < 60:
            log.warning(f"[W{worker_id}] {md_path.name}: texte trop court ({len(flat)}c), skip")
            release_md(md_path, annee, to_error=True)
            result["status"] = "ERROR_SHORT"
            return result

        prompt = build_resultats_prompt(unit)
        parsed = None

        for attempt in range(1, max_attempts + 1):
            try:
                raw = call_with_rotation(
                    prompt=prompt,
                    json_schema=RESULTATS_SCHEMA,
                    system_prompt=RESULTATS_SYSTEM_PROMPT,
                    max_retries=2,
                    providers=providers,
                )
                parsed = parse_json_flexible(raw)
                if parsed:
                    break
            except Exception as e:
                log.warning(f"[W{worker_id}] {md_path.name} tentative {attempt}/{max_attempts}: {e}")
                time.sleep(2 ** attempt)

        if not parsed:
            log.error(f"[W{worker_id}] {md_path.name}: LLM n'a pas retourné de JSON valide")
            release_md(md_path, annee, to_error=False)
            result["status"] = "ERROR_LLM"
            return result

        # Sauvegarder en DB
        conn = sqlite3.connect(str(DB_PATH), timeout=60)
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            res_id = save_resultat_to_db(
                conn=conn,
                data=parsed,
                unit=unit,
                bulletin_name=unit.get("_bulletin_nom") or f"Quotidien {unit.get('_bulletin_numero', '')}",
                date_parution=unit.get("_date_parution"),
                source_pdf=unit.get("_source_pdf") or str(md_path),
            )
            conn.commit()
            # Vérification cohérence (optionnelle, non bloquante)
            try:
                from coherence_resultats import verifier_et_corriger_dossier
                verifier_et_corriger_dossier(conn, res_id)
                conn.commit()
            except Exception:
                pass
        finally:
            conn.close()

        complete_md(md_path, annee)
        log.info(f"✔ [W{worker_id}] {md_path.name} → res_id={res_id}")
        result["status"] = "OK"
        result["res_id"] = res_id

    except Exception as e:
        log.exception(f"✖ [W{worker_id}] Exception sur {md_path.name}: {e}")
        try:
            release_md(md_path, annee, to_error=False)
        except Exception:
            pass
        result["status"] = "ERROR"
        result["error"] = str(e)

    return result


def worker_loop(worker_id: int, annee: str, providers: list,
                empty_patience: int = 8) -> dict:
    """Boucle principale d'un worker : prend des .md jusqu'à épuisement."""
    stats = {"processed": 0, "ok": 0, "errors": 0}
    empty_streak = 0

    log.info(f"[W{worker_id}] Démarré pour l'année {annee}")
    en_attente_dir = Path("resultats_decoupes_md") / annee / "en_attente"
    blocked_streak = 0
    while True:
        md_path = claim_next_md(annee)
        if md_path is None:
            reste = len(list(en_attente_dir.glob("*.md"))) if en_attente_dir.exists() else 0
            if reste > 0:
                # Fichiers présents mais non claimables (chunks de lot en attente
                # de leur prédécesseur) → on patiente sans compter comme "vide".
                blocked_streak += 1
                if blocked_streak >= 120:
                    log.warning(f"[W{worker_id}] File bloquée depuis {blocked_streak} tours → arrêt (vérifier en_cours/)")
                    break
                time.sleep(5)
                continue
            empty_streak += 1
            if empty_streak >= empty_patience:
                log.info(f"[W{worker_id}] File vide depuis {empty_streak} tours → arrêt")
                break
            time.sleep(3)
            continue

        empty_streak = 0
        blocked_streak = 0
        res = process_one_md(md_path, annee, providers, worker_id)
        stats["processed"] += 1
        if res["status"] == "OK":
            stats["ok"] += 1
        else:
            stats["errors"] += 1

    log.info(f"[W{worker_id}] Terminé : {stats}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Agent extraction résultats MD → DB")
    parser.add_argument("--annee", required=True, choices=["2025", "2026", "all"],
                        help="Année à traiter (2025, 2026, ou all)")
    parser.add_argument("--workers", type=int, default=8,
                        help="Nombre de workers parallèles (défaut: 8)")
    parser.add_argument("--max-attempts", type=int, default=2,
                        help="Tentatives LLM par fichier (défaut: 2)")
    args = parser.parse_args()

    # Vérifier la configuration LLM
    config.load_dotenv()
    providers = build_providers()
    if not providers:
        print("❌ Aucun provider LLM configuré !")
        print("   → Renseigne DEEPSEEK_API_KEY dans .env ou lance FreeLLMAPI (port 3001)")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Agent Extraction MD — Année(s): {args.annee}")
    print(f"  Workers: {args.workers}  |  Providers: {len(providers)}")
    for p in providers:
        base = p.get('_spec', {}).get('base_url', '') or ''
        print(f"    • {p['name']}  [{p['model']}] {('@' + base) if base else ''}")
    print(f"{'='*60}\n")

    annees = ["2025", "2026"] if args.annee == "all" else [args.annee]

    for annee in annees:
        en_attente = Path("resultats_decoupes_md") / annee / "en_attente"
        total = len(list(en_attente.glob("*.md"))) if en_attente.exists() else 0
        print(f"[{annee}] {total} fichiers .md en attente")

        if total == 0:
            print(f"[{annee}] Rien à traiter, on passe.")
            continue

        all_stats = {"processed": 0, "ok": 0, "errors": 0}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {
                ex.submit(worker_loop, i + 1, annee, providers, 8): i + 1
                for i in range(args.workers)
            }
            for fut in as_completed(futures):
                wid = futures[fut]
                try:
                    s = fut.result()
                    all_stats["processed"] += s["processed"]
                    all_stats["ok"] += s["ok"]
                    all_stats["errors"] += s["errors"]
                except Exception as e:
                    log.error(f"[W{wid}] Crash: {e}")

        print(f"\n[{annee}] ✅ TERMINÉ : {all_stats['ok']} OK, {all_stats['errors']} erreurs / {all_stats['processed']} traités")

    # Export final
    try:
        import export_resultats_to_front
        export_resultats_to_front.main()
        print("Export front terminé.")
    except Exception as e:
        log.warning(f"Export front ignoré: {e}")


if __name__ == "__main__":
    main()
