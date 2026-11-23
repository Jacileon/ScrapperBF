#!/usr/bin/env python3
"""
avis_parallel_extractor.py — Extracteur AVIS multi-APIs concurrent avec file d'attente

Fonctionnement :
  1. Charge le fichier de règles métier 'avis_rules.md' (rôle, champs, règles strictes, sans aucun regex).
  2. Lit la pile d'annonces Markdown (ex: générées dans output_pipeline/<numero>/annonces_md/).
  3. Met toutes les annonces dans une file d'attente (queue.Queue).
  4. Lance un pool de workers parallèles exploitant l'ensemble des APIs/clés configurées.
  5. Gestion dynamique des pannes & saturation (Retry automatique) :
     - Si une API répond 429 (quota/rate limit) ou timeout, l'annonce est IMMÉDIATEMENT
       remise dans la file d'attente (queue.put).
     - Une autre API libre reprendra le traitement de cette annonce dès qu'elle est disponible.
  6. Enregistre les extractions structurées en JSON (unitaire et consolidé).

Usage :
    python avis_parallel_extractor.py output_pipeline/N4505/annonces_md/
    python avis_parallel_extractor.py --dir output_pipeline/N4505/annonces_md/ --out-dir output/N4505/avis_json
"""

import os
import sys
import json
import time
import queue
import logging
import argparse
import threading
from pathlib import Path
from typing import List, Dict, Optional

import requests
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scrapperbf.extractor_queue")

BASE_DIR = Path(__file__).parent
RULES_PATH = BASE_DIR / "avis_rules.md"


def load_rules() -> str:
    """Charge le fichier de rôle et de règles d'extraction."""
    if not RULES_PATH.exists():
        raise FileNotFoundError(f"Fichier de règles introuvable : {RULES_PATH}")
    return RULES_PATH.read_text(encoding="utf-8")


