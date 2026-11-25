#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrateur d'extraction continue des RÉSULTATS avec FreeLLMAPI.
Fonctionnalités intégrées :
1. Lecture ordonnée du manifeste maître (manifeste_complet_resultats.json).
2. Extraction sémantique via FreeLLMAPI (modèle 'auto' / Mistral Large).
3. Contrôle à chaud de cohérence après chaque PDF (coherence_resultats.py).
4. Prise en compte du champ 'remarques_extracteur' pour alertes immédiates.
5. Barre de progression visuelle en direct et fichier de suivi 'progression_resultats.json'.
6. Reprise transparente (ignore les bulletins déjà présents en base).
"""

import argparse
import datetime
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from coherence_resultats import verifier_et_corriger_dossier
from extract_and_load_resultats import (
    DB_PATH,
    call_freellm_api,
    chunk_unit,
    classify_sector,
    merge_lot_results,
    save_resultat_to_db,
    segment_resultats,
    split_unit_into_dossiers,
    build_resultats_prompt
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("orchestrateur_continue")

MANIFEST_PATH = Path("manifeste_complet_resultats.json")
PROGRESSION_FILE = Path("progression_resultats.json")
ALERT_LOG_FILE = Path("alertes_extraction.log")


def get_existing_bulletins(conn: sqlite3.Connection) -> Set[str]:
    """Récupère l'ensemble des numéros de bulletins déjà extraits en base."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT bulletin FROM resultats_marches")
    return {row[0].strip() for row in cur.fetchall() if row[0]}


