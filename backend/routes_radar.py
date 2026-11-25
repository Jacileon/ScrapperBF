#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_radar.py — Radar concurrent : surveiller des entreprises
et être alerté quand elles remportent un marché (notifications type 'radar').
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api/radar", tags=["radar"])


class RadarIn(BaseModel):
    entreprise_nom: str


@router.get("")
def list_radar(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        noms = [r["entreprise_nom"] for r in conn.execute(
            "SELECT entreprise_nom FROM radar_concurrents WHERE user_id = ? ORDER BY cree_le DESC",
            (user["id"],),
        ).fetchall()]
        out = []
        for nom in noms:
            stats = conn.execute(
                """SELECT COUNT(*) AS wins,
                          COALESCE(SUM(CASE WHEN est_attributaire=1 THEN 1 ELSE 0 END),0) AS gagnes
                   FROM resultats_soumissionnaires WHERE nom_canonique = ?""",
                (nom,),
            ).fetchone()
            last = conn.execute(
                """SELECT m.objet, m.date_parution AS date, m.annonce_avis_id AS avis_id
                   FROM resultats_soumissionnaires s
                   JOIN resultats_marches m ON m.id = s.resultat_id
                   WHERE s.nom_canonique = ? AND s.est_attributaire = 1
                   ORDER BY m.date_extraction DESC LIMIT 1""",
                (nom,),
            ).fetchone()
            out.append({
                "entreprise_nom": nom,
                "soumissions": stats["wins"] or 0,
                "marches_gagnes": stats["gagnes"] or 0,
                "dernier_gain": dict(last) if last else None,
            })
        return {"results": out, "total": len(out)}
    finally:
        conn.close()


@router.get("/ids")
def radar_ids(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        return [r[0] for r in conn.execute(
            "SELECT entreprise_nom FROM radar_concurrents WHERE user_id = ?", (user["id"],)
        ).fetchall()]
    finally:
        conn.close()


@router.post("")
def add_radar(body: RadarIn, user: dict = Depends(require_user)):
    nom = (body.entreprise_nom or "").strip()
    if len(nom) < 2:
        raise HTTPException(status_code=400, detail="Nom d'entreprise invalide.")
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM resultats_soumissionnaires WHERE nom_canonique = ? LIMIT 1", (nom,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Entreprise introuvable dans l'historique.")
        conn.execute(
            "INSERT OR IGNORE INTO radar_concurrents (user_id, entreprise_nom) VALUES (?, ?)",
            (user["id"], nom),
        )
        conn.commit()
        return {"ok": True, "entreprise_nom": nom}
    finally:
        conn.close()


@router.delete("/{entreprise_nom}")
def remove_radar(entreprise_nom: str, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM radar_concurrents WHERE user_id = ? AND entreprise_nom = ?",
            (user["id"], entreprise_nom),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
