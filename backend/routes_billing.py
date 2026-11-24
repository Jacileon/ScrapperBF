#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_billing.py
=========================
Offres, abonnements et paiements (/api/billing/*).

Parcours :
  GET  /plans                 -> grille publique des offres
  GET  /status                -> abonnement courant + historique paiements (connecté)
  POST /subscribe             -> crée un paiement 'pending' et initialise le fournisseur
  POST /confirm               -> (sandbox) confirme un paiement simulé et active l'offre
  POST /webhook               -> rappel serveur-à-serveur d'un vrai agrégateur
  GET/POST/DELETE /api-keys   -> gestion des clés API (offre Entreprise)
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.config import PAYMENT_PROVIDER
from backend.db import get_db
from backend.deps import require_feature, require_user
from backend.payments import get_provider
from backend.plans import PLANS, get_plan, public_plans
from backend.security import generate_api_key

router = APIRouter(prefix="/api/billing", tags=["billing"])

VALID_CYCLES = ("mensuel", "annuel")
VALID_OPERATEURS = ("orange", "moov", "carte")


class SubscribeIn(BaseModel):
    plan_id: str
    cycle: str = "mensuel"
    operateur: str = "orange"
    telephone: str | None = None


class ConfirmIn(BaseModel):
    reference: str
    succes: bool = True   # sandbox : simuler succès ou échec


class ApiKeyIn(BaseModel):
    label: str | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _amount_for(plan_id: str, cycle: str) -> int:
    p = get_plan(plan_id)
    return p["prix_annuel_fcfa"] if cycle == "annuel" else p["prix_mensuel_fcfa"]


def _activate_subscription(conn, user_id: int, plan_id: str, cycle: str) -> int:
    """Clôture les abonnements actifs et en crée un nouveau. Met à jour users.plan_id."""
    now = datetime.utcnow()
    fin = now + (timedelta(days=365) if cycle == "annuel" else timedelta(days=30))
    conn.execute(
        "UPDATE subscriptions SET statut='expiree' WHERE user_id=? AND statut='active'",
        (user_id,),
    )
    cur = conn.execute(
        """INSERT INTO subscriptions (user_id, plan_id, statut, cycle, debut, fin)
           VALUES (?, ?, 'active', ?, ?, ?)""",
        (user_id, plan_id, cycle, now.isoformat(sep=" ", timespec="seconds"),
         fin.isoformat(sep=" ", timespec="seconds")),
    )
    conn.execute("UPDATE users SET plan_id=? WHERE id=?", (plan_id, user_id))
    conn.commit()
    return cur.lastrowid


# --------------------------------------------------------------------------- #
# Offres
# --------------------------------------------------------------------------- #
@router.get("/plans")
def list_plans():
    return {"plans": public_plans(), "provider": PAYMENT_PROVIDER}


@router.get("/status")
def status_(request: Request):
    user = require_user(request)
    conn = get_db()
    try:
        sub = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND statut='active' "
            "ORDER BY id DESC LIMIT 1", (user["id"],),
        ).fetchone()
        pays = conn.execute(
            "SELECT id, plan_id, cycle, montant_fcfa, provider, operateur, statut, "
            "reference_interne, cree_le FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 20",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {
        "plan_actuel": user.get("plan_id"),
        "abonnement": dict(sub) if sub else None,
        "paiements": [dict(p) for p in pays],
    }


# --------------------------------------------------------------------------- #
# Abonnement / paiement
# --------------------------------------------------------------------------- #
@router.post("/subscribe")
def subscribe(body: SubscribeIn, request: Request):
    user = require_user(request)
    plan_id = (body.plan_id or "").lower()
    if plan_id not in PLANS or plan_id == "gratuit":
        raise HTTPException(status_code=400, detail="Offre payante invalide.")
    if body.cycle not in VALID_CYCLES:
        raise HTTPException(status_code=400, detail="Cycle invalide (mensuel/annuel).")
    if body.operateur not in VALID_OPERATEURS:
        raise HTTPException(status_code=400, detail="Opérateur de paiement invalide.")

    montant = _amount_for(plan_id, body.cycle)
    reference = "VBF-" + datetime.utcnow().strftime("%Y%m%d") + "-" + secrets.token_hex(4).upper()

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO payments (user_id, plan_id, cycle, montant_fcfa, provider,
                                     operateur, telephone, reference_interne, statut)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (user["id"], plan_id, body.cycle, montant, PAYMENT_PROVIDER,
             body.operateur, body.telephone, reference),
        )
        conn.commit()
    finally:
        conn.close()

    provider = get_provider()
    init = provider.init_payment(
        reference_interne=reference, montant_fcfa=montant, operateur=body.operateur,
        telephone=body.telephone or "", description=f"Abonnement {plan_id} ({body.cycle})",
        metadata={"user_id": user["id"], "plan_id": plan_id, "cycle": body.cycle},
    )
    # enregistre la référence externe si fournie
    if init.reference_externe:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE payments SET reference_externe=?, payload_json=? WHERE reference_interne=?",
                (init.reference_externe, json.dumps(init.extra, ensure_ascii=False), reference),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "reference": reference,
        "montant_fcfa": montant,
        "plan_id": plan_id,
        "cycle": body.cycle,
        "mode": init.mode,
        "checkout_url": init.checkout_url,
        "confirm_url": init.confirm_url,
        "instructions": init.instructions,
    }


@router.post("/confirm")
def confirm(body: ConfirmIn, request: Request):
    """
    Confirmation en mode SANDBOX uniquement : simule le résultat d'un paiement.
    Refusé si un vrai fournisseur est actif (il utilisera /webhook).
    """
    if PAYMENT_PROVIDER not in ("sandbox",):
        raise HTTPException(status_code=403, detail="Confirmation manuelle indisponible pour ce fournisseur.")
    user = require_user(request)
    conn = get_db()
    try:
        pay = conn.execute(
            "SELECT * FROM payments WHERE reference_interne=? AND user_id=?",
            (body.reference, user["id"]),
        ).fetchone()
        if not pay:
            raise HTTPException(status_code=404, detail="Paiement introuvable.")
        if pay["statut"] == "paye":
            return {"statut": "paye", "message": "Paiement déjà confirmé.", "plan_id": pay["plan_id"]}

        if not body.succes:
            conn.execute(
                "UPDATE payments SET statut='echec', maj_le=CURRENT_TIMESTAMP WHERE id=?",
                (pay["id"],),
            )
            conn.commit()
            return {"statut": "echec", "message": "Paiement simulé échoué."}

        sub_id = _activate_subscription(conn, user["id"], pay["plan_id"], pay["cycle"])
        conn.execute(
            "UPDATE payments SET statut='paye', subscription_id=?, maj_le=CURRENT_TIMESTAMP WHERE id=?",
            (sub_id, pay["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"statut": "paye", "message": "Abonnement activé.", "plan_id": pay["plan_id"]}


@router.post("/webhook")
async def webhook(request: Request):
    """
    Rappel serveur-à-serveur d'un vrai agrégateur. Inactif en sandbox/manual :
    le provider réel implémentera parse_webhook() pour vérifier la signature,
    retrouver le paiement par reference et activer l'abonnement.
    """
    provider = get_provider()
    body = await request.body()
    try:
        vr = provider.parse_webhook(headers=dict(request.headers), body=body)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Webhook non supporté pour ce fournisseur.")
    # (Branchement réel : retrouver le paiement via vr.reference_externe, activer si 'paye'.)
    return {"recu": True, "statut": vr.statut}


# --------------------------------------------------------------------------- #
# Clés API (offre Entreprise)
# --------------------------------------------------------------------------- #
@router.get("/api-keys")
def list_api_keys(user: dict = Depends(require_feature("api"))):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, prefixe, label, actif, cree_le, derniere_utilisation "
            "FROM api_keys WHERE user_id=? ORDER BY id DESC", (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {"cles": [dict(r) for r in rows]}


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(body: ApiKeyIn, user: dict = Depends(require_feature("api"))):
    cle, prefixe, cle_hash = generate_api_key()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO api_keys (user_id, cle_hash, prefixe, label) VALUES (?, ?, ?, ?)",
            (user["id"], cle_hash, prefixe, body.label),
        )
        conn.commit()
    finally:
        conn.close()
    # La clé claire n'est renvoyée qu'ici, une seule fois.
    return {"cle": cle, "prefixe": prefixe, "label": body.label,
            "message": "Conservez cette clé : elle ne sera plus affichée."}


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: int, user: dict = Depends(require_feature("api"))):
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, user["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Clé introuvable.")
    return {"ok": True}
