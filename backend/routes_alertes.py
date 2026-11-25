#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_alertes.py — Souscription d'alertes (tunnel d'acquisition).
La création est ouverte (sans compte) pour servir de porte d'entrée ; la
gestion (liste, suppression) exige un compte.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import get_current_user_optional, require_user

router = APIRouter(prefix="/api/alertes", tags=["alertes"])

_CANAUX = {"email", "whatsapp"}


class AlerteIn(BaseModel):
    secteur: Optional[str] = None
    type_marche: Optional[str] = None
    region: Optional[str] = None
    canal: str = "email"
    cible: str


@router.post("")
def creer_alerte(body: AlerteIn, request: Request):
    canal = body.canal if body.canal in _CANAUX else "email"
    cible = (body.cible or "").strip()
    if len(cible) < 4:
        raise HTTPException(status_code=400, detail="Email ou numéro requis.")
    user = get_current_user_optional(request)
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO alertes (user_id, secteur, type_marche, region, canal, cible)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user["id"] if user else None, body.secteur, body.type_marche, body.region, canal, cible),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "message": "Alerte créée. Vous recevrez les marchés correspondants."}
    finally:
        conn.close()


@router.get("")
def mes_alertes(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, secteur, type_marche, region, canal, cible, actif, cree_le "
            "FROM alertes WHERE user_id = ? ORDER BY cree_le DESC",
            (user["id"],),
        ).fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.delete("/{alerte_id}")
def supprimer_alerte(alerte_id: int, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        conn.execute("DELETE FROM alertes WHERE id = ? AND user_id = ?", (alerte_id, user["id"]))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
