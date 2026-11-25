#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_intel.py — Intelligence de marché (autorité, prix, tendances, prédictif).
Routes ouvertes en lecture (vitrine) ; le détail fin pourra être gated plus tard.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend import intelligence
from backend.db import get_db

router = APIRouter(prefix="/api/intel", tags=["intelligence"])


@router.get("/autorite")
def get_autorite(nom: str = Query(..., min_length=2)):
    conn = get_db()
    try:
        data = intelligence.autorite_intel(conn, nom)
        if not data["marches_publies"] and not data["lots_attribues"]:
            raise HTTPException(status_code=404, detail="Autorité inconnue.")
        return data
    finally:
        conn.close()


@router.get("/prix")
def get_prix(secteur: str = Query(..., min_length=2), type_marche: Optional[str] = Query(None)):
    conn = get_db()
    try:
        return intelligence.prix_intel(conn, secteur, type_marche)
    finally:
        conn.close()


@router.get("/tendances")
def get_tendances():
    conn = get_db()
    try:
        return intelligence.tendances(conn)
    finally:
        conn.close()


@router.get("/predictions")
def get_predictions(limit: int = Query(30, ge=1, le=100)):
    conn = get_db()
    try:
        return intelligence.predictions(conn, limit)
    finally:
        conn.close()
