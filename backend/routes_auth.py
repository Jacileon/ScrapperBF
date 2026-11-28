#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_auth.py
======================
Inscription, connexion, déconnexion, profil (/api/auth/*).
Session via cookie httpOnly signé (voir security.create_token).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator

from backend.config import (COOKIE_SAMESITE, COOKIE_SECURE, JWT_TTL_SECONDS,
                            SESSION_COOKIE)
from backend.db import get_db
from backend.deps import require_user
from backend.plans import get_plan, get_quota
from backend.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- #
# Schémas
# --------------------------------------------------------------------------- #
class RegisterIn(BaseModel):
    email: str
    password: str
    nom: str | None = None
    organisation: str | None = None
    telephone: str | None = None

    @field_validator("email")
    @classmethod
    def _email_ok(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Adresse email invalide.")
        return v

    @field_validator("password")
    @classmethod
    def _pwd_ok(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("Le mot de passe doit contenir au moins 6 caractères.")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class ForgotIn(BaseModel):
    email: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _public_user(row: sqlite3.Row | dict) -> dict:
    u = dict(row)
    u.pop("password_hash", None)
    plan = get_plan(u.get("plan_id"))
    u["plan"] = {
        "id": plan["id"],
        "nom": plan["nom"],
        "features": plan["features"],
        "quotas": plan["quotas"],
    }
    return u


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, response: Response):
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (body.email,)
        ).fetchone()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Un compte existe déjà avec cet email.",
            )
        cur = conn.execute(
            """INSERT INTO users (email, password_hash, nom, organisation, telephone, plan_id, role)
               VALUES (?, ?, ?, ?, ?, 'gratuit', 'user') RETURNING id""",
            (body.email, hash_password(body.password), body.nom,
             body.organisation, body.telephone),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        # abonnement gratuit par défaut
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan_id, statut, cycle) "
            "VALUES (?, 'gratuit', 'active', 'mensuel')",
            (user_id,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()

    token = create_token(user_id, body.email)
    _set_session_cookie(response, token)
    return {"user": _public_user(row)}


@router.post("/login")
def login(body: LoginIn, response: Response):
    email = (body.email or "").strip().lower()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
        )
    token = create_token(row["id"], email)
    _set_session_cookie(response, token)
    return {"user": _public_user(row)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    """Profil courant + usage des quotas du jour. 401 si non connecté."""
    user = require_user(request)
    pu = _public_user(user)

    # usage du jour
    periode = date.today().isoformat()
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT compteur_recherches, compteur_fiches FROM usage_counters "
            "WHERE user_id = ? AND periode = ?",
            (user["id"], periode),
        ).fetchone()
    finally:
        conn.close()
    used_rech = int(row["compteur_recherches"]) if row else 0
    used_fiches = int(row["compteur_fiches"]) if row else 0
    pu["usage"] = {
        "recherches": {"utilise": used_rech,
                       "limite": get_quota(user.get("plan_id"), "recherches_par_jour")},
        "fiches": {"utilise": used_fiches,
                   "limite": get_quota(user.get("plan_id"), "fiches_par_jour")},
    }
    return {"user": pu}


@router.post("/forgot-password")
def forgot_password(body: ForgotIn):
    """
    Stub : l'envoi d'email n'est pas branché dans cette itération.
    On répond toujours OK pour ne pas divulguer l'existence d'un compte.
    """
    return {
        "ok": True,
        "message": "Si un compte existe pour cet email, les instructions de "
                   "réinitialisation y seront envoyées.",
    }
