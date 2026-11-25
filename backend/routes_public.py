#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_public.py
========================
Pages publiques pour le référencement (SEO) et l'acquisition :
  - /secteur/{slug}  : landing par secteur (marchés ouverts, rendu serveur)
  - /barometre       : baromètre des marchés publics (rendu serveur)
  - /api/whatsapp/webhook : vérification + réception des messages (bot).
"""

from __future__ import annotations

import os
import re
import unicodedata

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from backend import intelligence
from backend import notifications as notif
from backend.db import get_db

router = APIRouter(tags=["public"])


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def _esc(s) -> str:
    s = "" if s is None else str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _fcfa(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ") + " FCFA"
    except Exception:
        return "—"


def _page(title: str, desc: str, body: str) -> str:
    return (
        "<!doctype html><html lang=fr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title><meta name=description content='{_esc(desc)}'>"
        "<link rel=icon href=/assets/logo.svg><link rel=stylesheet href=/assets/app.css>"
        "<style>body{max-width:960px;margin:0 auto;padding:24px 18px;font-family:system-ui,sans-serif}"
        "a{color:#047857}.mk{border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin:10px 0}"
        ".mk h3{margin:0 0 6px;font-size:15px}.mk .m{color:#64748b;font-size:13px}"
        ".top{display:flex;align-items:center;gap:10px;margin-bottom:18px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0}"
        ".tile{background:#f1f5f9;border-radius:12px;padding:14px}.tile b{font-size:20px;display:block}</style>"
        "</head><body><div class=top><a href=/><img src=/assets/logo.svg width=34 alt=''></a>"
        "<strong>VEILLE BF</strong> · Marchés publics du Burkina Faso</div>"
        f"{body}"
        "<p style='margin-top:30px;color:#64748b;font-size:13px'>"
        "Données publiques issues des bulletins officiels de la DGCMEF. "
        "<a href=/inscription>Créer un compte gratuit</a> · <a href=/offres>Nos offres</a></p>"
        "</body></html>"
    )


@router.get("/secteur/{slug}", response_class=HTMLResponse)
def secteur_page(slug: str):
    conn = get_db()
    try:
        secteurs = [r[0] for r in conn.execute(
            "SELECT DISTINCT secteur_activite FROM annonces_avis WHERE secteur_activite IS NOT NULL"
        ).fetchall()]
        match = next((s for s in secteurs if _slug(s) == slug), None)
        if not match:
            return HTMLResponse(_page("Secteur introuvable", "", "<h1>Secteur introuvable</h1>"
                                      "<p><a href=/marches>Voir tous les marchés</a></p>"), status_code=404)
        rows = conn.execute(
            """SELECT id, objet_marche, autorite_contractante, date_limite_depot, budget_previsionnel_fcfa
               FROM annonces_avis WHERE secteur_activite = ? ORDER BY rowid DESC LIMIT 50""", (match,),
        ).fetchall()
    finally:
        conn.close()

    cards = "".join(
        f"<div class=mk><h3><a href=/market.html?id={_esc(r['id'])}>{_esc(r['objet_marche'])}</a></h3>"
        f"<div class=m>{_esc(r['autorite_contractante'])} · Dépôt : {_esc(r['date_limite_depot'] or 'n.c.')} · "
        f"{_fcfa(r['budget_previsionnel_fcfa'])}</div></div>"
        for r in rows
    )
    title = f"Marchés publics {match} au Burkina Faso | Veille BF"
    desc = f"Tous les appels d'offres et demandes de prix du secteur {match} au Burkina Faso, mis à jour quotidiennement."
    body = (f"<h1>Marchés publics — {_esc(match)}</h1>"
            f"<p>{len(rows)} marchés récents du secteur <strong>{_esc(match)}</strong> au Burkina Faso. "
            "Suivez-les, évaluez vos chances et recevez les nouveaux par alerte.</p>" + (cards or "<p>Aucun marché pour l'instant.</p>"))
    return HTMLResponse(_page(title, desc, body))


@router.get("/barometre", response_class=HTMLResponse)
def barometre_page():
    conn = get_db()
    try:
        t = intelligence.tendances(conn)
    finally:
        conn.close()
    tiles = (f"<div class=tile><b>{t['marches_ouverts']:,}</b>Marchés ouverts</div>"
             f"<div class=tile><b>{_fcfa(t['budget_total'])}</b>Volume cumulé</div>"
             f"<div class=tile><b>{len(t['par_secteur'])}</b>Secteurs suivis</div>").replace(",", " ")
    sect = "".join(
        f"<div class=mk><h3><a href=/secteur/{_slug(s['secteur'])}>{_esc(s['secteur'])}</a></h3>"
        f"<div class=m>{s['n']} marchés · {_fcfa(s['budget'])}</div></div>"
        for s in t["par_secteur"]
    )
    body = ("<h1>Baromètre des marchés publics du Burkina Faso</h1>"
            "<p>Photographie en temps réel de l'activité des marchés publics (DGCMEF).</p>"
            f"<div class=grid>{tiles}</div><h2>Par secteur</h2>{sect}")
    return HTMLResponse(_page("Baromètre des marchés publics du Burkina Faso | Veille BF",
                              "Baromètre temps réel des marchés publics du Burkina Faso : volumes, budgets et secteurs actifs.",
                              body))


# --------------------------------------------------------------------------- #
# Webhook WhatsApp (bot conversationnel) — nécessite un compte Meta Cloud API.
# --------------------------------------------------------------------------- #
@router.get("/api/whatsapp/webhook")
def whatsapp_verify(request: Request):
    """Vérification du webhook (handshake Meta)."""
    params = request.query_params
    token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "veillebf-verify")
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == token:
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("forbidden", status_code=403)


@router.post("/api/whatsapp/webhook")
async def whatsapp_incoming(request: Request):
    """Réception d'un message : répond avec les marchés correspondant au mot-clé."""
    try:
        data = await request.json()
    except Exception:
        return {"ok": True}
    try:
        value = data["entry"][0]["changes"][0]["value"]
        msg = value["messages"][0]
        frm = msg["from"]
        texte = (msg.get("text", {}).get("body") or "").strip()
    except Exception:
        return {"ok": True}  # notifications de statut, etc.

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT objet_marche, autorite_contractante, date_limite_depot
               FROM annonces_avis
               WHERE objet_marche LIKE ? OR secteur_activite LIKE ? OR autorite_contractante LIKE ?
               ORDER BY rowid DESC LIMIT 3""",
            (f"%{texte}%", f"%{texte}%", f"%{texte}%"),
        ).fetchall()
    finally:
        conn.close()

    if rows:
        lignes = [f"• {(r['objet_marche'] or '')[:70]} — dépôt {r['date_limite_depot'] or 'n.c.'}" for r in rows]
        reponse = "Marchés trouvés :\n" + "\n".join(lignes) + "\n\nPlus sur veillebf."
    else:
        reponse = "Aucun marché trouvé pour « " + texte[:40] + " ». Essayez un secteur (BTP, santé, informatique…)."
    notif.send("whatsapp", frm, "Veille BF", reponse)
    return {"ok": True}
