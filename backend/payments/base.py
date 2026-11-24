#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/payments/base.py
========================
Contrat d'un fournisseur de paiement (Mobile Money / carte).

Toute intégration réelle (CinetPay, Ligdicash, ...) implémente cette interface,
ce qui permet de la brancher sans toucher aux routes de facturation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InitResult:
    """Résultat d'une initialisation de paiement."""
    mode: str                       # "simulate" | "redirect" | "manual"
    reference_interne: str
    reference_externe: Optional[str] = None
    checkout_url: Optional[str] = None     # page hébergée (fournisseur réel)
    confirm_url: Optional[str] = None       # endpoint de confirmation (mode simulate)
    instructions: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class VerifyResult:
    """Résultat de la vérification d'un paiement."""
    statut: str                     # "paye" | "pending" | "echec" | "annule"
    reference_externe: Optional[str] = None
    raw: dict = field(default_factory=dict)


class PaymentProvider:
    """Interface. Les méthodes réseau lèvent NotImplementedError par défaut."""

    name = "base"

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
        raise NotImplementedError

    def verify(self, *, reference_interne: str, reference_externe: str | None) -> VerifyResult:
        raise NotImplementedError

    def parse_webhook(self, *, headers: dict, body: bytes) -> VerifyResult:
        raise NotImplementedError