def get_db_metrics(conn: sqlite3.Connection) -> Dict[str, int]:
    """Récupère les compteurs globaux de la base."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM resultats_marches")
    nb_m = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resultats_lots")
    nb_l = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resultats_soumissionnaires")
    nb_s = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resultats_marches WHERE statut_coherence = 'ALERTE_INCERTITUDE'")
    nb_alt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resultats_marches WHERE statut_coherence = 'A_VERIFIER'")
    nb_ano = cur.fetchone()[0]
    return {
        "marches": nb_m,
        "lots": nb_l,
        "soumissionnaires": nb_s,
        "alertes": nb_alt,
        "anomalies": nb_ano
    }


def render_progress_bar(current: int, total: int, width: int = 30) -> str:
    """Génère une barre de progression visuelle ASCII stylisée."""
    if total <= 0:
        return "[" + " " * width + "] 0%"
    pct = min(1.0, current / total)
    filled = int(round(width * pct))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct * 100:.1f}%"


def update_progression_json(
    state: str,
    annee: str,
    current_idx: int,
    total_quotidiens: int,
    current_bulletin: str,
    metrics: Dict[str, int],
    elapsed_sec: float,
    recent_alerts: List[Dict]
):
    """Met à jour le fichier d'état progression_resultats.json en temps réel."""
    pct = round((current_idx / total_quotidiens) * 100, 1) if total_quotidiens else 0
    speed_qpm = round((current_idx / (elapsed_sec / 60)), 2) if elapsed_sec > 5 else 0
    remaining = total_quotidiens - current_idx
    eta_min = round((remaining / speed_qpm), 1) if speed_qpm > 0 else 0

    prog_data = {
        "statut": state,
        "annee_cible": annee,
        "progression": {
            "quotidiens_traites": current_idx,
            "total_quotidiens": total_quotidiens,
            "pourcentage": pct
        },
        "dernier_bulletin": current_bulletin,
        "statistiques_cumulees": metrics,
        "performance": {
            "temps_ecoule_sec": round(elapsed_sec, 1),
            "vitesse_quotidiens_par_minute": speed_qpm,
            "eta_estime_minutes": eta_min
        },
        "alertes_recentes": recent_alerts[-10:],
        "derniere_mise_a_jour": datetime.datetime.now().isoformat()
    }

    try:
        PROGRESSION_FILE.write_text(json.dumps(prog_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Impossible d'écrire la progression JSON: {e}")


def traiter_section_pdf(pdf_path: Path, bulletin_name: str, date_parution: Optional[str], conn: sqlite3.Connection) -> List[str]:
    """Extrait toutes les unités d'une section PDF découpée et les insère."""
    if not pdf_path.exists():
        logger.warning(f"Section PDF manquante: {pdf_path}")
        return []

    units = segment_resultats(str(pdf_path))
    if not units:
        logger.info(f"Aucun bloc émetteur détecté dans {pdf_path.name}.")
        return []

    # Éclatement en dossiers individuels
    all_dossiers = []
    for i, unit in enumerate(units, 1):
        unit["_numero"] = i
        sub_dossiers = split_unit_into_dossiers(unit)
        all_dossiers.extend(sub_dossiers)

    saved_ids = []
    for k, d_unit in enumerate(all_dossiers, 1):
        emetteur = d_unit.get("emetteur", f"Dossier_{k}")
        flat_text = d_unit.get("flat_text", "")

        # Ignorer les fragments ou blocs vides (< 80 caractères)
        if len(flat_text.strip()) < 80:
            logger.info(f"Dossier {k} ({emetteur}) ignoré car trop court ({len(flat_text.strip())} car.).")
            continue

        # Chunking par lots si texte volumineux (seuil 4200 pour compatibilité Groq & LLM rapides)
        if len(flat_text) > 4200:
            chunks = chunk_unit(d_unit, max_chars=4200)
            chunk_results = []
            for ch in chunks:
                prompt = build_resultats_prompt(ch)
                res = call_freellm_api(prompt)
                if res:
                    chunk_results.append(res)
                time.sleep(1.0)
            if not chunk_results:
                logger.error(f"Échec LLM (chunks) pour dossier {k} ({emetteur}).")
                continue
            final_data = merge_lot_results(chunk_results)
        else:
            prompt = build_resultats_prompt(d_unit)
            final_data = call_freellm_api(prompt)
            if not final_data:
                logger.error(f"Échec LLM pour dossier {k} ({emetteur}).")
                continue
            time.sleep(1.0)

        # Enregistrement en base
        res_id = save_resultat_to_db(
            conn=conn,
            data=final_data,
            unit=d_unit,
            bulletin_name=bulletin_name,
            date_parution=date_parution,
            source_pdf=str(pdf_path)
        )
        saved_ids.append(res_id)

        # Contrôle à chaud immédiat de cohérence
        audit = verifier_et_corriger_dossier(conn, res_id)
        if audit.get("alertes"):
            logger.info(f"  [ALERTE INCERTITUDE] {res_id}: {'; '.join(audit['alertes'])}")
        if audit.get("anomalies"):
            logger.warning(f"  [ANOMALIE ARITHMÉTIQUE] {res_id}: {'; '.join(audit['anomalies'])}")

        # Mise à jour du statut live immédiat pour le suivi en temps réel (--watch)
        try:
            with open("statut_live_2026.json", "w", encoding="utf-8") as f_st:
                json.dump({
                    "bulletin": bulletin_name,
                    "section": pdf_path.name,
                    "dossier": f"{k}/{len(all_dossiers)}",
                    "emetteur": emetteur[:45],
                    "total_marches_section": len(saved_ids),
                    "dernier_res_id": res_id,
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    "mtime": time.time()
                }, f_st)
        except Exception:
            pass

    return saved_ids


def lancer_orchestration(
    annee: str = "2026",
    mois_filtre: Optional[str] = None,
    limite: Optional[int] = None,
    forcer: bool = False
):
    """Boucle principale d'extraction ordonnée avec barre de suivi."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifeste introuvable : {MANIFEST_PATH}")

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifeste_global = json.load(f)

    queue_key = f"queue_{annee}"
    candidats = manifeste_global.get(queue_key, [])
    if not candidats:
        logger.error(f"Aucune file d'attente trouvée pour l'année {annee}.")
        return

    # Filtrage par mois si spécifié
    if mois_filtre:
        mois_str = str(mois_filtre).zfill(2)
        candidats = [q for q in candidats if q.get("mois") == mois_str]
        logger.info(f"Filtre appliqué : Mois {mois_str} ({len(candidats)} quotidiens).")

    if limite:
        candidats = candidats[:limite]
        logger.info(f"Limite appliquée : {len(candidats)} quotidiens.")

    conn = sqlite3.connect(DB_PATH)
    deja_extraits = get_existing_bulletins(conn) if not forcer else set()
    logger.info(f"Bulletins déjà enregistrés en base : {len(deja_extraits)}.")

    total_quotidiens = len(candidats)
    recent_alerts = []
    t_start = time.time()

    print("\n" + "=" * 80)
    print(f"DÉMARRAGE DE L'EXTRACTION CONTINUE RÉSULTATS [{annee}] VIA FREELLMAPI")
    print(f"Nombre de Quotidiens à traiter : {total_quotidiens}")
    print("=" * 80 + "\n")

    for idx, q in enumerate(candidats, 1):
        num = q["numero"]
        b_name = q.get("bulletin_nom") or f"Quotidien {num}"
        mois = q.get("mois", "??")
        date_parution = q.get("date_parution")
        sections = q.get("sections", {})

        # Vérifier si déjà en base
        if b_name in deja_extraits and not forcer:
            metrics = get_db_metrics(conn)
            p_bar = render_progress_bar(idx, total_quotidiens)
            print(f"\r{p_bar} | {idx}/{total_quotidiens} | {b_name} [DÉJÀ EN BASE - IGNORÉ] | Base: {metrics['marches']} M, {metrics['lots']} L", end="", flush=True)
            continue

        print(f"\n>>> Traitement [{idx}/{total_quotidiens}] : {b_name} (Mois {mois}) - {len(sections)} section(s)...")

        total_marches_ce_bulletin = 0
        for sec_name, sec_info in sections.items():
            pdf_path = Path(sec_info["pdf_path"])
            logger.info(f"  -> Extraction section {sec_name.upper()} : {pdf_path.name} ({sec_info.get('nb_pages', 0)} pages)...")
            saved_ids = traiter_section_pdf(pdf_path, b_name, date_parution, conn)
            total_marches_ce_bulletin += len(saved_ids)

        # Récupération des métriques et mise à jour de la barre et du fichier JSON
        metrics = get_db_metrics(conn)
        elapsed = time.time() - t_start

        # Export automatique vers le front (web/app/assets/data_resultats.js)
        try:
            import export_resultats_to_front
            export_resultats_to_front.main()
        except Exception as e_exp:
            logger.warning(f"Erreur export front auto : {e_exp}")

        update_progression_json(
            state="EN_COURS",
            annee=annee,
            current_idx=idx,
            total_quotidiens=total_quotidiens,
            current_bulletin=b_name,
            metrics=metrics,
            elapsed_sec=elapsed,
            recent_alerts=recent_alerts
        )

        p_bar = render_progress_bar(idx, total_quotidiens)
        speed = round((idx / (elapsed / 60)), 1) if elapsed > 5 else 0
        print(f"{p_bar} | {idx}/{total_quotidiens} | {b_name} (+{total_marches_ce_bulletin} marchés) | Total base: {metrics['marches']} M, {metrics['lots']} L, {metrics['soumissionnaires']} S | Alertes: {metrics['alertes']} | Vitesse: {speed} q/min\n")

    # Finalisation
    elapsed = time.time() - t_start
    metrics = get_db_metrics(conn)
    update_progression_json(
        state="TERMINE",
        annee=annee,
        current_idx=total_quotidiens,
        total_quotidiens=total_quotidiens,
        current_bulletin="TOUS_TRAITES",
        metrics=metrics,
        elapsed_sec=elapsed,
        recent_alerts=recent_alerts
    )
    conn.close()

    print("\n" + "=" * 80)
    print("EXTRACTION ET CONTRÔLE TERMINÉS AVEC SUCCÈS")
    print(f"Durée totale : {datetime.timedelta(seconds=int(elapsed))}")
    print(f"Métriques finales : {metrics['marches']} marchés, {metrics['lots']} lots, {metrics['soumissionnaires']} soumissionnaires")
    print(f"Alertes d'incertitude relevées : {metrics['alertes']}")
    print(f"Anomalies arithmétiques relevées : {metrics['anomalies']}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestrateur d'extraction continue avec suivi et alertes.")
    parser.add_argument("--annee", default="2026", help="Année à traiter (2026 ou 2025)")
    parser.add_argument("--mois", default=None, help="Filtrer sur un mois spécifique (ex: 10 ou 11)")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max de quotidiens à traiter")
    parser.add_argument("--force", action="store_true", help="Forcer le retraitement des bulletins déjà en base")
    args = parser.parse_args()

    lancer_orchestration(
        annee=args.annee,
        mois_filtre=args.mois,
        limite=args.limit,
        forcer=args.force
    )
