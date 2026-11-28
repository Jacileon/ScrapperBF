#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_admin.py
=======================
Console d'administration (réservée role='admin') :
  - Statistiques globales (utilisateurs, offres, revenus, usage, données)
  - Gestion des utilisateurs (rôle, offre, suppression)
  - Abonnements & paiements (activation manuelle)
Toutes les routes exigent un administrateur (deps.require_admin).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_admin
from backend.plans import PLAN_ORDER

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ROLES = {"user", "admin"}


class UserPatch(BaseModel):
    role: Optional[str] = None
    plan_id: Optional[str] = None


class PaymentPatch(BaseModel):
    statut: str


# --------------------------------------------------------------------------- #
# Statistiques
# --------------------------------------------------------------------------- #
@router.get("/stats")
def admin_stats(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        def one(sql, params=()):
            r = conn.execute(sql, params).fetchone()
            return r[0] if r else 0

        users_total = one("SELECT COUNT(*) FROM users")
        admins = one("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        by_plan = {r["plan_id"]: r["n"] for r in conn.execute(
            "SELECT plan_id, COUNT(*) AS n FROM users GROUP BY plan_id").fetchall()}
        subs_active = one("SELECT COUNT(*) FROM subscriptions WHERE statut = 'active'")
        revenus = one("SELECT COALESCE(SUM(montant_fcfa),0) FROM payments WHERE statut = 'paye'")
        paie_pending = one("SELECT COUNT(*) FROM payments WHERE statut = 'pending'")
        nouveaux_7j = one("SELECT COUNT(*) FROM users WHERE cree_le >= now() - interval '7 days'")
        suivis_total = one("SELECT COUNT(*) FROM suivis")
        data = {
            "annonces": one("SELECT COUNT(*) FROM annonces_avis"),
            "resultats": one("SELECT COUNT(*) FROM resultats_marches"),
            "entreprises": one("SELECT COUNT(*) FROM entreprises"),
        }
        return {
            "users_total": users_total,
            "admins": admins,
            "by_plan": by_plan,
            "subs_active": subs_active,
            "revenus_fcfa": int(revenus or 0),
            "paiements_en_attente": paie_pending,
            "nouveaux_7j": nouveaux_7j,
            "suivis_total": suivis_total,
            "data": data,
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Utilisateurs
# --------------------------------------------------------------------------- #
@router.get("/users")
def admin_users(q: str = "", limit: int = 100, admin: dict = Depends(require_admin)):
    limit = max(1, min(int(limit or 100), 500))
    conn = get_db()
    try:
        where, params = "", []
        if q:
            where = "WHERE u.email ILIKE ? OR u.nom ILIKE ? OR u.organisation ILIKE ?"
            like = f"%{q}%"
            params = [like, like, like]
        rows = conn.execute(
            f"""SELECT u.id, u.email, u.nom, u.organisation, u.telephone, u.plan_id,
                       u.role, u.email_verifie, u.cree_le,
                       (SELECT COUNT(*) FROM suivis s WHERE s.user_id = u.id) AS nb_suivis,
                       (SELECT COUNT(*) FROM radar_concurrents r WHERE r.user_id = u.id) AS nb_radar
                FROM users u {where}
                ORDER BY u.cree_le DESC LIMIT {limit}""",
            tuple(params),
        ).fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.patch("/users/{user_id}")
def admin_update_user(user_id: int, body: UserPatch, admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        target = conn.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

        if body.role is not None:
            if body.role not in _ROLES:
                raise HTTPException(status_code=400, detail="Rôle invalide.")
            # Empêcher de retirer le dernier admin.
            if target["role"] == "admin" and body.role != "admin":
                n = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if n <= 1:
                    raise HTTPException(status_code=400, detail="Impossible : dernier administrateur.")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))

        if body.plan_id is not None:
            if body.plan_id not in PLAN_ORDER:
                raise HTTPException(status_code=400, detail="Offre invalide.")
            conn.execute(
                "UPDATE subscriptions SET statut = 'expiree' WHERE user_id = ? AND statut = 'active'",
                (user_id,))
            conn.execute(
                "INSERT INTO subscriptions (user_id, plan_id, statut, cycle) "
                "VALUES (?, ?, 'active', 'mensuel')", (user_id, body.plan_id))
            conn.execute("UPDATE users SET plan_id = ? WHERE id = ?", (body.plan_id, user_id))

        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, admin: dict = Depends(require_admin)):
    if int(user_id) == int(admin["id"]):
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte.")
    conn = get_db()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
        if row["role"] == "admin":
            n = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
            if n <= 1:
                raise HTTPException(status_code=400, detail="Impossible : dernier administrateur.")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Abonnements & paiements
# --------------------------------------------------------------------------- #
@router.get("/subscriptions")
def admin_subscriptions(limit: int = 100, admin: dict = Depends(require_admin)):
    limit = max(1, min(int(limit or 100), 500))
    conn = get_db()
    try:
        rows = conn.execute(
            f"""SELECT s.id, s.user_id, u.email, s.plan_id, s.statut, s.cycle, s.debut, s.fin
                FROM subscriptions s LEFT JOIN users u ON u.id = s.user_id
                ORDER BY s.cree_le DESC LIMIT {limit}""").fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.get("/payments")
def admin_payments(limit: int = 100, admin: dict = Depends(require_admin)):
    limit = max(1, min(int(limit or 100), 500))
    conn = get_db()
    try:
        rows = conn.execute(
            f"""SELECT p.id, p.user_id, u.email, p.plan_id, p.cycle, p.montant_fcfa,
                       p.provider, p.operateur, p.statut, p.reference_interne, p.cree_le
                FROM payments p LEFT JOIN users u ON u.id = p.user_id
                ORDER BY p.cree_le DESC LIMIT {limit}""").fetchall()
        return {"results": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()


@router.patch("/payments/{payment_id}")
def admin_update_payment(payment_id: int, body: PaymentPatch, admin: dict = Depends(require_admin)):
    if body.statut not in {"pending", "paye", "echec", "annule"}:
        raise HTTPException(status_code=400, detail="Statut invalide.")
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE payments SET statut = ?, maj_le = CURRENT_TIMESTAMP WHERE id = ?",
            (body.statut, payment_id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Paiement introuvable.")
        return {"ok": True}
    finally:
        conn.close()
