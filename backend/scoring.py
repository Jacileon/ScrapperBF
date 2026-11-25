#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scoring.py
==================
Scoring « Mes chances » GO / NO GO, et sa preuve (attributions comparables).

Principe : on n'invente rien. Les indicateurs (concurrents attendus, zone de
prix, montant probable) sont calculés à partir des **attributions réelles de
marchés comparables** déjà en base (resultats_marches / resultats_lots), et le
score est une heuristique transparente combinant ces faits et le profil de
l'entreprise. Honnêteté assumée : rien n'est une certitude (voir `disclaimer`).
"""

from __future__ import annotations

from statistics import mean, median
from typing import Optional

# Seuils de verdict
GO_MIN = 70
ETUDE_MIN = 50

DISCLAIMER = ("Estimation indicative calculée sur des marchés comparables déjà "
             "attribués. Ce n'est pas une prévision certaine : vérifiez toujours "
             "le dossier d'appel d'offres avant de décider.")


def _amount(row) -> Optional[int]:
    return row["mt_max"] or row["mt_min"]


def _percentiles(values: list[int]) -> dict:
    if not values:
        return {"min": None, "q1": None, "median": None, "q3": None, "max": None}
    s = sorted(values)
    n = len(s)
    def pick(p):
        if n == 1:
            return s[0]
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return s[idx]
    return {"min": s[0], "q1": pick(0.25), "median": int(median(s)),
            "q3": pick(0.75), "max": s[-1]}


def _comparables(conn, secteur: Optional[str], autorite: Optional[str], limit: int = 400) -> list[dict]:
    """Lots attribués (non infructueux, montant connu) du même secteur."""
    if not secteur:
        return []
    rows = conn.execute(
        """
        SELECT l.montant_attribue_max_fcfa AS mt_max,
               l.montant_attribue_min_fcfa AS mt_min,
               l.nombre_plis_recus          AS plis,
               l.attributaire_nom           AS gagnant,
               m.objet AS objet, m.autorite_contractante AS autorite,
               m.date_parution AS date, m.annonce_avis_id AS avis_id,
               m.id AS resultat_id
        FROM resultats_lots l
        JOIN resultats_marches m ON m.id = l.resultat_id
        WHERE COALESCE(l.est_infructueux, 0) = 0
          AND (l.montant_attribue_max_fcfa IS NOT NULL OR l.montant_attribue_min_fcfa IS NOT NULL)
          AND m.secteur_activite = ?
        ORDER BY (m.autorite_contractante = ?) DESC, m.date_extraction DESC
        LIMIT ?
        """,
        (secteur, autorite or "", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _taux_infructueux(conn, secteur: Optional[str]) -> Optional[float]:
    if not secteur:
        return None
    row = conn.execute(
        """SELECT SUM(CASE WHEN COALESCE(l.est_infructueux,0)=1 THEN 1 ELSE 0 END) AS infr,
                  COUNT(*) AS tot
           FROM resultats_lots l JOIN resultats_marches m ON m.id = l.resultat_id
           WHERE m.secteur_activite = ?""",
        (secteur,),
    ).fetchone()
    if not row or not row["tot"]:
        return None
    return round(100.0 * (row["infr"] or 0) / row["tot"])


def score_marche(conn, avis: dict, profil: Optional[dict] = None) -> dict:
    """Calcule le scoring d'un marché (avis = ligne annonces_avis sous forme dict)."""
    secteur = avis.get("secteur_activite")
    autorite = avis.get("autorite_contractante")
    budget = avis.get("budget_previsionnel_fcfa")

    comps = _comparables(conn, secteur, autorite)
    amounts = [a for a in (_amount(r) for r in comps) if a]
    plis = [r["plis"] for r in comps if r["plis"]]

    nb_concurrents = round(mean(plis)) if plis else None
    prix = _percentiles(amounts)
    montant_probable = prix["median"]
    taux_infr = _taux_infructueux(conn, secteur)

    # Preuve : 5 attributions comparables récentes (priorité même autorité)
    comparables_preuve = []
    for r in comps[:5]:
        comparables_preuve.append({
            "objet": r["objet"], "autorite": r["autorite"], "gagnant": r["gagnant"],
            "montant": _amount(r), "plis": r["plis"], "date": r["date"],
            "avis_id": r["avis_id"],
        })

    # --- Heuristique de score ---
    score = 50.0
    forts, vigilance = [], []
    personnalise = bool(profil)

    if profil:
        secteurs_profil = profil.get("secteurs") or []
        if secteur and secteurs_profil:
            if secteur in secteurs_profil:
                score += 15; forts.append("Le marché est dans votre secteur d'activité.")
            else:
                score -= 10; vigilance.append("Hors de vos secteurs déclarés.")
        # Agrément
        requis_agr = bool((avis.get("qualifications_ou_agrement") or "").lower().find("agr") >= 0)
        a_agr = bool((profil.get("agrements") or "").strip())
        if requis_agr:
            if a_agr:
                score += 8; forts.append("Vous déclarez un agrément, exigé par ce marché.")
            else:
                score -= 18; vigilance.append("Un agrément semble exigé — vérifiez que vous l'avez.")
        # Budget
        bmin, bmax = profil.get("budget_min"), profil.get("budget_max")
        if budget and (bmin or bmax):
            if (not bmin or budget >= bmin) and (not bmax or budget <= bmax):
                score += 8; forts.append("Le montant est dans votre fourchette habituelle.")
            else:
                score -= 6; vigilance.append("Le montant sort de votre fourchette habituelle.")
        if (profil.get("marches_gagnes") or 0) > 0:
            score += 5; forts.append("Votre historique de marchés gagnés joue en votre faveur.")

    # Concurrence attendue
    if nb_concurrents is not None:
        if nb_concurrents <= 2:
            score += 10; forts.append(f"Peu de concurrents attendus (~{nb_concurrents}).")
        elif nb_concurrents <= 4:
            score += 4
        elif nb_concurrents >= 8:
            score -= 6; vigilance.append(f"Forte concurrence attendue (~{nb_concurrents} offres).")
        else:
            vigilance.append(f"Concurrence modérée (~{nb_concurrents} offres).")

    # Taux d'infructueux du secteur
    if taux_infr is not None and taux_infr >= 25:
        score -= 5
        vigilance.append(f"{taux_infr}% des lots de ce secteur finissent infructueux.")

    # Données disponibles
    if len(comps) < 5:
        vigilance.append("Peu de marchés comparables en base : estimation fragile.")

    score = int(max(5, min(95, round(score))))
    if score >= GO_MIN:
        verdict, verdict_label = "GO", "Favorable"
    elif score >= ETUDE_MIN:
        verdict, verdict_label = "ETUDE", "À étudier"
    else:
        verdict, verdict_label = "NOGO", "Risqué"

    if not forts:
        forts.append("Marché ouvert : à évaluer selon votre capacité.")

    return {
        "avis_id": avis.get("id"),
        "score": score,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "personnalise": personnalise,
        "concurrents_attendus": nb_concurrents,
        "zone_prix": prix,
        "montant_probable": montant_probable,
        "budget_previsionnel": budget,
        "taux_infructueux_secteur": taux_infr,
        "nb_comparables": len(comps),
        "points_forts": forts,
        "points_vigilance": vigilance,
        "comparables": comparables_preuve,
        "disclaimer": DISCLAIMER,
    }
