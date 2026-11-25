#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/alertes_resultats.py
============================
Alerte « boucle fermée » : quand un marché suivi (favori) est attribué, on
génère une notification pour l'utilisateur, avec un débrief (gagnant, montant,
nombre d'offres, écart au budget prévisionnel) et un miroir si l'utilisateur
avait indiqué « je soumissionne ».

Le lien marché → résultat se fait via resultats_marches.annonce_avis_id
(clé étrangère vers annonces_avis.id), renseignée par le pipeline d'extraction.

- generate_for_user(user_id) : génère les notifications manquantes pour UN
  utilisateur (appelé paresseusement à l'ouverture du fil → feedback immédiat).
- generate_all() : balaye tous les suivis (pour un cron quotidien).
"""

from __future__ import annotations

import json

from backend.db import get_db


def _fmt_fcfa(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ") + " FCFA"
    except Exception:
        return "—"


def _summarize(conn, resultat: dict) -> dict:
    """Résume un résultat (gagnants, montant, nb d'offres, infructueux)."""
    rid = resultat["id"]
    lots = [dict(r) for r in conn.execute(
        "SELECT * FROM resultats_lots WHERE resultat_id = ? ORDER BY numero_lot", (rid,)
    ).fetchall()]
    nb_offres = conn.execute(
        "SELECT COUNT(*) FROM resultats_soumissionnaires WHERE resultat_id = ?", (rid,)
    ).fetchone()[0]

    gagnants = []
    montant_total = 0
    nb_infructueux = 0
    for lot in lots:
        if lot.get("est_infructueux"):
            nb_infructueux += 1
            continue
        nom = (lot.get("attributaire_nom") or "").strip()
        if not nom:
            w = conn.execute(
                """SELECT COALESCE(nom_canonique, nom_soumissionnaire) AS n
                   FROM resultats_soumissionnaires
                   WHERE resultat_id = ? AND est_attributaire = 1 LIMIT 1""",
                (rid,),
            ).fetchone()
            nom = (w["n"] if w else "") or ""
        mt = lot.get("montant_attribue_max_fcfa") or lot.get("montant_attribue_min_fcfa") or 0
        if mt:
            montant_total += mt
        if nom:
            gagnants.append({"nom": nom, "montant": mt, "lot": lot.get("numero_lot")})

    # Repli : aucun lot détaillé → attributaire global
    if not lots:
        w = conn.execute(
            """SELECT COALESCE(nom_canonique, nom_soumissionnaire) AS n,
                      COALESCE(montant_corrige_ttc_max, montant_corrige_ttc_min,
                               montant_lu_ttc_max, montant_lu_ttc_min, 0) AS mt
               FROM resultats_soumissionnaires
               WHERE resultat_id = ? AND est_attributaire = 1 LIMIT 1""",
            (rid,),
        ).fetchone()
        if w and w["n"]:
            gagnants.append({"nom": w["n"], "montant": w["mt"] or 0, "lot": None})
            montant_total += (w["mt"] or 0)

    infructueux = (len(lots) > 0 and nb_infructueux == len(lots))
    return {
        "resultat_id": rid,
        "objet": resultat.get("objet"),
        "autorite": resultat.get("autorite_contractante"),
        "date": resultat.get("date_parution") or resultat.get("date_deliberation"),
        "nb_lots": len(lots) or (resultat.get("nombre_lots") or 1),
        "nb_offres": nb_offres,
        "gagnants": gagnants,
        "montant_total": montant_total,
        "infructueux": infructueux,
    }


def _build(conn, suivi: dict, resultat: dict) -> dict:
    """Construit titre, message et payload d'une notification de résultat."""
    s = _summarize(conn, resultat)
    avis_id = suivi["avis_id"]
    av = conn.execute(
        "SELECT objet_marche, budget_previsionnel_fcfa FROM annonces_avis WHERE id = ?",
        (avis_id,),
    ).fetchone()
    budget = av["budget_previsionnel_fcfa"] if av else None
    objet = s["objet"] or (av["objet_marche"] if av else "votre marché suivi")

    titre = "Résultat publié"
    if s["infructueux"]:
        message = "Le marché que vous suiviez a été déclaré infructueux."
    elif s["gagnants"]:
        g0 = s["gagnants"][0]
        if len(s["gagnants"]) == 1:
            bout_montant = (" pour " + _fmt_fcfa(g0["montant"])) if g0["montant"] else ""
            bout_offres = (
                " · " + str(s["nb_offres"]) + " offre" + ("s" if s["nb_offres"] > 1 else "")
                if s["nb_offres"] else ""
            )
            message = "Attribué à " + g0["nom"] + bout_montant + bout_offres + "."
        else:
            bout = (" (" + _fmt_fcfa(g0["montant"]) + ")") if g0["montant"] else ""
            message = str(len(s["gagnants"])) + " lots attribués — dont " + g0["nom"] + bout + "."
    else:
        message = "Le résultat de ce marché vient d'être publié."

    debrief = None
    if not s["infructueux"] and s["montant_total"] and budget:
        ecart = round(100.0 * (s["montant_total"] - budget) / budget)
        signe = "+" if ecart > 0 else ""
        debrief = (
            "Montant retenu " + _fmt_fcfa(s["montant_total"])
            + " · budget prévisionnel " + _fmt_fcfa(budget)
            + " (" + signe + str(ecart) + "%)."
        )

    miroir = None
    if suivi.get("statut") == "je_soumissionne":
        miroir = "Vous aviez indiqué « je soumissionne » sur ce marché."

    payload = {
        "objet": objet,
        "autorite": s["autorite"],
        "date": s["date"],
        "gagnants": s["gagnants"],
        "montant_total": s["montant_total"],
        "nb_offres": s["nb_offres"],
        "nb_lots": s["nb_lots"],
        "infructueux": s["infructueux"],
        "budget_previsionnel": budget,
        "debrief": debrief,
        "miroir": miroir,
    }
    return {"titre": titre, "message": message, "payload": payload, "resultat_id": s["resultat_id"]}


def generate_for_user(user_id: int) -> int:
    """Génère les notifications de résultat manquantes pour un utilisateur."""
    conn = get_db()
    created = 0
    try:
        suivis = [dict(r) for r in conn.execute(
            "SELECT * FROM suivis WHERE user_id = ? AND statut != 'abandonne'", (user_id,)
        ).fetchall()]
        for s in suivis:
            results = [dict(r) for r in conn.execute(
                "SELECT * FROM resultats_marches WHERE annonce_avis_id = ?", (s["avis_id"],)
            ).fetchall()]
            for r in results:
                exists = conn.execute(
                    "SELECT 1 FROM notifications WHERE user_id=? AND type='resultat' AND resultat_id=?",
                    (user_id, r["id"]),
                ).fetchone()
                if exists:
                    continue
                n = _build(conn, s, r)
                conn.execute(
                    """INSERT OR IGNORE INTO notifications
                       (user_id, type, avis_id, resultat_id, titre, message, payload_json)
                       VALUES (?, 'resultat', ?, ?, ?, ?, ?)""",
                    (user_id, s["avis_id"], n["resultat_id"], n["titre"], n["message"],
                     json.dumps(n["payload"], ensure_ascii=False)),
                )
                created += 1
        conn.commit()
    finally:
        conn.close()
    return created


def generate_all() -> int:
    """Balaye tous les suivis (cron). Renvoie le nombre de notifications créées."""
    conn = get_db()
    try:
        uids = [r[0] for r in conn.execute(
            "SELECT DISTINCT user_id FROM suivis WHERE statut != 'abandonne'"
        ).fetchall()]
    finally:
        conn.close()
    total = 0
    for uid in uids:
        total += generate_for_user(uid)
    return total


if __name__ == "__main__":
    n = generate_all()
    print(f"[alertes_resultats] {n} notification(s) generee(s).")
