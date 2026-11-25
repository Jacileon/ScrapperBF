#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voir_progression.py
===================
Tableau de bord dynamique pour suivre en temps réel la progression
de l'extraction des RÉSULTATS d'attribution pour les deux années :
  - Année 2026 (FreeLLMAPI - Flux continu en arrière-plan)
  - Année 2025 (Agent IA - Analyse cognitive approfondie à haute précision)

Usage :
    python voir_progression.py            # Affichage instantané (one-shot)
    python voir_progression.py --watch    # Mode live animé avec rafraîchissement auto
    python voir_progression.py --json     # Export JSON des métriques
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

DB_PATH = Path("marches_publics_burkina.db")
MANIFESTE_PATH = Path("manifeste_complet_resultats.json")
PROGRESSION_LLM_PATH = Path("progression_resultats.json")
TASKS_DIR = Path(r"C:\Users\DANIEL\.gemini\antigravity\brain\92f2df28-0e50-4d7e-bb72-769e47d9d551\.system_generated\tasks")

# Couleurs ANSI
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_RED = "\033[31m"
C_WHITE = "\033[97m"
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def format_fcfa(amount: int) -> str:
    if not amount:
        return "0 FCFA"
    return f"{amount:,.0f} FCFA".replace(",", " ")


def make_progress_bar(current: int, total: int, width: int = 28, color: str = C_GREEN) -> str:
    if total <= 0:
        pct = 0.0
        filled = 0
    else:
        pct = min(100.0, (current / total) * 100.0)
        filled = int((pct / 100.0) * width)
    unfilled = width - filled
    bar = f"{color}{'█' * filled}{C_DIM}{'░' * unfilled}{C_RESET}"
    return f"[{bar}] {C_BOLD}{pct:5.1f}%{C_RESET}"


def get_live_task_status() -> dict:
    status = {
        "2026_activite": "En attente de démarrage...",
        "2025_activite": "En attente de démarrage...",
        "2026_last_update": None,
        "2025_last_update": None
    }

    # 1. Priorité aux indicateurs live en temps réel (fichiers d'état instantanés)
    st26_path = Path("statut_live_2026.json")
    if st26_path.exists():
        try:
            with open(st26_path, "r", encoding="utf-8") as f:
                st = json.load(f)
                mtime = st.get("mtime", os.path.getmtime(st26_path))
                elapsed = int(time.time() - mtime)
                status["2026_activite"] = f"[{st.get('bulletin')}] {st.get('dossier')} : {st.get('emetteur')}"
                status["2026_last_update"] = elapsed
        except Exception:
            pass

    st25_path = Path("statut_live_2025.json")
    if st25_path.exists():
        try:
            with open(st25_path, "r", encoding="utf-8") as f:
                st = json.load(f)
                mtime = st.get("mtime", os.path.getmtime(st25_path))
                elapsed = int(time.time() - mtime)
                status["2025_activite"] = f"[{st.get('bulletin')}] {st.get('section')} {st.get('unite')} : {st.get('emetteur')}"
                status["2025_last_update"] = elapsed
        except Exception:
            pass

    # 2. Scanner dynamiquement les derniers logs de tâches si statut non alimenté
    if TASKS_DIR.exists():
        recent_logs = sorted(TASKS_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)[:8]
        for log_file in recent_logs:
            try:
                mtime = os.path.getmtime(log_file)
                age = int(time.time() - mtime)
                if age > 1800:
                    continue
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                if not lines:
                    continue
                last_line = lines[-1]
                content_sample = " ".join(lines[-10:])
                if ("2026" in content_sample or "orchestrateur" in content_sample) and (status["2026_last_update"] is None or age < status["2026_last_update"]):
                    status["2026_activite"] = last_line
                    status["2026_last_update"] = age
                elif ("2025" in content_sample or "workflow" in content_sample or "[phase]" in content_sample) and (status["2025_last_update"] is None or age < status["2025_last_update"]):
                    status["2025_activite"] = last_line
                    status["2025_last_update"] = age
            except Exception:
                pass

    return status


