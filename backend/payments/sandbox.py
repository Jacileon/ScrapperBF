#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/payments/sandbox.py
===========================
Fournisseur de SIMULATION (aucun mouvement d'argent réel).

Le front appelle /subscribe -> init_payment renvoie mode="simulate" + une URL de
confirmation. Le front (ou l'utilisateur) déclenche ensuite /confirm pour simuler
un paiement réussi (ou échoué). Idéal pour développer et démontrer le parcours
complet avant de brancher un vrai agrégateur Mobile Money.
"""

from __future__ import annotations

from backend.config import PUBLIC_URL
from backend.payments.base import InitResult, PaymentProvider, VerifyResult


class SandboxProvider(PaymentProvider):
    name = "sandbox"

    def init_payment(self, *, reference_interne, montant_fcfa, operateur,
                     telephone, description, metadata) -> InitResult:
        return InitResult(
            mode="simulate",
            reference_interne=reference_interne,
            reference_externe=f"SBX-{reference_interne}",
            confirm_url=f"{PUBLIC_URL}/api/billing/confirm",
            instructions=(
                f"Mode simulation : aucun paiement réel. Opérateur « {operateur} », "
                f"montant {montant_fcfa:,} FCFA. Confirmez pour simuler le succès."
            ),
            extra={"operateur": operateur, "telephone": telephone},
        )

    def verify(self, *, reference_interne, reference_externe) -> VerifyResult:
        # En simulation, la vérification seule ne décide pas : c'est /confirm qui tranche.
        return VerifyResult(statut="pending", reference_externe=reference_externe)
