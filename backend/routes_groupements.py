#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_groupements.py — « Tinder des groupements ».
L'utilisateur se déclare ouvert aux groupements ; pour un marché donné, on
propose des partenaires : membres inscrits ouverts dans le secteur + entreprises
historiquement actives dans ce secteur (données publiques).
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api/groupements", tags=["groupements"])


class OptinIn(BaseModel):
    secteurs: Optional[List[str]] = None
    agrements: Optional[str] = None
    contact: Optional[str] = None
    message: Optional[str] = None
    actif: Optional[bool] = True


@router.get("/moi")
def mon_optin(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM groupement_profils WHERE user_id = ?", (user["id"],)).fetchone()
        if not row:
            return {"inscrit": False}
        d = dict(row)
        try:
            d["secteurs"] = json.loads(d.get("secteurs") or "[]")
        except Exception:
            d["secteurs"] = []
        d["actif"] = bool(d.get("actif"))
        d["inscrit"] = True
        return d
    finally:
        conn.close()


@router.put("/moi")
def set_optin(body: OptinIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO groupement_profils (user_id, secteurs, agrements, contact, message, actif)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 secteurs=excluded.secteurs, agrements=excluded.agrements,
                 contact=excluded.contact, message=excluded.message, actif=excluded.actif""",
            (user["id"], json.dumps(body.secteurs or [], ensure_ascii=False), body.agrements,
             body.contact, body.message, int(bool(body.actif))),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/moi")
def delete_optin(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        conn.execute("DELETE FROM groupement_profils WHERE user_id = ?", (user["id"],))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("")
def trouver_partenaires(
    avis_id: Optional[str] = Query(None),
    secteur: Optional[str] = Query(None),
    user: dict = Depends(require_user),
):
    """Partenaires potentiels pour un marché (par secteur)."""
    conn = get_db()
    try:
        sec = secteur
        objet = None
        if avis_id and not sec:
            row = conn.execute(
                "SELECT secteur_activite, objet_marche FROM annonces_avis WHERE id = ?", (avis_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Marché introuvable.")
            sec = row["secteur_activite"]
            objet = row["objet_marche"]
        if not sec:
            raise HTTPException(status_code=400, detail="secteur ou avis_id requis.")

        # 1) Membres inscrits ouverts aux groupements dans ce secteur
        membres = [dict(r) for r in conn.execute(
            """SELECT u.nom, u.organisation, g.contact, g.message, g.agrements
               FROM groupement_profils g JOIN users u ON u.id = g.user_id
               WHERE g.actif = 1 AND g.user_id != ? AND g.secteurs LIKE ?""",
            (user["id"], f'%{sec}%'),
        ).fetchall()]

        # 2) Entreprises du domaine ayant déjà répondu en groupement (partenaires potentiels)
        partenaires_groupement = [dict(r) for r in conn.execute(
            """SELECT s.nom_canonique AS nom,
                      SUM(CASE WHEN s.est_attributaire=1 THEN 1 ELSE 0 END) AS gagnes,
                      COUNT(*) AS soumissions
               FROM resultats_soumissionnaires s JOIN resultats_marches m ON m.id = s.resultat_id
               WHERE m.secteur_activite = ? AND s.nom_canonique IS NOT NULL
                     AND s.nom_canonique != 'INCONNU' AND LENGTH(TRIM(s.nom_canonique)) > 3
                     AND (s.est_groupement = 1 OR UPPER(s.nom_canonique) LIKE '%GROUPEMENT%')
               GROUP BY s.nom_canonique ORDER BY gagnes DESC, soumissions DESC LIMIT 6""",
            (sec,),
        ).fetchall()]

        # 3) Concurrents potentiels actifs dans le secteur (soumissionnaires directs)
        concurrents_potentiels = [dict(r) for r in conn.execute(
            """SELECT s.nom_canonique AS nom,
                      SUM(CASE WHEN s.est_attributaire=1 THEN 1 ELSE 0 END) AS gagnes,
                      COUNT(*) AS soumissions
               FROM resultats_soumissionnaires s JOIN resultats_marches m ON m.id = s.resultat_id
               WHERE m.secteur_activite = ? AND s.nom_canonique IS NOT NULL
                     AND s.nom_canonique != 'INCONNU' AND LENGTH(TRIM(s.nom_canonique)) > 3
                     AND COALESCE(s.est_groupement, 0) = 0
                     AND UPPER(s.nom_canonique) NOT LIKE '%GROUPEMENT%'
               GROUP BY s.nom_canonique ORDER BY gagnes DESC, soumissions DESC LIMIT 8""",
            (sec,),
        ).fetchall()]

        return {
            "secteur": sec,
            "objet": objet,
            "membres": membres,
            "partenaires_groupement": partenaires_groupement,
            "concurrents_potentiels": concurrents_potentiels,
            "suggestions": concurrents_potentiels,
        }
    finally:
        conn.close()