def collect_metrics() -> dict:
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "2025": {
            "nom": "Année 2025 (Agent IA - Cognitive)",
            "moteur": "Analyse Cognitive Agent (Fidélité 100%)",
            "quotidiens_total": 116,
            "quotidiens_traites": 0,
            "bulletins_liste": [],
            "marches": 0,
            "lots": 0,
            "soumissionnaires": 0,
            "valides": 0,
            "alertes": 0,
            "anomalies": 0,
            "budget_total_fcfa": 0,
            "dernier_bulletin": None
        },
        "2026": {
            "nom": "Année 2026 (FreeLLMAPI - Continu)",
            "moteur": "FreeLLMAPI / Qwen (Tâche de fond continue)",
            "quotidiens_total": 209,
            "quotidiens_traites": 0,
            "bulletins_liste": [],
            "marches": 0,
            "lots": 0,
            "soumissionnaires": 0,
            "valides": 0,
            "alertes": 0,
            "anomalies": 0,
            "budget_total_fcfa": 0,
            "dernier_bulletin": None
        },
        "global": {
            "total_marches": 0,
            "total_lots": 0,
            "total_soumissionnaires": 0,
            "total_budget_fcfa": 0,
            "total_annonces_avis": 0,
            "total_avis_rapproches": 0,
            "derniere_insertion": None,
            "temps_derniere_insertion": None
        },
        "alertes_recentes": [],
        "activite_live": get_live_task_status()
    }

    # 1. Charger les totaux du manifeste
    q25_keys, q26_keys = {}, {}
    if MANIFESTE_PATH.exists():
        try:
            with open(MANIFESTE_PATH, "r", encoding="utf-8") as f:
                man = json.load(f)
            q25 = man.get("queue_2025", [])
            q26 = man.get("queue_2026", [])
            data["2025"]["quotidiens_total"] = len(q25) or 116
            data["2026"]["quotidiens_total"] = len(q26) or 209

            for q in q25:
                q25_keys[q.get("numero", "").upper()] = q
                slug = re.sub(r"[^\w]", "", q.get("bulletin_nom", "")).upper()
                q25_keys[slug] = q

            for q in q26:
                q26_keys[q.get("numero", "").upper()] = q
                slug = re.sub(r"[^\w]", "", q.get("bulletin_nom", "")).upper()
                q26_keys[slug] = q
        except Exception:
            pass

    # 2. Lire la base SQLite
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            c.execute("SELECT count(*) FROM annonces_avis")
            data["global"]["total_annonces_avis"] = c.fetchone()[0]

            c.execute("SELECT count(*) FROM resultats_marches WHERE annonce_avis_id IS NOT NULL")
            data["global"]["total_avis_rapproches"] = c.fetchone()[0]

            # Dernière insertion absolue
            last_m = c.execute("""
                SELECT bulletin, autorite_contractante, id, date_extraction
                FROM resultats_marches
                ORDER BY rowid DESC LIMIT 1
            """).fetchone()

            if last_m:
                data["global"]["derniere_insertion"] = f"{last_m[0]} : {last_m[1][:35]}"
                if last_m[3]:
                    try:
                        dt = datetime.fromisoformat(last_m[3])
                        data["global"]["temps_derniere_insertion"] = int((datetime.now() - dt).total_seconds())
                    except Exception:
                        pass

            rows = c.execute("""
                SELECT m.id, m.bulletin, m.source_file, m.statut_coherence,
                       m.remarques_extracteur, m.budget_previsionnel_max_fcfa,
                       (SELECT count(*) FROM resultats_lots l WHERE l.resultat_id = m.id) as nb_lots,
                       (SELECT count(*) FROM resultats_soumissionnaires s WHERE s.resultat_id = m.id) as nb_soum,
                       m.date_extraction
                FROM resultats_marches m
                ORDER BY m.id
            """).fetchall()

            bulletins_2025 = set()
            bulletins_2026 = set()

            for mid, bull, src, statut, rem, budget, n_lots, n_soum, dt_ext in rows:
                b_slug = re.sub(r"[^\w]", "", bull or "").upper()
                num_match = re.search(r"N\s*(\d{4})", bull or "", re.I)
                num_key = f"N{num_match.group(1)}" if num_match else ""

                is_25 = (num_key in q25_keys or b_slug in q25_keys or (src and "2025" in src))
                is_26 = (num_key in q26_keys or b_slug in q26_keys or (src and "2026" in src))

                yr = "2025" if is_25 else ("2026" if is_26 else None)
                if not yr:
                    if num_match:
                        n = int(num_match.group(1))
                        yr = "2025" if n <= 4250 else "2026"
                    else:
                        yr = "2026"

                st = data[yr]
                st["marches"] += 1
                st["lots"] += (n_lots or 0)
                st["soumissionnaires"] += (n_soum or 0)
                if bull:
                    if yr == "2025":
                        bulletins_2025.add(bull)
                    else:
                        bulletins_2026.add(bull)
                    st["dernier_bulletin"] = bull

                if budget:
                    st["budget_total_fcfa"] += budget

                if statut in ("VALIDE", "CONFORME"):
                    st["valides"] += 1
                elif statut == "ALERTE_INCERTITUDE":
                    st["alertes"] += 1
                elif statut == "ANOMALIE_ARITHMETIQUE":
                    st["anomalies"] += 1

                data["global"]["total_marches"] += 1
                data["global"]["total_lots"] += (n_lots or 0)
                data["global"]["total_soumissionnaires"] += (n_soum or 0)
                if budget:
                    data["global"]["total_budget_fcfa"] += budget

            data["2025"]["quotidiens_traites"] = len(bulletins_2025)
            data["2025"]["bulletins_liste"] = sorted(list(bulletins_2025))
            data["2026"]["quotidiens_traites"] = len(bulletins_2026)
            data["2026"]["bulletins_liste"] = sorted(list(bulletins_2026))

            alertes_rows = c.execute("""
                SELECT bulletin, autorite_contractante, remarques_extracteur, id
                FROM resultats_marches
                WHERE remarques_extracteur IS NOT NULL AND trim(remarques_extracteur) != ''
                ORDER BY rowid DESC LIMIT 4
            """).fetchall()

            for b, aut, rmk, rid in alertes_rows:
                data["alertes_recentes"].append({
                    "id": rid,
                    "bulletin": b,
                    "autorite": aut,
                    "remarque": rmk
                })

            conn.close()
        except Exception as e:
            data["erreur_db"] = str(e)

    return data