def call_llm_api(provider_spec: dict, prompt_system: str, prompt_user: str) -> Optional[dict]:
    """Exécute un appel direct à une API configurée et extrait l'objet JSON."""
    kind = provider_spec["kind"]
    key = provider_spec.get("key") or provider_spec.get("api_key")
    model = provider_spec["model"]

    def _parse_clean_json(text: str) -> dict:
        t = (text or "").strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[1] if "\n" in t else t[3:]
            if t.endswith("```"):
                t = t.rsplit("```", 1)[0]
        return json.loads(t.strip())

    if kind == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/scrapperbf",
            "X-Title": "ScrapperBF Avis Extractor"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        r = requests.post(url, headers=headers, json=payload, timeout=45)
        if r.status_code == 429:
            raise RuntimeError(f"RateLimit 429 sur modèle {model}")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} : {r.text[:120]}")

        data = r.json()
        raw_text = data["choices"][0]["message"]["content"]
        return _parse_clean_json(raw_text)

    elif kind == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": prompt_system}]},
            "contents": [{"parts": [{"text": prompt_user}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
        }
        r = requests.post(url, headers=headers, json=payload, timeout=45)
        if r.status_code == 429:
            raise RuntimeError(f"Gemini 429 Quota dépassé")
        if r.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {r.status_code} : {r.text[:120]}")

        data = r.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_clean_json(raw_text)

    elif kind == "openai_compat":
        base_url = provider_spec.get("base_url", "http://localhost:11434/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            "temperature": 0.1
        }
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code == 429:
            raise RuntimeError(f"OpenAI compat 429 Quota dépassé sur {model}")
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI compat HTTP {r.status_code} : {r.text[:120]}")
        data = r.json()
        raw_text = data["choices"][0]["message"]["content"]
        return _parse_clean_json(raw_text)

    raise ValueError(f"Provider non supporté : {kind}")


class AvisParallelExtractor:
    """Orchestre la file d'attente d'annonces et la répartition multi-APIs avec remise en file."""

    def __init__(self, rules_text: str, out_dir: Path):
        self.rules_text = rules_text
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.task_queue = queue.Queue()
        self.results = []
        self.lock = threading.Lock()
        self.total_tasks = 0
        self.completed_tasks = 0

    def add_announcement_file(self, md_path: Path):
        text = md_path.read_text(encoding="utf-8")
        task = {
            "id": md_path.stem,
            "source_file": md_path.name,
            "text": text,
            "attempts": 0
        }
        self.task_queue.put(task)
        self.total_tasks += 1

    def worker_loop(self, provider_spec: dict):
        prov_name = f"{provider_spec['kind']}:{provider_spec['model']}"
        log.info("Démarrage du worker pour l'API [%s]", prov_name)

        while not self.task_queue.empty():
            try:
                task = self.task_queue.get_nowait()
            except queue.Empty:
                break

            task_id = task["id"]
            prompt_user = f"ANNONCE À EXTRAIRE :\n{task['text']}"

            try:
                log.info("[%s] Traitement de '%s' via %s...", task_id, task['source_file'], prov_name)
                extracted = call_llm_api(provider_spec, self.rules_text, prompt_user)

                if extracted and isinstance(extracted, dict):
                    extracted["_id"] = task_id
                    extracted["_source_file"] = task["source_file"]
                    extracted["_api_provider"] = prov_name
                    extracted["_date_extraction"] = time.strftime("%Y-%m-%d %H:%M:%S")

                    # Sauvegarde unitaire
                    out_unit = self.out_dir / f"{task_id}.json"
                    out_unit.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")

                    with self.lock:
                        self.results.append(extracted)
                        self.completed_tasks += 1
                        log.info("✓ [%d/%d] Succès : %s extrait par %s",
                                 self.completed_tasks, self.total_tasks, task_id, prov_name)

                    self.task_queue.task_done()
                else:
                    raise ValueError("Réponse JSON vide ou invalide")

            except Exception as e:
                task["attempts"] += 1
                log.warning("⚠ Échec temporaire sur %s avec %s : %s", task_id, prov_name, e)

                # Si tentative < 4, on remet l'annonce immédiatement dans la file d'attente
                if task["attempts"] < 4:
                    log.info("-> Remise de l'annonce '%s' dans la file d'attente (tentative %d/4)",
                             task_id, task["attempts"])
                    self.task_queue.put(task)
                else:
                    log.error("✗ Abandon de l'annonce %s après 4 échecs consécutifs", task_id)

                self.task_queue.task_done()
                # Temporisation pour laisser respirer l'API si 429
                time.sleep(3)

        log.info("Arrêt du worker pour l'API [%s]", prov_name)

    def run(self):
        providers = config.provider_specs()
        if not providers:
            log.error("Aucun provider LLM configuré dans .env ou model_keys.json !")
            return []

        log.info("Lancement de l'extraction concurrente sur %d annonce(s) avec %d provider(s)",
                 self.total_tasks, len(providers))

        threads = []
        for prov in providers:
            t = threading.Thread(target=self.worker_loop, args=(prov,))
            t.daemon = True
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Enregistrement consolidé
        consolidated_path = self.out_dir / "_tous_les_avis.json"
        consolidated_path.write_text(json.dumps(self.results, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Extraction terminée : %d/%d annonces enregistrées dans %s",
                 len(self.results), self.total_tasks, consolidated_path)
        return self.results


def process_annonces_dir(md_dir: Path, out_dir: Optional[Path] = None):
    rules = load_rules()
    md_dir = Path(md_dir)
    if not md_dir.is_dir():
        raise NotADirectoryError(f"Le dossier n'existe pas : {md_dir}")

    out_dir = out_dir or (md_dir.parent / "avis_extraits_json")
    extractor = AvisParallelExtractor(rules, out_dir)

    md_files = sorted(md_dir.glob("*.md"))
    log.info("Chargement de %d fichier(s) Markdown depuis %s", len(md_files), md_dir)
    for f in md_files:
        extractor.add_announcement_file(f)

    return extractor.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extracteur concurrent d'avis en file d'attente multi-APIs")
    parser.add_argument("dir", nargs="?", default="output_pipeline/N4505/annonces_md",
                        help="Dossier contenant les fichiers .md des annonces")
    parser.add_argument("--out-dir", default=None, help="Dossier de sortie pour les JSON extraits")
    args = parser.parse_args()

    target_dir = Path(args.dir)
    out_target = Path(args.out_dir) if args.out_dir else None
    process_annonces_dir(target_dir, out_target)
