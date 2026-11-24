#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/security.py
===================
Hachage des mots de passe et jetons de session — 100 % bibliothèque standard
(aucune dépendance externe), donc déployable et testable immédiatement.

- Mot de passe : PBKDF2-HMAC-SHA256 (260 000 itérations) + sel aléatoire.
- Jeton de session : charge utile JSON signée HMAC-SHA256 (format type JWT compact),
  avec expiration. Signé avec VEILLEBF_JWT_SECRET.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from backend.config import JWT_SECRET, JWT_TTL_SECONDS

# --------------------------------------------------------------------------- #
# Mots de passe
# --------------------------------------------------------------------------- #
_PBKDF2_ITER = 260_000
_PBKDF2_ALGO = "sha256"


def hash_password(password: str) -> str:
    """Renvoie une chaîne stockable : pbkdf2$<iter>$<sel_b64>$<hash_b64>."""
    if not password or len(password) < 6:
        raise ValueError("Le mot de passe doit contenir au moins 6 caractères.")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode("utf-8"), salt, _PBKDF2_ITER)
    return "pbkdf2${}${}${}".format(
        _PBKDF2_ITER,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre la valeur stockée (comparaison constante)."""
    try:
        scheme, iters, salt_b64, hash_b64 = stored.split("$")
        if scheme != "pbkdf2":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Jetons de session (JWT-like, HMAC-SHA256)
# --------------------------------------------------------------------------- #
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(msg: str) -> str:
    sig = hmac.new(JWT_SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return _b64url(sig)


def create_token(user_id: int, email: str, ttl: int | None = None) -> str:
    """Crée un jeton signé portant l'identité de l'utilisateur."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + (ttl if ttl is not None else JWT_TTL_SECONDS),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    header = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    signing_input = f"{header}.{body}"
    return f"{signing_input}.{_sign(signing_input)}"


def decode_token(token: str) -> dict | None:
    """Vérifie signature + expiration. Renvoie le payload, ou None si invalide."""
    try:
        header, body, sig = token.split(".")
        signing_input = f"{header}.{body}"
        if not hmac.compare_digest(sig, _sign(signing_input)):
            return None
        payload = json.loads(_b64url_decode(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Clés d'API (offre Entreprise)
# --------------------------------------------------------------------------- #
def generate_api_key() -> tuple[str, str, str]:
    """
    Génère une clé API.
    Renvoie (cle_claire, prefixe, cle_hash). La clé claire n'est montrée qu'une
    seule fois ; seul le hash est stocké.
    """
    raw = secrets.token_urlsafe(32)
    cle = f"vbf_{raw}"
    prefixe = cle[:12]
    cle_hash = hashlib.sha256(cle.encode("utf-8")).hexdigest()
    return cle, prefixe, cle_hash


def hash_api_key(cle: str) -> str:
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()
