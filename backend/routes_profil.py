#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_profil.py
========================
Profil de candidature, scoring « Mes chances », fil personnalisé et
tableau de bord personnel de l'utilisateur.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import get_current_user_optional, require_user
from backend.scoring import score_marche

router = APIRouter(prefix="/api", tags=["profil"])


# --------------------------------------------------------------------------- #
# Profil de candidature
# --------------------------------------------------------------------------- #
class ProfilIn(BaseModel):
    secteurs: Optional[List[str]] = None
    region: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    agrements: Optional[str] = None
    anciennete_annees: Optional[int] = None
    en_groupement: Optional[bool] = None
    marches_soumis: Optional[int] = None
    marches_gagnes: Optional[int] = None


def _load_profil(conn, user_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM profils_candidature WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["secteurs"] = json.loads(d.get("secteurs") or "[]")
    except Exception:
        d["secteurs"] = []
    d["en_groupement"] = bool(d.get("en_groupement"))
    return d


@router.get("/profil")
def get_profil(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        p = _load_profil(conn, user["id"])
        return {"profil": p, "complet": bool(p and p.get("secteurs"))}
    finally:
        conn.close()


@router.put("/profil")
def put_profil(body: ProfilIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        secteurs_json = json.dumps(body.secteurs or [], ensure_ascii=False)
        conn.execute(
            """INSERT INTO profils_candidature
                 (user_id, secteurs, region, budget_min, budget_max, agrements,
                  anciennete_annees, en_groupement, marches_soumis, marches_gagnes, maj_le)
               VALUES (?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                 secteurs=excluded.secteurs, region=excluded.region,
                 budget_min=excluded.budget_min, budget_max=excluded.budget_max,
                 agrements=excluded.agrements, anciennete_annees=excluded.anciennete_annees,
                 en_groupement=excluded.en_groupement, marches_soumis=excluded.marches_soumis,
                 marches_gagnes=excluded.marches_gagnes, maj_le=CURRENT_TIMESTAMP""",
            (user["id"], secteurs_json, body.region, body.budget_min, body.budget_max,
             body.agrements, body.anciennete_annees, int(bool(body.en_groupement)),
             body.marches_soumis or 0, body.marches_gagnes or 0),
        )
        conn.commit()
        return {"ok": True, "profil": _load_profil(conn, user["id"])}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Scoring « Mes chances »
# --------------------------------------------------------------------------- #
@router.get("/scoring/{avis_id}")
def get_scoring(avis_id: str, request: Request):
    user = get_current_user_optional(request)
    conn = get_db()
    try:
        avis = conn.execute("SELECT * FROM annonces_avis WHERE id = ?", (avis_id,)).fetchone()
        if not avis:
            raise HTTPException(status_code=404, detail="Marché introuvable.")
        profil = _load_profil(conn, user["id"]) if user else None
        return score_marche(conn, dict(avis), profil)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Fil personnalisé « fait pour moi »
# --------------------------------------------------------------------------- #
def _days_left(date_limite: Optional[str]) -> Optional[int]:
    if not date_limite:
        return None
    try:
        d = datetime.strptime(date_limite.strip()[:10], "%d/%m/%Y")
        return (d.date() - datetime.now().date()).days
    except Exception:
        return None


@router.get("/moi/fil")
def fil_personnalise(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        profil = _load_profil(conn, user["id"])
        if not profil or not profil.get("secteurs"):
            return {"profil_requis": True, "results": []}
        secteurs = profil["secteurs"]
        placeholders = ",".join("?" * len(secteurs))
        params = list(secteurs)
        budget_sql = ""
        if profil.get("budget_min"):
            budget_sql += " AND budget_previsionnel_fcfa >= ?"; params.append(profil["budget_min"])
        if profil.get("budget_max"):
            budget_sql += " AND budget_previsionnel_fcfa <= ?"; params.append(profil["budget_max"])
        rows = conn.execute(
            f"""SELECT id, objet_marche AS objet, autorite_contractante AS autorite,
                       secteur_activite AS secteur, type_procedure AS type,
                       date_limite_depot AS date_limite, budget_previsionnel_fcfa AS budget
                FROM annonces_avis
                WHERE secteur_activite IN ({placeholders}) {budget_sql}
                ORDER BY rowid DESC LIMIT 400""",
            params,
        ).fetchall()
        # Garder les marchés dont la date limite est future (ou inconnue), trier par urgence
        out = []
        for r in rows:
            d = dict(r)
            dl = _days_left(d["date_limite"])
            d["jours_restants"] = dl
            if dl is None or dl >= 0:
                out.append(d)
        out.sort(key=lambda x: (x["jours_restants"] is None, x["jours_restants"] if x["jours_restants"] is not None else 9999))
        return {"profil_requis": False, "total": len(out), "results": out[:40]}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Tableau de bord personnel
# --------------------------------------------------------------------------- #
@router.get("/moi/stats")
def mes_stats(user: dict = Depends(require_user)):
    conn = get_db()
    uid = user["id"]
    try:
        suivis = conn.execute("SELECT COUNT(*) FROM suivis WHERE user_id=?", (uid,)).fetchone()[0]
        radar = conn.execute("SELECT COUNT(*) FROM radar_concurrents WHERE user_id=?", (uid,)).fetchone()[0]
        non_lus = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND lu=0", (uid,)).fetchone()[0]
        dstats = {r["statut"]: r["n"] for r in conn.execute(
            "SELECT statut, COUNT(*) AS n FROM dossiers WHERE user_id=? GROUP BY statut", (uid,)
        ).fetchall()}
        deposes = (dstats.get("depose", 0) + dstats.get("gagne", 0) + dstats.get("perdu", 0))
        gagnes = dstats.get("gagne", 0)
        taux = round(100.0 * gagnes / deposes) if deposes else None
        return {
            "suivis": suivis,
            "radar": radar,
            "notifications_non_lues": non_lus,
            "dossiers": dstats,
            "soumissions": deposes,
            "gagnes": gagnes,
            "taux_reussite": taux,
        }
    finally:
        conn.close()
