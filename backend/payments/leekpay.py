#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/payments/leekpay.py
===========================
Fournisseur officiel LeekPay (Mobile Money Orange, Moov, Wave et Carte).

Documentation : https://www.leekpay.me/docs
- REST API : POST /api/v1/checkout
- Polling / Statut : GET /api/v1/checkout/{id}
- Webhook : X-LeekPay-Signature-V2 (HMAC-SHA256 avec timestamp)
- SDK Widget / JS : https://leekpay.fr/js/leekpay.js (LeekPay.checkout)
"""

from __future__ import annotations

import hmac
import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from backend.config import (
    LEEKPAY_BASE_URL,
    LEEKPAY_PUBLIC_KEY,
    LEEKPAY_SECRET_KEY,
    LEEKPAY_WEBHOOK_SECRET,
    PUBLIC_URL,
)
from backend.payments.base import InitResult, PaymentProvider, VerifyResult

logger = logging.getLogger("backend.payments.leekpay")


class LeekPayProvider(PaymentProvider):
    name = "leekpay"

    def __init__(
        self,
        *,
        secret_key: Optional[str] = None,
        public_key: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.secret_key = (secret_key or LEEKPAY_SECRET_KEY).strip()
        self.public_key = (public_key or LEEKPAY_PUBLIC_KEY).strip()
        self.webhook_secret = (webhook_secret or LEEKPAY_WEBHOOK_SECRET).strip()
        self.base_url = (base_url or LEEKPAY_BASE_URL).rstrip("/")

    def init_payment(
        self,
        *,
        reference_interne: str,
        montant_fcfa: int,
        operateur: str,
        telephone: str,
        description: str,
        metadata: dict,
    ) -> InitResult:
        """Initialise une session de paiement LeekPay (REST API v1)."""
        url = f"{self.base_url}/api/v1/checkout"
        
        return_url = f"{PUBLIC_URL}/checkout.html?statut=succes&ref={urllib.parse.quote(reference_interne)}"
        cancel_url = f"{PUBLIC_URL}/checkout.html?statut=annule&ref={urllib.parse.quote(reference_interne)}"

        # Métadonnées transmises pour le suivi et la réconciliation webhook
        meta_payload = dict(metadata or {})
        meta_payload["reference_interne"] = reference_interne
        meta_payload["operateur"] = operateur

        payload = {
            "amount": int(montant_fcfa),
            "currency": "XOF",
            "description": description or f"Abonnement Veille BF - {metadata.get('plan_id', 'Pro').title()}",
            "return_url": return_url,
            "cancel_url": cancel_url,
            "metadata": meta_payload,
        }

        # LeekPay refuse explicitement les webhook_url sur adresses internes/locales (127.0.0.1, localhost)
        is_local = any(h in PUBLIC_URL.lower() for h in ("127.0.0.1", "localhost", "::1", "0.0.0.0"))
        if not is_local:
            payload["webhook_url"] = f"{PUBLIC_URL}/api/billing/webhook"

        if telephone:
            payload["customer_phone"] = telephone
        if metadata.get("email"):
            payload["customer_email"] = metadata.get("email")
        if metadata.get("nom"):
            payload["customer_name"] = metadata.get("nom")

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "User-Agent": "VeilleBF-SaaS/1.0",
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error("Erreur HTTP LeekPay (%s) : %s", e.code, err_body)
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message") or err_json.get("error") or str(e)
            except Exception:
                msg = err_body or str(e)
            raise RuntimeError(f"Échec de l'initialisation LeekPay ({e.code}) : {msg}")
        except Exception as e:
            logger.error("Erreur connexion LeekPay : %s", e)
            raise RuntimeError(f"Impossible de contacter la passerelle LeekPay : {e}")

        if not resp_data.get("success"):
            msg = resp_data.get("message", "Erreur inconnue retournée par LeekPay.")
            raise RuntimeError(f"Échec LeekPay : {msg}")

        data = resp_data.get("data", {})
        checkout_id = data.get("id")
        payment_url = data.get("payment_url")

        return InitResult(
            mode="redirect",
            reference_interne=reference_interne,
            reference_externe=checkout_id,
            checkout_url=payment_url,
            confirm_url=None,
            instructions=(
                "Paiement sécurisé LeekPay (Orange Money, Moov Money, Wave, Carte bancaire). "
                "Vous allez être redirigé vers la page de paiement."
            ),
            extra={
                "provider": "leekpay",
                "checkout_id": checkout_id,
                "public_key": self.public_key,
                "payment_url": payment_url,
                "amount": montant_fcfa,
                "currency": "XOF",
                "reference_interne": reference_interne,
            },
        )

    def verify(self, *, reference_interne: str, reference_externe: str | None) -> VerifyResult:
        """Interroge l'API LeekPay pour vérifier l'état en direct de la transaction."""
        checkout_id = reference_externe
        if not checkout_id:
            return VerifyResult(statut="pending", raw={"message": "Aucun identifiant externe LeekPay"})

        url = f"{self.base_url}/api/v1/checkout/{checkout_id}"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "User-Agent": "VeilleBF-SaaS/1.0",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("Erreur vérification LeekPay %s : %s", checkout_id, e)
            return VerifyResult(statut="pending", reference_externe=checkout_id, raw={"error": str(e)})

        data = resp_data.get("data", {})
        st = (data.get("status") or "").lower()

        # Statuts LeekPay : "paid", "completed", "pending", "failed", "cancelled", "expired"
        if st in ("paid", "completed", "success"):
            statut = "paye"
        elif st in ("failed", "cancelled", "expired"):
            statut = "echec"
        else:
            statut = "pending"

        return VerifyResult(statut=statut, reference_externe=checkout_id, raw=data)

    def parse_webhook(self, *, headers: dict, body: bytes) -> VerifyResult:
        """Vérifie l'en-tête X-LeekPay-Signature-V2 et analyse le webhook."""
        # Recherche insensible à la casse de l'en-tête
        sig_header = None
        for k, v in headers.items():
            if k.lower() == "x-leekpay-signature-v2":
                sig_header = v
                break

        # Extraction timestamp (t) et signature (v1)
        sig_parts = {}
        if sig_header:
            for part in sig_header.replace(",", "&").split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    sig_parts[k.strip()] = v.strip()

        t_str = sig_parts.get("t")
        v1 = sig_parts.get("v1")

        # Vérification anti-rejeu et signature si le secret webhook est configuré
        if self.webhook_secret and t_str and v1:
            try:
                t_val = int(t_str)
                # Tolérance de 5 minutes (300 secondes)
                if abs(time.time() - t_val) > 300:
                    logger.warning("Rejet Webhook LeekPay : horodatage expiré (t=%s)", t_val)
                    raise ValueError("Horodatage de webhook expiré.")

                raw_text = body.decode("utf-8", errors="ignore")
                expected = hmac.new(
                    self.webhook_secret.encode("utf-8"),
                    f"{t_val}.{raw_text}".encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()

                if not hmac.compare_digest(expected, v1):
                    logger.warning("Rejet Webhook LeekPay : signature v1 invalide")
                    raise ValueError("Signature LeekPay invalide.")
            except ValueError:
                raise
            except Exception as e:
                logger.warning("Erreur vérification signature webhook : %s", e)
                raise ValueError(f"Échec validation signature : {e}")

        # Décodage du corps JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.error("Corps Webhook LeekPay non-JSON : %s", e)
            raise ValueError("Payload JSON invalide.")

        event = payload.get("event", "")
        data = payload.get("data", {})
        checkout_id = data.get("checkout_id") or data.get("id") or data.get("transaction_id")
        raw_status = (data.get("status") or "").lower()

        if event == "payment.completed" or raw_status in ("paid", "completed", "success"):
            statut = "paye"
        elif event in ("payment.failed", "payment.cancelled") or raw_status in ("failed", "cancelled", "expired"):
            statut = "echec"
        else:
            statut = "pending"

        return VerifyResult(statut=statut, reference_externe=checkout_id, raw=payload)
