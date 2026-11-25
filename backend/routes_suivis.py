#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_suivis.py
========================
Favoris : suivre un marché, lister ses marchés suivis, changer leur statut,
les retirer. Socle de l'alerte résultat « boucle fermée » (backend/alertes_resultats.py).
Toutes les routes exigent un utilisateur connecté.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api/suivis", tags=["suivis"])

_STATUTS = {"suivi", "je_soumissionne", "abandonne"}


class SuiviIn(BaseModel):
    avis_id: str
    statut: Optional[str] = None
    note: Optional[str] = None


class SuiviPatch(BaseModel):
    statut: Optional[str] = None
    note: Optional[str] = None


@router.get("")
def list_suivis(user: dict = Depends(require_user)):
    """Liste des marchés suivis, enrichie des infos marché + présence d'un résultat."""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT s.avis_id, s.statut, s.note, s.cree_le,
                   a.objet_marche        AS objet,
                   a.autorite_contractante AS autorite,
                   a.secteur_activite    AS secteur,
                   a.type_procedure      AS type,
                   a.date_limite_depot   AS date_limite,
                   a.budget_previsionnel_fcfa AS budget,
                   a.reference_dossier   AS reference,
                   (SELECT r.id FROM resultats_marches r
                      WHERE r.annonce_avis_id = s.avis_id LIMIT 1) AS resultat_id
            FROM suivis s
            LEFT JOIN annonces_avis a ON a.id = s.avis_id
            WHERE s.user_id = ?
            ORDER BY s.cree_le DESC
            """,
            (user["id"],),
        ).fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.get("/ids")
def list_suivi_ids(user: dict = Depends(require_user)):
    """Liste légère des avis_id suivis (pour griser/activer les boutons côté front)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT avis_id FROM suivis WHERE user_id = ?", (user["id"],)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


@router.post("")
def add_suivi(body: SuiviIn, user: dict = Depends(require_user)):
    """Suivre un marché (idempotent : met à jour le statut si déjà suivi)."""
    statut = body.statut if body.statut in _STATUTS else "suivi"
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM annonces_avis WHERE id = ?", (body.avis_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Marché introuvable.")
        conn.execute(
            """INSERT INTO suivis (user_id, avis_id, statut, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, avis_id)
               DO UPDATE SET statut = excluded.statut,
                             note = COALESCE(excluded.note, suivis.note)""",
            (user["id"], body.avis_id, statut, body.note),
        )
        conn.commit()
        return {"ok": True, "avis_id": body.avis_id, "statut": statut}
    finally:
        conn.close()


@router.patch("/{avis_id}")
def update_suivi(avis_id: str, body: SuiviPatch, user: dict = Depends(require_user)):
    """Changer le statut (ex. « je_soumissionne ») ou la note d'un marché suivi."""
    fields, params = [], []
    if body.statut is not None:
        if body.statut not in _STATUTS:
            raise HTTPException(status_code=400, detail="Statut invalide.")
        fields.append("statut = ?")
        params.append(body.statut)
    if body.note is not None:
        fields.append("note = ?")
        params.append(body.note)
    if not fields:
        return {"ok": True}
    params.extend([user["id"], avis_id])
    conn = get_db()
    try:
        cur = conn.execute(
            f"UPDATE suivis SET {', '.join(fields)} WHERE user_id = ? AND avis_id = ?",
            params,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Suivi introuvable.")
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/{avis_id}")
def remove_suivi(avis_id: str, user: dict = Depends(require_user)):
    """Retirer un marché des suivis."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM suivis WHERE user_id = ? AND avis_id = ?",
            (user["id"], avis_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
