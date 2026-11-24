#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/deps.py
===============
Dépendances FastAPI : identité de l'utilisateur courant (via cookie de session
ou clé d'API), verrouillage par offre (features / rang de plan) et quotas.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from backend.config import SESSION_COOKIE
from backend.db import get_db
from backend.plans import get_quota, has_feature, plan_at_least
from backend.security import decode_token, hash_api_key


def _row_to_user(row) -> dict:
    u = dict(row)
    u.pop("password_hash", None)
    return u


def _load_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def _load_user_by_api_key(cle: str) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT u.* FROM api_keys k JOIN users u ON u.id = k.user_id
               WHERE k.cle_hash = ? AND k.actif = 1""",
            (hash_api_key(cle),),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE api_keys SET derniere_utilisation = CURRENT_TIMESTAMP WHERE cle_hash = ?",
            (hash_api_key(cle),),
        )
        conn.commit()
        return _row_to_user(row)
    finally:
        conn.close()


def _extract_token(request: Request) -> Optional[str]:
    # 1) cookie de session
    tok = request.cookies.get(SESSION_COOKIE)
    if tok:
        return tok
    # 2) en-tête Authorization: Bearer <token>
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def get_current_user_optional(request: Request) -> Optional[dict]:
    """Renvoie l'utilisateur courant ou None (pour les routes publiques gated)."""
    # Clé d'API (offre Entreprise / usage machine)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return _load_user_by_api_key(api_key)

    token = _extract_token(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return _load_user_by_id(int(payload["sub"]))


def require_user(request: Request) -> dict:
    """Exige un utilisateur connecté, sinon 401."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
        )
    return user


def plan_of(user: Optional[dict]) -> str:
    return (user or {}).get("plan_id", "gratuit")


def require_feature(feature: str):
    """
    Fabrique une dépendance qui exige une capacité (feature) du plan.
    Renvoie l'utilisateur si autorisé, sinon 401 (anonyme) ou 402 (plan insuffisant).
    """
    def _dep(user: dict = Depends(require_user)) -> dict:
        if not has_feature(plan_of(user), feature):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "upgrade_required",
                    "feature": feature,
                    "plan_actuel": plan_of(user),
                    "message": "Cette fonctionnalité nécessite une offre supérieure.",
                },
            )
        return user
    return _dep


def require_plan(minimum: str):
    """Dépendance exigeant un plan >= `minimum` (gratuit < pro < entreprise)."""
    def _dep(user: dict = Depends(require_user)) -> dict:
        if not plan_at_least(plan_of(user), minimum):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "upgrade_required",
                    "plan_requis": minimum,
                    "plan_actuel": plan_of(user),
                    "message": f"Cette section nécessite l'offre {minimum}.",
                },
            )
        return user
    return _dep


# --------------------------------------------------------------------------- #
# Quotas (offre Gratuit)
# --------------------------------------------------------------------------- #
def consume_quota(user: Optional[dict], quota_key: str, counter_col: str) -> None:
    """
    Incrémente et vérifie un quota journalier pour l'utilisateur.
    - Anonyme : non compté ici (les routes gratuites anonymes peuvent rester ouvertes).
    - Quota -1 : illimité, ne compte pas.
    - Dépassement : 402.
    """
    if not user:
        return
    limit = get_quota(plan_of(user), quota_key)
    if limit < 0:
        return  # illimité

    periode = date.today().isoformat()
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO usage_counters (user_id, periode) VALUES (?, ?)",
            (user["id"], periode),
        )
        row = conn.execute(
            f"SELECT {counter_col} AS n FROM usage_counters WHERE user_id = ? AND periode = ?",
            (user["id"], periode),
        ).fetchone()
        used = int(row["n"]) if row else 0
        if used >= limit:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "quota_depasse",
                    "quota": quota_key,
                    "limite": limit,
                    "plan_actuel": plan_of(user),
                    "message": "Quota journalier atteint pour votre offre.",
                },
            )
        conn.execute(
            f"UPDATE usage_counters SET {counter_col} = {counter_col} + 1 "
            f"WHERE user_id = ? AND periode = ?",
            (user["id"], periode),
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
