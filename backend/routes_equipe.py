#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_equipe.py — Espace équipe (offre Entreprise) :
inviter des collaborateurs existants, gérer les rôles. Max 5 membres.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_feature

router = APIRouter(prefix="/api/equipe", tags=["equipe"])

MAX_MEMBRES = 5


class InviteIn(BaseModel):
    email: str
    role: str = "membre"


@router.get("")
def liste_equipe(user: dict = Depends(require_feature("equipe"))):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT t.member_user_id, t.role, t.cree_le, u.nom, u.email, u.organisation
               FROM team_members t JOIN users u ON u.id = t.member_user_id
               WHERE t.owner_user_id = ? ORDER BY t.cree_le DESC""",
            (user["id"],),
        ).fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows), "max": MAX_MEMBRES}
    finally:
        conn.close()


@router.post("")
def inviter(body: InviteIn, user: dict = Depends(require_feature("equipe"))):
    email = (body.email or "").strip().lower()
    role = body.role if body.role in ("membre", "admin") else "membre"
    conn = get_db()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM team_members WHERE owner_user_id = ?", (user["id"],)
        ).fetchone()[0]
        if n >= MAX_MEMBRES:
            raise HTTPException(status_code=402, detail=f"Maximum {MAX_MEMBRES} membres pour l'offre Entreprise.")
        membre = conn.execute("SELECT id, nom, email FROM users WHERE email = ?", (email,)).fetchone()
        if not membre:
            raise HTTPException(status_code=404, detail="Aucun compte avec cet email. Le collaborateur doit d'abord créer son compte.")
        if membre["id"] == user["id"]:
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous inviter vous-même.")
        conn.execute(
            """INSERT INTO team_members (owner_user_id, member_user_id, role) VALUES (?, ?, ?)
               ON CONFLICT(owner_user_id, member_user_id) DO UPDATE SET role = excluded.role""",
            (user["id"], membre["id"], role),
        )
        conn.commit()
        return {"ok": True, "membre": {"id": membre["id"], "nom": membre["nom"], "email": membre["email"], "role": role}}
    finally:
        conn.close()


@router.delete("/{member_user_id}")
def retirer(member_user_id: int, user: dict = Depends(require_feature("equipe"))):
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM team_members WHERE owner_user_id = ? AND member_user_id = ?",
            (user["id"], member_user_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
