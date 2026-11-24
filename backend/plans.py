#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/plans.py
================
SOURCE DE VÉRITÉ des offres (tiers) du SaaS Veille BF.

Prix PROVISOIRES — ajustez librement ici (ou en base via migrate_saas.py).
Les capacités (`features`) sont vérifiées côté serveur (deps.require_feature)
et reflétées côté front.
"""

from __future__ import annotations

# Capacités connues (clés de features)
FEAT_RECHERCHE = "recherche"             # recherche de marchés
FEAT_FICHES = "fiches"                   # fiches marché détaillées
FEAT_RESULTATS = "resultats"             # section Résultats / attributaires (complet)
FEAT_ENTREPRISES = "entreprises"         # répertoire Entreprises (CRM soumissionnaires)
FEAT_ALERTES = "alertes"                 # alertes email/WhatsApp
FEAT_EXPORT = "export"                   # export CSV / Excel
FEAT_API = "api"                         # accès API + clés
FEAT_EQUIPE = "equipe"                   # multi-utilisateurs

# -1 = illimité
PLANS: dict[str, dict] = {
    "gratuit": {
        "id": "gratuit",
        "nom": "Gratuit",
        "sous_titre": "Pour découvrir la veille des marchés publics",
        "prix_mensuel_fcfa": 0,
        "prix_annuel_fcfa": 0,
        "ordre": 0,
        "features": {
            FEAT_RECHERCHE: True,
            FEAT_FICHES: True,
            FEAT_RESULTATS: False,   # aperçu flouté seulement
            FEAT_ENTREPRISES: False,
            FEAT_ALERTES: False,
            FEAT_EXPORT: False,
            FEAT_API: False,
            FEAT_EQUIPE: False,
        },
        "quotas": {
            "recherches_par_jour": 15,
            "fiches_par_jour": 10,
        },
        "support": "Communauté",
        "limites": {
            "utilisateurs": "1",
            "historique": "30 derniers jours",
            "recherches_jour": "15 / jour",
            "fiches_jour": "10 / jour",
        },
        "mise_en_avant": [
            "Recherche de base dans les marchés",
            "Jusqu'à 10 fiches détaillées par jour",
            "Aperçu des résultats d'attribution",
        ],
    },
    "pro": {
        "id": "pro",
        "nom": "Pro",
        "sous_titre": "Pour les entreprises qui répondent aux appels d'offres",
        "prix_mensuel_fcfa": 15000,
        "prix_annuel_fcfa": 150000,
        "ordre": 1,
        "features": {
            FEAT_RECHERCHE: True,
            FEAT_FICHES: True,
            FEAT_RESULTATS: True,
            FEAT_ENTREPRISES: True,
            FEAT_ALERTES: True,
            FEAT_EXPORT: True,
            FEAT_API: False,
            FEAT_EQUIPE: False,
        },
        "quotas": {
            "recherches_par_jour": -1,
            "fiches_par_jour": -1,
        },
        "support": "Email sous 48 h",
        "limites": {
            "utilisateurs": "1",
            "historique": "Complet",
            "recherches_jour": "Illimité",
            "fiches_jour": "Illimité",
        },
        "mise_en_avant": [
            "Recherche et fiches illimitées",
            "Résultats et attributaires complets",
            "Répertoire des entreprises soumissionnaires",
            "Alertes email & WhatsApp",
            "Export CSV / Excel",
        ],
    },
    "entreprise": {
        "id": "entreprise",
        "nom": "Entreprise",
        "sous_titre": "Pour les équipes et les intégrations sur mesure",
        "prix_mensuel_fcfa": 50000,
        "prix_annuel_fcfa": 500000,
        "ordre": 2,
        "features": {
            FEAT_RECHERCHE: True,
            FEAT_FICHES: True,
            FEAT_RESULTATS: True,
            FEAT_ENTREPRISES: True,
            FEAT_ALERTES: True,
            FEAT_EXPORT: True,
            FEAT_API: True,
            FEAT_EQUIPE: True,
        },
        "quotas": {
            "recherches_par_jour": -1,
            "fiches_par_jour": -1,
        },
        "support": "Prioritaire",
        "limites": {
            "utilisateurs": "Jusqu'à 5",
            "historique": "Complet",
            "recherches_jour": "Illimité",
            "fiches_jour": "Illimité",
        },
        "mise_en_avant": [
            "Tout l'offre Pro",
            "Accès API + clés développeur",
            "Comptes multi-utilisateurs (équipe)",
            "Support prioritaire",
        ],
    },
}

DEFAULT_PLAN = "gratuit"
PLAN_ORDER = ["gratuit", "pro", "entreprise"]


def get_plan(plan_id: str | None) -> dict:
    """Renvoie la définition d'un plan, ou le plan par défaut si inconnu."""
    return PLANS.get((plan_id or "").lower(), PLANS[DEFAULT_PLAN])


def has_feature(plan_id: str | None, feature: str) -> bool:
    """Le plan donne-t-il accès à la capacité demandée ?"""
    return bool(get_plan(plan_id).get("features", {}).get(feature, False))


def get_quota(plan_id: str | None, quota_key: str) -> int:
    """Quota numérique d'un plan (-1 = illimité, 0 par défaut si inconnu)."""
    return int(get_plan(plan_id).get("quotas", {}).get(quota_key, 0))


def plan_rank(plan_id: str | None) -> int:
    """Rang hiérarchique d'un plan (gratuit=0 < pro=1 < entreprise=2)."""
    pid = (plan_id or DEFAULT_PLAN).lower()
    return PLAN_ORDER.index(pid) if pid in PLAN_ORDER else 0


def plan_at_least(plan_id: str | None, minimum: str) -> bool:
    """Vrai si le plan courant est >= au plan minimum requis."""
    return plan_rank(plan_id) >= plan_rank(minimum)


def public_plans() -> list[dict]:
    """Représentation publique des offres pour le front (page Tarifs)."""
    out = []
    for pid in PLAN_ORDER:
        p = PLANS[pid]
        out.append({
            "id": p["id"],
            "nom": p["nom"],
            "sous_titre": p["sous_titre"],
            "prix_mensuel_fcfa": p["prix_mensuel_fcfa"],
            "prix_annuel_fcfa": p["prix_annuel_fcfa"],
            "features": p["features"],
            "quotas": p["quotas"],
            "support": p.get("support", ""),
            "limites": p.get("limites", {}),
            "mise_en_avant": p["mise_en_avant"],
        })
    return out
