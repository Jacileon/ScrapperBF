#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/payments/__init__.py
============================
Sélection du fournisseur de paiement actif (VEILLEBF_PAYMENT_PROVIDER).

Pour brancher un vrai agrégateur plus tard :
  1. créer backend/payments/cinetpay.py (ou ligdicash.py) implémentant PaymentProvider ;
  2. l'enregistrer dans _REGISTRY ci-dessous ;
  3. définir VEILLEBF_PAYMENT_PROVIDER=cinetpay + les clés dans l'environnement.
"""

from __future__ import annotations

from backend.config import PAYMENT_PROVIDER
from backend.payments.base import PaymentProvider
from backend.payments.manual import ManualProvider
from backend.payments.sandbox import SandboxProvider

_REGISTRY: dict[str, type[PaymentProvider]] = {
    "sandbox": SandboxProvider,
    "manual": ManualProvider,
    # "cinetpay": CinetPayProvider,   # à ajouter le moment venu
    # "ligdicash": LigdicashProvider,
}


def get_provider() -> PaymentProvider:
    cls = _REGISTRY.get(PAYMENT_PROVIDER, SandboxProvider)
    return cls()
