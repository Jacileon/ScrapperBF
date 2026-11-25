#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/intelligence.py
=======================
Intelligence de marché calculée depuis l'historique réel (resultats_*) :
  - indice de fiabilité / concentration par autorité contractante
  - prix gagnants réels (fourchettes) par secteur / type
  - tendances « temps réel » (snapshot de l'activité courante)
  - veille prédictive : marchés récurrents attendus
"""

from __future__ import annotations

from typing import Optional

from backend.scoring import _percentiles

_IGNORE_NOMS = (
    "NON", "OUI", "NEANT", "NÉANT", "RAS", "N/A", "NA", "INCONNU", "ATTRIBUTAIRE",
)


def autorite_intel(conn, nom: str) -> dict:
    """Indice de fiabilité & concentration d'une autorité contractante."""
    nom = (nom or "").strip()
    publies = conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(budget_previsionnel_fcfa),0) AS budget
           FROM annonces_avis WHERE autorite_contractante = ?""", (nom,)
    ).fetchone()
    lots = conn.execute(
        """SELECT COUNT(*) AS tot,
                  SUM(CASE WHEN COALESCE(l.est_infructueux,0)=1 THEN 1 ELSE 0 END) AS infr,
                  COUNT(DISTINCT l.attributaire_nom) AS entreprises,
                  COALESCE(SUM(COALESCE(l.montant_attribue_max_fcfa,l.montant_attribue_min_fcfa,0)),0) AS montant
           FROM resultats_lots l JOIN resultats_marches m ON m.id=l.resultat_id
           WHERE m.autorite_contractante = ?""", (nom,)
    ).fetchone()
    tot_lots = lots["tot"] or 0
    taux_infr = round(100.0 * (lots["infr"] or 0) / tot_lots) if tot_lots else None

    gagnants = [dict(r) for r in conn.execute(
        """SELECT l.attributaire_nom AS nom, COUNT(*) AS wins,
                  COALESCE(SUM(COALESCE(l.montant_attribue_max_fcfa,l.montant_attribue_min_fcfa,0)),0) AS montant
           FROM resultats_lots l JOIN resultats_marches m ON m.id=l.resultat_id
           WHERE m.autorite_contractante = ? AND COALESCE(l.est_infructueux,0)=0
                 AND l.attributaire_nom IS NOT NULL AND TRIM(l.attributaire_nom) <> ''
           GROUP BY l.attributaire_nom ORDER BY wins DESC LIMIT 8""", (nom,)
    ).fetchall()]
    total_wins = sum(g["wins"] for g in gagnants)
    concentration = round(100.0 * sum(g["wins"] for g in gagnants[:3]) / total_wins) if total_wins else None

    # Indice de fiabilité (0-100) : pénalise infructueux élevé et forte concentration.
    indice = 100
    if taux_infr is not None:
        indice -= min(40, taux_infr)
    if concentration is not None and concentration >= 60:
        indice -= min(30, concentration - 50)
    indice = max(0, min(100, indice))

    return {
        "autorite": nom,
        "marches_publies": publies["n"] or 0,
        "budget_publie": publies["budget"] or 0,
        "lots_attribues": tot_lots,
        "taux_infructueux": taux_infr,
        "nb_entreprises": lots["entreprises"] or 0,
        "montant_total_attribue": lots["montant"] or 0,
        "concentration_top3": concentration,
        "indice_fiabilite": indice,
        "top_attributaires": gagnants,
    }


def prix_intel(conn, secteur: str, type_marche: Optional[str] = None) -> dict:
    """Fourchettes de prix réellement attribués pour un secteur (+ type)."""
    params = [secteur]
    type_sql = ""
    if type_marche:
        type_sql = " AND m.objet LIKE ?"  # pas de type sur résultats : filtre léger via objet
        params.append(f"%{type_marche}%")
    rows = conn.execute(
        f"""SELECT COALESCE(l.montant_attribue_max_fcfa,l.montant_attribue_min_fcfa) AS mt
            FROM resultats_lots l JOIN resultats_marches m ON m.id=l.resultat_id
            WHERE COALESCE(l.est_infructueux,0)=0 AND m.secteur_activite = ? {type_sql}
                  AND COALESCE(l.montant_attribue_max_fcfa,l.montant_attribue_min_fcfa) IS NOT NULL""",
        params,
    ).fetchall()
    amounts = [r["mt"] for r in rows if r["mt"]]
    return {
        "secteur": secteur,
        "nb_marches": len(amounts),
        "fourchette": _percentiles(amounts),
    }


def tendances(conn) -> dict:
    """Snapshot de l'activité courante (vivant, pas mensuel)."""
    par_secteur = [dict(r) for r in conn.execute(
        """SELECT COALESCE(secteur_activite,'Autre') AS secteur, COUNT(*) AS n,
                  COALESCE(SUM(budget_previsionnel_fcfa),0) AS budget
           FROM annonces_avis GROUP BY 1 ORDER BY n DESC LIMIT 15"""
    ).fetchall()]
    top_autorites = [dict(r) for r in conn.execute(
        """SELECT autorite_contractante AS autorite, COUNT(*) AS n
           FROM annonces_avis WHERE autorite_contractante IS NOT NULL AND TRIM(autorite_contractante)<>''
           GROUP BY 1 ORDER BY n DESC LIMIT 10"""
    ).fetchall()]
    tot = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(budget_previsionnel_fcfa),0) AS b FROM annonces_avis").fetchone()
    res_par_annee = [dict(r) for r in conn.execute(
        """SELECT annee, COUNT(*) AS n FROM resultats_marches
           WHERE annee IS NOT NULL GROUP BY annee ORDER BY annee DESC LIMIT 5"""
    ).fetchall()]
    return {
        "marches_ouverts": tot["n"] or 0,
        "budget_total": tot["b"] or 0,
        "par_secteur": par_secteur,
        "top_autorites": top_autorites,
        "resultats_par_annee": res_par_annee,
    }


def predictions(conn, limit: int = 30) -> dict:
    """Marchés récurrents : (autorité, secteur) qui reviennent souvent dans l'historique."""
    rows = conn.execute(
        """SELECT m.autorite_contractante AS autorite, m.secteur_activite AS secteur,
                  COUNT(DISTINCT m.id) AS occurrences,
                  COUNT(DISTINCT m.annee) AS annees,
                  MAX(m.objet) AS dernier_objet
           FROM resultats_marches m
           WHERE m.autorite_contractante IS NOT NULL AND TRIM(m.autorite_contractante) <> ''
                 AND m.secteur_activite IS NOT NULL AND TRIM(m.secteur_activite) <> ''
           GROUP BY m.autorite_contractante, m.secteur_activite
           HAVING occurrences >= 3
           ORDER BY annees DESC, occurrences DESC
           LIMIT ?""", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["confiance"] = "élevée" if (d["annees"] or 0) >= 2 and (d["occurrences"] or 0) >= 5 else "moyenne"
        out.append(d)
    return {
        "total": len(out),
        "predictions": out,
        "note": ("Marchés que cette autorité a déjà passés plusieurs fois dans ce "
                 "secteur — susceptibles de revenir. Signal indicatif, pas une garantie."),
    }
