#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_api.py — API publique (offre Entreprise).
Lecture programmatique via clé d'API (en-tête X-API-Key) ou session.
Toutes les routes exigent la capacité « api » (require_feature).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.db import get_db
from backend.deps import require_feature

router = APIRouter(prefix="/api/v1", tags=["api-publique"])


@router.get("/marches")
def v1_marches(
    user: dict = Depends(require_feature("api")),
    q: Optional[str] = Query(None),
    secteur: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = get_db()
    try:
        cond, params = [], []
        if q:
            cond.append("(objet_marche LIKE ? OR autorite_contractante LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if secteur:
            cond.append("secteur_activite = ?"); params.append(secteur)
        where = ("WHERE " + " AND ".join(cond)) if cond else ""
        total = conn.execute(f"SELECT COUNT(*) FROM annonces_avis {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, objet_marche, autorite_contractante, secteur_activite,
                       type_procedure, date_limite_depot, budget_previsionnel_fcfa
                FROM annonces_avis {where} ORDER BY rowid DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "results": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/resultats")
def v1_resultats(
    user: dict = Depends(require_feature("api")),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = get_db()
    try:
        cond, params = [], []
        if q:
            cond.append("(objet LIKE ? OR autorite_contractante LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        where = ("WHERE " + " AND ".join(cond)) if cond else ""
        total = conn.execute(f"SELECT COUNT(*) FROM resultats_marches {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, objet, autorite_contractante, secteur_activite,
                       date_parution, nombre_lots FROM resultats_marches {where}
                ORDER BY rowid DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "results": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/entreprises")
def v1_entreprises(
    user: dict = Depends(require_feature("api")),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    conn = get_db()
    try:
        cond = ["nom_canonique IS NOT NULL", "LENGTH(TRIM(nom_canonique)) > 3"]
        params = []
        if q:
            cond.append("nom_canonique LIKE ?"); params.append(f"%{q}%")
        where = "WHERE " + " AND ".join(cond)
        rows = conn.execute(
            f"""SELECT nom_canonique AS nom, COUNT(*) AS soumissions,
                       SUM(CASE WHEN est_attributaire=1 THEN 1 ELSE 0 END) AS marches_gagnes
                FROM resultats_soumissionnaires {where}
                GROUP BY nom_canonique ORDER BY marches_gagnes DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()
