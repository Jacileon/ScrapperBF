#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/notifications.py
========================
Couche d'ABSTRACTION d'envoi (email / WhatsApp), calquée sur backend/payments.
Par défaut : provider « log » (écrit dans la console) — fonctionne sans aucun
compte externe. Pour l'envoi réel :
  - Email   : variables SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM
  - WhatsApp: WHATSAPP_TOKEN + WHATSAPP_PHONE_ID (Meta Cloud API) — à fournir par
              l'utilisateur ; le code d'envoi est prêt, il ne manque que les clés.

Tant que les clés ne sont pas fournies, l'envoi retombe proprement sur le log,
donc toute la chaîne (souscription → job → envoi) est testable immédiatement.
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.mime.text import MIMEText
from typing import Optional


def _log(canal: str, cible: str, titre: str, message: str) -> dict:
    print(f"[NOTIF:{canal}] -> {cible or '(sans cible)'} | {titre} | {message}")
    return {"ok": True, "provider": "log", "canal": canal}


def _send_email(cible: str, titre: str, message: str) -> dict:
    host = os.environ.get("SMTP_HOST")
    if not host or not cible:
        return _log("email", cible, titre, message)
    try:
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = titre
        msg["From"] = os.environ.get("SMTP_FROM", "no-reply@veillebf")
        msg["To"] = cible
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            user = os.environ.get("SMTP_USER")
            if user:
                s.login(user, os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return {"ok": True, "provider": "smtp", "canal": "email"}
    except Exception as e:
        return {"ok": False, "provider": "smtp", "error": str(e)}


def _send_whatsapp(cible: str, titre: str, message: str) -> dict:
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    if not (token and phone_id and cible):
        # Pas de compte fournisseur configuré : repli sur le log (chaîne fonctionnelle).
        return _log("whatsapp", cible, titre, message)
    try:
        url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": cible,
            "type": "text",
            "text": {"body": f"*{titre}*\n{message}"},
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": resp.status < 300, "provider": "whatsapp_cloud", "status": resp.status}
    except Exception as e:
        return {"ok": False, "provider": "whatsapp_cloud", "error": str(e)}


def send(canal: str, cible: Optional[str], titre: str, message: str) -> dict:
    """Envoie une notification sur le canal demandé (email|whatsapp), sinon log."""
    canal = (canal or "log").lower()
    if canal == "email":
        return _send_email(cible or "", titre, message)
    if canal == "whatsapp":
        return _send_whatsapp(cible or "", titre, message)
    return _log(canal, cible or "", titre, message)
