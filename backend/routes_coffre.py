#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_coffre.py — Coffre documentaire (profil « coffre »).
Upload en base64 (aucune dépendance multipart), stockage sur disque,
liste, téléchargement, suppression. Réservé aux membres connectés.
"""

from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api/coffre", tags=["coffre"])

STORE = Path("data/coffre")
MAX_BYTES = 5 * 1024 * 1024  # 5 Mo


class DocIn(BaseModel):
    nom: str
    type: Optional[str] = None
    contenu_base64: str


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", (name or "doc"))[:80]


@router.get("")
def liste(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, nom, type, taille, cree_le FROM coffre_documents WHERE user_id = ? ORDER BY cree_le DESC",
            (user["id"],),
        ).fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.post("")
def ajouter(body: DocIn, user: dict = Depends(require_user)):
    raw = body.contenu_base64 or ""
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]  # enlève le préfixe data:...;base64,
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="Contenu base64 invalide.")
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 5 Mo).")

    STORE.mkdir(parents=True, exist_ok=True)
    fname = f"{user['id']}_{uuid.uuid4().hex}_{_safe(body.nom)}"
    path = STORE / fname
    path.write_bytes(data)

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO coffre_documents (user_id, nom, type, taille, chemin) VALUES (?,?,?,?,?) RETURNING id",
            (user["id"], body.nom[:120], body.type, len(data), str(path)),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return {"ok": True, "id": new_id, "taille": len(data)}
    finally:
        conn.close()


@router.get("/{doc_id}/download")
def telecharger(doc_id: int, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT nom, type, chemin FROM coffre_documents WHERE id = ? AND user_id = ?",
            (doc_id, user["id"]),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    p = Path(row["chemin"])
    if not p.exists():
        raise HTTPException(status_code=410, detail="Fichier absent du stockage.")
    return Response(content=p.read_bytes(), media_type=row["type"] or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{_safe(row["nom"])}"'})


@router.delete("/{doc_id}")
def supprimer(doc_id: int, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT chemin FROM coffre_documents WHERE id = ? AND user_id = ?", (doc_id, user["id"])
        ).fetchone()
        if row:
            try:
                Path(row["chemin"]).unlink(missing_ok=True)
            except Exception:
                pass
            conn.execute("DELETE FROM coffre_documents WHERE id = ? AND user_id = ?", (doc_id, user["id"]))
            conn.commit()
        return {"ok": True}
    finally:
        conn.close()
