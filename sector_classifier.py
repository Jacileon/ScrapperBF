#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sector_classifier.py
====================
Moteur de classification sectorielle métier pour les marchés publics du Burkina Faso.
Utilisé pour déterminer automatiquement le secteur d'activité métier lors de l'extraction
et du chargement des annonces (DGCMEF).
"""

import re
import unicodedata
from typing import Optional

def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFD', str(text))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.lower()

SECTOR_CONFIG = [
    {
        "name": "Informatique & Télécoms",
        "patterns": [
            r'informatique', r'ordinateur', r'serveur', r'logiciel', r'licence',
            r'fibre optique', r't[eé]l[eé]com', r'portail web', r'site web',
            r'r[eé]seau local', r'interconnexion', r'imprimante', r'scanner',
            r'photocopieur', r'consommables? informatiques?', r'cybers[eé]curit[eé]',
            r'radiocommunication', r'biom[eé]tri', r'mat[eé]riel informatique',
            r'arcep', r'antenne samu', r'syst[eè]me int[eé]gr[eé]'
        ]
    },
    {
        "name": "Eau, Forages & Assainissement",
        "patterns": [
            r'forage', r'ch[aâ]teau d[\'’]eau', r'bornes? fontaines?', r'aepps',
            r'adduction d[\'’]eau', r'hydraulique', r'assainissement', r'latrine',
            r'motricit[eé] humaine', r'pompage', r'plomberie sanitaire', r'dalot',
            r'caniveau', r'bassin hydrographique'
        ]
    },
    {
        "name": "Énergie & Électricité",
        "patterns": [
            r'[eé]lectricit[eé]', r'[eé]lectrique', r'[eé]lectrification',
            r'transformateur', r'lampadaires? solaire', r'photovolta[iï]que',
            r'groupes? [eé]lectrog[eè]ne', r'compteurs? d[\'’][eé]nergie',
            r'lignes? [eé]lectrique', r'c[aâ]bles? [eé]lectrique', r'[eé]clairage public',
            r'sonabel'
        ]
    },
    {
        "name": "Santé, Médical & Pharmacie",
        "patterns": [
            r'm[eé]dica[ulx]', r'm[eé]dicament', r'r[eé]actif', r'seringue',
            r'hospitali[eé]r', r'biom[eé]dical', r'pansement', r'laboratoire',
            r'radiologie', r'soins', r'vaccin', r'ophtalmo', r'pharmacie',
            r'matern[eé]t[eé]', r'csps', r'sant[eé]', r'cameg', r'chru', r'chup', r'samu'
        ]
    },
    {
        "name": "Véhicules, Transports & Hydrocarbures",
        "patterns": [
            r'mat[eé]riels? roulant', r'v[eé]hicule', r'motos?\b', r'pneumatique',
            r'pi[eè]ces? de rechange', r'vidange', r'engins? tp', r'camion',
            r'ambulance', r'carburant', r'hydrocarbure', r'p[eé]troli[eè]r',
            r'sonabhy', r'ccva', r'mat[eé]riel de transport'
        ]
    },
    {
        "name": "Gardiennage & Sécurité",
        "patterns": [
            r'gardiennage', r'surveillance', r's[eé]curit[eé]', r'vigiles?',
            r'extincteur', r's[eé]curisation', r's[uû]ret[eé]', r'vdp'
        ]
    },
    {
        "name": "Mobilier & Fournitures de Bureau",
        "patterns": [
            r'fournitures? de bureau', r'mobiliers? de bureau', r'tables? bancs?',
            r'mobiliers? scolaire', r'registres?', r'papiers? rame', r'cartouches?',
            r'mat[eé]riels? de bureau', r'consommables? de bureau', r'fournitures? scolaires?'
        ]
    },
    {
        "name": "Restauration & Événementiel",
        "patterns": [
            r'restauration', r'pause[- ]caf[eé]', r'pause[- ]d[eé]jeuner',
            r'repas', r'vivres', r'denr[eé]es? alimentaire', r'cantine',
            r'h[eé]bergement', r'traiteur', r'pause'
        ]
    },
    {
        "name": "Agriculture, Élevage & Forêt",
        "patterns": [
            r'semence', r'engrais', r'intrants? agricole', r'agricole',
            r'pastoral', r'b[eé]tail', r'v[eé]t[eé]rinaire', r'reboisement',
            r'environnement', r'for[eê]t', r'p[eê]che', r'am[eé]nagement hydro[- ]agricole',
            r'jardinage', r'apiculture', r'd[eé]chets? solides?'
        ]
    },
    {
        "name": "BTP, Génie Civil & Construction",
        "patterns": [
            r'construction', r'r[eé]habilitation', r'b[aâ]timent', r'mur de cl[oô]ture',
            r'pavage', r'voirie', r'hangar', r'terrassement', r'boutique',
            r'piste', r'am[eé]nagement', r'g[eé]nie civil', r'[eé]tanch[eé]it[eé]',
            r'peinture', r'r[eé]fection', r'auberge', r'salles? de classe',
            r'travaux de', r'travaux'
        ]
    },
    {
        "name": "Études, Audit & Conseil",
        "patterns": [
            r'[eé]tudes?', r'ma[iî]trise d[\'’]oeuvre', r'audit', r'contr[oô]le technique',
            r'formation', r'renforcement de capacit[eé]', r'commissariat aux comptes',
            r'consultant', r'diagnostic', r'[eé]valuation', r'[eé]laboration',
            r'assistance technique', r'suivi[- ]contr[oô]le', r'architecture'
        ]
    },
    {
        "name": "Agréments & Répertoires Fournisseurs",
        "patterns": [
            r'base de donn[eé]es? de fournisseurs', r'r[eé]pertoire des? prestataires',
            r'r[eé]pertoire de fournisseurs', r'constitution d[\'’]une liste de candidats',
            r'candidats potentiels', r'manifestation d[\'’]int[eé]r[eê]t pour la constitution'
        ]
    }
]

LISTE_SECTEURS = [
    "BTP, Génie Civil & Construction",
    "Services Généraux & Divers",
    "Santé, Médical & Pharmacie",
    "Eau, Forages & Assainissement",
    "Informatique & Télécoms",
    "Véhicules, Transports & Hydrocarbures",
    "Énergie & Électricité",
    "Mobilier & Fournitures de Bureau",
    "Agréments & Répertoires Fournisseurs",
    "Gardiennage & Sécurité",
    "Études, Audit & Conseil",
    "Agriculture, Élevage & Forêt",
    "Restauration & Événementiel"
]

def classify_sector(objet: Optional[str], categorie: Optional[str] = None, autorite: Optional[str] = None) -> str:
    """
    Règle de classification d'un marché public par secteur d'activité métier.
    Priorité 1 : Mots-clés discriminants dans l'objet de la commande.
    Priorité 2 : Mots-clés dans la combinaison (objet + catégorie + autorité).
    Défaut : 'Services Généraux & Divers'.
    """
    norm_title = normalize_text(objet or "")
    norm_all = normalize_text(f"{objet or ''} {categorie or ''} {autorite or ''}")

    # Priorité 1 : Titre / Objet (le besoin réel)
    for sec in SECTOR_CONFIG:
        for p in sec["patterns"]:
            if re.search(r'\b' + p, norm_title):
                return sec["name"]

    # Priorité 2 : Contexte étendu (catégorie + autorité)
    for sec in SECTOR_CONFIG:
        for p in sec["patterns"]:
            if re.search(r'\b' + p, norm_all):
                return sec["name"]

    return "Services Généraux & Divers"
