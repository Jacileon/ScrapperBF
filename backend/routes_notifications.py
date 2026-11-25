#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_notifications.py
===============================
Fil de notifications de l'utilisateur. À l'ouverture, on génère paresseusement
les alertes « résultat » manquantes (un marché suivi désormais attribué apparaît
immédiatement). Toutes les routes exigent un utilisateur connecté.
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend import jobs
from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class ReadIn(BaseModel):
    ids: Optional[List[int]] = None


@router.get("")
def list_notifications(user: dict = Depends(require_user)):
    # Génération paresseuse (ne doit jamais casser l'affichage du fil).
    try:
        jobs.generate_for_user(user["id"])
    except Exception:
        pass

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, type, avis_id, resultat_id, titre, message, payload_json, lu, cree_le
               FROM notifications WHERE user_id = ?
               ORDER BY cree_le DESC, id DESC LIMIT 50""",
            (user["id"],),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d.pop("payload_json", None)
                d["payload"] = {}
            out.append(d)
        non_lus = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND lu = 0",
            (user["id"],),
        ).fetchone()[0]
        return {"notifications": out, "non_lus": non_lus, "total": len(out)}
    finally:
        conn.close()


@router.post("/read")
def mark_read(body: ReadIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        if body.ids:
            qmarks = ",".join("?" * len(body.ids))
            conn.execute(
                f"UPDATE notifications SET lu = 1 WHERE user_id = ? AND id IN ({qmarks})",
                [user["id"], *body.ids],
            )
        else:
            conn.execute(
                "UPDATE notifications SET lu = 1 WHERE user_id = ?", (user["id"],)
            )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