def render_dashboard(metrics: dict, clear_screen: bool = False, frame_idx: int = 0):
    if clear_screen:
        os.system("cls" if os.name == "nt" else "clear")

    width = 84
    sep_double = "═" * width
    sep_single = "─" * width
    spinner = SPINNER_FRAMES[frame_idx % len(SPINNER_FRAMES)]

    live = metrics.get("activite_live", {})
    t26_sec = live.get("2026_last_update")
    t25_sec = live.get("2025_last_update")

    t26_str = f"({t26_sec}s ago)" if t26_sec is not None else ""
    t25_str = f"({t25_sec}s ago)" if t25_sec is not None else ""

    out = []
    out.append(f"{C_CYAN}{C_BOLD}{sep_double}")
    out.append(f"  {spinner} TABLEAU DE BORD D'EXTRACTION — SUIVI DYNAMIQUE EN TEMPS RÉEL")
    out.append(f"  Horodatage : {metrics['timestamp']} | ScrapperBF DGCMEF (2025 & 2026)")
    out.append(f"{sep_double}{C_RESET}")

    # Section 2026
    s26 = metrics["2026"]
    bar26 = make_progress_bar(s26["quotidiens_traites"], s26["quotidiens_total"], width=26, color=C_CYAN)

    out.append(f"\n{C_BOLD}{C_CYAN}▶ ANNÉE 2026 (OpenRouter & FreeLLMAPI — Flux Continu Autonome){C_RESET}")
    out.append(f"  Moteur          : {C_WHITE}{s26['moteur']}{C_RESET}")
    out.append(f"  Progression     : {bar26} ({s26['quotidiens_traites']}/{s26['quotidiens_total']} Quotidiens archivés)")
    out.append(f"  En base SQLite  : {C_BOLD}{s26['marches']}{C_RESET} Marchés | {C_BOLD}{s26['lots']}{C_RESET} Lots | {C_BOLD}{s26['soumissionnaires']}{C_RESET} Candidats qualifiés")
    out.append(f"  Audit qualité   : {C_GREEN}✔ {s26['valides']} Conformes{C_RESET}  |  {C_YELLOW}⚠ {s26['alertes']} Alertes de transparence{C_RESET}  |  {C_RED}✖ {s26['anomalies']} Anomalies{C_RESET}")
    out.append(f"  Budget extrait  : {C_WHITE}{format_fcfa(s26['budget_total_fcfa'])}{C_RESET}")
    
    act_26 = live.get("2026_activite", "")
    if len(act_26) > 72:
        act_26 = act_26[:69] + "..."
    out.append(f"  {C_YELLOW}⚡ Activité live {t26_str} : {C_WHITE}{act_26}{C_RESET}")

    # Section 2025
    s25 = metrics["2025"]
    bar25 = make_progress_bar(s25["quotidiens_traites"], s25["quotidiens_total"], width=26, color=C_GREEN)

    out.append(f"\n{C_BOLD}{C_GREEN}▶ ANNÉE 2025 (Agent IA — Analyse Cognitive Directe 100% Fidèle){C_RESET}")
    out.append(f"  Moteur          : {C_WHITE}{s25['moteur']}{C_RESET}")
    out.append(f"  Progression     : {bar25} ({s25['quotidiens_traites']}/{s25['quotidiens_total']} Quotidiens archivés)")
    out.append(f"  En base SQLite  : {C_BOLD}{s25['marches']}{C_RESET} Marchés | {C_BOLD}{s25['lots']}{C_RESET} Lots | {C_BOLD}{s25['soumissionnaires']}{C_RESET} Candidats qualifiés")
    out.append(f"  Audit qualité   : {C_GREEN}✔ {s25['valides']} Conformes{C_RESET}  |  {C_YELLOW}⚠ {s25['alertes']} Alertes de transparence{C_RESET}  |  {C_RED}✖ {s25['anomalies']} Anomalies{C_RESET}")
    out.append(f"  Budget extrait  : {C_WHITE}{format_fcfa(s25['budget_total_fcfa'])}{C_RESET}")
    
    act_25 = live.get("2025_activite", "")
    if len(act_25) > 72:
        act_25 = act_25[:69] + "..."
    out.append(f"  {C_GREEN}⚡ Activité live {t25_str} : {C_WHITE}{act_25}{C_RESET}")

    # Section Consolidation Globale
    g = metrics["global"]
    out.append(f"\n{C_DIM}{sep_single}{C_RESET}")
    out.append(f"{C_BOLD}{C_WHITE}📊 CONSOLIDATION TOTALE BASE SQLite ({DB_PATH.name}){C_RESET}")
    out.append(f"  • Total Marchés Résultats  : {C_BOLD}{g['total_marches']}{C_RESET} (2025: {s25['marches']} | 2026: {s26['marches']})")
    out.append(f"  • Total Lots Résultats     : {C_BOLD}{g['total_lots']}{C_RESET} (2025: {s25['lots']} | 2026: {s26['lots']})")
    out.append(f"  • Total Soumissionnaires   : {C_BOLD}{g['total_soumissionnaires']}{C_RESET} (2025: {s25['soumissionnaires']} | 2026: {s26['soumissionnaires']})")
    out.append(f"  • Montants Prévisionnels   : {C_BOLD}{format_fcfa(g['total_budget_fcfa'])}{C_RESET}")
    if g.get("derniere_insertion"):
        dt_str = f"(il y a {g['temps_derniere_insertion']}s)" if g.get("temps_derniere_insertion") is not None else ""
        out.append(f"  • Dernière écriture en BD  : {C_GREEN}{g['derniere_insertion']} {dt_str}{C_RESET}")

    # Section Alertes Récentes
    if metrics.get("alertes_recentes"):
        out.append(f"\n{C_YELLOW}{C_BOLD}🔔 DERNIÈRES ALERTES / REMARQUES D'INCERTITUDE{C_RESET}")
        for alt in metrics["alertes_recentes"][:3]:
            rmk = alt["remarque"]
            if len(rmk) > 110:
                rmk = rmk[:107] + "..."
            out.append(f"  [{alt['bulletin']}] {C_BOLD}{alt['autorite'][:35]}{C_RESET} : {rmk}")

    out.append(f"{C_CYAN}{sep_double}{C_RESET}")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Suivi comparatif de l'extraction des résultats 2025 & 2026.")
    parser.add_argument("-w", "--watch", action="store_true", help="Mode suivi continu avec rafraîchissement dynamique")
    parser.add_argument("-i", "--interval", type=int, default=2, help="Intervalle de rafraîchissement en secondes (défaut: 2)")
    parser.add_argument("-j", "--json", action="store_true", help="Affiche la sortie au format JSON")

    args = parser.parse_args()

    if args.json:
        metrics = collect_metrics()
        for k in ("2025", "2026"):
            if "bulletins_liste" in metrics[k]:
                metrics[k]["bulletins_liste"] = list(metrics[k]["bulletins_liste"])
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        return

    if args.watch:
        try:
            frame = 0
            while True:
                metrics = collect_metrics()
                print(render_dashboard(metrics, clear_screen=True, frame_idx=frame))
                print(f"{C_DIM}Appuyez sur Ctrl+C pour quitter... Rafraîchissement dynamique toutes les {args.interval}s{C_RESET}")
                frame += 1
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n{C_CYAN}Arrêt du suivi.{C_RESET}")
    else:
        metrics = collect_metrics()
        print(render_dashboard(metrics, clear_screen=False, frame_idx=0))


if __name__ == "__main__":
    main()
