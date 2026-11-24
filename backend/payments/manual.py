#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/payments/manual.py
==========================
Activation MANUELLE : le paiement reste "pending" jusqu'à validation par un
administrateur (virement, dépôt Mobile Money hors ligne, facture...).
Utile avant l'obtention d'un compte marchand agrégateur.
"""

from __future__ import annotations

from backend.payments.base import InitResult, PaymentProvider, VerifyResult


class ManualProvider(PaymentProvider):
    name = "manual"

    def init_payment(self, *, reference_interne, montant_fcfa, operateur,
                     telephone, description, metadata) -> InitResult:
        return InitResult(
            mode="manual",
            reference_interne=reference_interne,
            instructions=(
                f"Pour activer votre offre, effectuez le paiement de {montant_fcfa:,} FCFA "
                f"via {operateur} puis communiquez la référence « {reference_interne} » à "
                "notre équipe. L'abonnement sera activé après vérification."
            ),
            extra={"operateur": operateur, "telephone": telephone},
        )

    def verify(self, *, reference_interne, reference_externe) -> VerifyResult:
        return VerifyResult(statut="pending", reference_externe=reference_externe)
