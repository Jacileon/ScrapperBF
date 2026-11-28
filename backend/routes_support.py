#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_support.py
=========================
Système de tickets support client :
  - Création d'un ticket par l'utilisateur
  - Liste des tickets (utilisateur : ses tickets ; admin : tous les tickets)
  - Réponse sur un ticket (utilisateur ou admin)
  - Changement de statut (ouvert / répondu / fermé)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import get_current_user_optional, require_user

router = APIRouter(prefix="/api/support", tags=["support"])


def _ensure_tables(conn) -> None:
    from backend.db import IS_POSTGRES
    if IS_POSTGRES:
        return  # tables déjà provisionnées (backend/schema_postgres.sql)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_email TEXT,
            user_nom TEXT,
            sujet TEXT NOT NULL,
            categorie TEXT DEFAULT 'Général',
            statut TEXT DEFAULT 'ouvert',
            cree_le TEXT NOT NULL,
            maj_le TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            sender_nom TEXT,
            sender_role TEXT DEFAULT 'user',
            message TEXT NOT NULL,
            cree_le TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


class TicketIn(BaseModel):
    sujet: str
    categorie: Optional[str] = "Général"
    message: str


class ReplyIn(BaseModel):
    message: str


class StatusIn(BaseModel):
    statut: str


@router.get("/tickets")
def list_tickets(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        _ensure_tables(conn)
        is_admin = (user.get("role") == "admin")
        if is_admin:
            rows = conn.execute(
                "SELECT * FROM support_tickets ORDER BY maj_le DESC, id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM support_tickets WHERE user_id = ? ORDER BY maj_le DESC, id DESC",
                (user["id"],),
            ).fetchall()

        tickets = []
        for r in rows:
            t = dict(r)
            msgs = conn.execute(
                "SELECT id, sender_id, sender_nom, sender_role, message, cree_le "
                "FROM support_messages WHERE ticket_id = ? ORDER BY id ASC",
                (t["id"],),
            ).fetchall()
            t["messages"] = [dict(m) for m in msgs]
            tickets.append(t)

        return {"is_admin": is_admin, "results": tickets}
    finally:
        conn.close()


@router.post("/tickets")
def create_ticket(body: TicketIn, user: dict = Depends(require_user)):
    sujet = (body.sujet or "").strip()
    message = (body.message or "").strip()
    categorie = (body.categorie or "Général").strip()
    if len(sujet) < 3 or len(message) < 5:
        raise HTTPException(status_code=400, detail="Sujet (min 3 car.) et message (min 5 car.) requis.")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        _ensure_tables(conn)
        cur = conn.execute(
            """INSERT INTO support_tickets (user_id, user_email, user_nom, sujet, categorie, statut, cree_le, maj_le)
               VALUES (?, ?, ?, ?, ?, 'ouvert', ?, ?) RETURNING id""",
            (user["id"], user.get("email"), user.get("nom") or user.get("email"), sujet, categorie, now, now),
        )
        ticket_id = cur.fetchone()[0]
        conn.execute(
            """INSERT INTO support_messages (ticket_id, sender_id, sender_nom, sender_role, message, cree_le)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticket_id, user["id"], user.get("nom") or user.get("email"), user.get("role") or "user", message, now),
        )
        conn.commit()
        return {"ok": True, "ticket_id": ticket_id}
    finally:
        conn.close()


@router.post("/tickets/{ticket_id}/reply")
def reply_ticket(ticket_id: int, body: ReplyIn, user: dict = Depends(require_user)):
    msg = (body.message or "").strip()
    if len(msg) < 2:
        raise HTTPException(status_code=400, detail="Le message ne peut pas être vide.")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        _ensure_tables(conn)
        t = conn.execute("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="Ticket introuvable.")

        is_admin = (user.get("role") == "admin")
        if not is_admin and t["user_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Accès refusé à ce ticket.")

        sender_role = "admin" if is_admin else "user"
        new_status = "repondu" if is_admin else "ouvert"

        conn.execute(
            """INSERT INTO support_messages (ticket_id, sender_id, sender_nom, sender_role, message, cree_le)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticket_id, user["id"], user.get("nom") or user.get("email"), sender_role, msg, now),
        )
        conn.execute(
            "UPDATE support_tickets SET statut = ?, maj_le = ? WHERE id = ?",
            (new_status, now, ticket_id),
        )
        conn.commit()
        return {"ok": True, "statut": new_status}
    finally:
        conn.close()


@router.patch("/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: int, body: StatusIn, user: dict = Depends(require_user)):
    st = (body.statut or "").strip().lower()
    if st not in ("ouvert", "repondu", "ferme"):
        raise HTTPException(status_code=400, detail="Statut invalide (ouvert, repondu, ferme).")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        _ensure_tables(conn)
        t = conn.execute("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="Ticket introuvable.")
        is_admin = (user.get("role") == "admin")
        if not is_admin and t["user_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Accès refusé.")
        conn.execute("UPDATE support_tickets SET statut = ?, maj_le = ? WHERE id = ?", (st, now, ticket_id))
        conn.commit()
        return {"ok": True, "statut": st}
    finally:
        conn.close()


class ReportIn(BaseModel):
    type_cible: str = "avis"  # "avis" ou "resultat"
    cible_id: str
    cible_titre: Optional[str] = ""
    motif: str = "Données erronées ou incomplètes"
    message: str
    contact: Optional[str] = None


@router.post("/report")
def create_report(body: ReportIn, request: Request):
    msg = (body.message or "").strip()
    if len(msg) < 4:
        raise HTTPException(status_code=400, detail="Veuillez décrire le problème constaté (min 4 caractères).")

    user = get_current_user_optional(request)
    uid = user["id"] if user else None
    uemail = (user.get("email") if user else None) or (body.contact or "Visiteur anonyme")
    unom = (user.get("nom") or user.get("email")) if user else (body.contact or "Visiteur")

    kind_lbl = "Résultat" if (body.type_cible or "").lower().startswith("res") else "Avis"
    sujet = f"[Signalement {kind_lbl}] {(body.cible_titre or body.cible_id)[:110]}"
    full_msg = f"Cible : {kind_lbl} ({body.cible_id})\nMotif : {body.motif}\n\n{msg}"

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        _ensure_tables(conn)
        cur = conn.execute(
            """INSERT INTO support_tickets (user_id, user_email, user_nom, sujet, categorie, statut, cree_le, maj_le)
               VALUES (?, ?, ?, ?, ?, 'ouvert', ?, ?) RETURNING id""",
            (uid, uemail, unom, sujet, f"Signalement {kind_lbl}", now, now),
        )
        ticket_id = cur.fetchone()[0]
        conn.execute(
            """INSERT INTO support_messages (ticket_id, sender_id, sender_nom, sender_role, message, cree_le)
               VALUES (?, ?, ?, 'user', ?, ?)""",
            (ticket_id, uid or 0, unom, full_msg, now),
        )
        conn.commit()
        return {"ok": True, "ticket_id": ticket_id}
    finally:
        conn.close()
