#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/config.py
=================
Configuration centrale du SaaS Veille BF. Tout est pilotable par variables
d'environnement (voir .env.example). Des valeurs de secours raisonnables sont
fournies pour le développement local.
"""

import os
from pathlib import Path

# Racine du projet (…/ScrapperBF)
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Base de données ---
# Postgres (Supabase) en production/SaaS : chaîne de connexion libpq ou URI.
#   ex : postgresql://user:pwd@host:6543/postgres?sslmode=require
# Fournie par VEILLEBF_DATABASE_URL (ou DATABASE_URL). Si absente, on retombe
# sur la base SQLite locale (pipeline / dev hors-ligne).
DATABASE_URL = os.getenv("VEILLEBF_DATABASE_URL") or os.getenv("DATABASE_URL", "")
# Base SQLite historique (pipeline d'ingestion + repli dev si DATABASE_URL vide).
DB_PATH = Path(os.getenv("VEILLEBF_DB", BASE_DIR / "marches_publics_burkina.db"))

# --- Dossier du front statique ---
WEB_DIR = Path(os.getenv("VEILLEBF_WEB_DIR", BASE_DIR / "web" / "app"))

# --- Sécurité / JWT ---
# IMPORTANT : en production, définir VEILLEBF_JWT_SECRET (chaîne longue et aléatoire).
JWT_SECRET = os.getenv("VEILLEBF_JWT_SECRET", "dev-secret-CHANGEZ-MOI-en-production")
JWT_ALGO = "HS256"
JWT_TTL_SECONDS = int(os.getenv("VEILLEBF_JWT_TTL", str(60 * 60 * 24 * 7)))  # 7 jours

# Nom du cookie de session et options
SESSION_COOKIE = "veillebf_session"
# Secure=True exige HTTPS ; en dev local (http) on le laisse à False.
COOKIE_SECURE = os.getenv("VEILLEBF_COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = os.getenv("VEILLEBF_COOKIE_SAMESITE", "lax")

# --- URL publique (pour les retours de paiement) ---
PUBLIC_URL = os.getenv("VEILLEBF_PUBLIC_URL", "http://127.0.0.1:8000")

# --- CORS ---
# Liste d'origines séparées par des virgules. "*" déconseillé avec cookies.
_cors = os.getenv("VEILLEBF_CORS_ORIGINS", PUBLIC_URL)
CORS_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]

# --- Fournisseur de paiement ---
# "leekpay" (Mobile Money & Carte), "sandbox" (simulation), "manual" (activation manuelle).
PAYMENT_PROVIDER = os.getenv("VEILLEBF_PAYMENT_PROVIDER", "leekpay").lower()

# LeekPay (Agrégateur Mobile Money Orange / Moov / Wave / Carte)
# IMPORTANT : ne JAMAIS coder les clés en dur ici. Elles viennent uniquement de
# l'environnement (.env en local, variables d'environnement Vercel en prod).
LEEKPAY_PUBLIC_KEY = os.getenv("LEEKPAY_PUBLIC_KEY", "")
LEEKPAY_SECRET_KEY = os.getenv("LEEKPAY_SECRET_KEY", "")
LEEKPAY_WEBHOOK_SECRET = os.getenv("LEEKPAY_WEBHOOK_SECRET", "")
LEEKPAY_BASE_URL = os.getenv("LEEKPAY_BASE_URL", "https://leekpay.fr").rstrip("/")

# Clés du fournisseur générique (compatibilité)
PROVIDER_API_KEY = os.getenv("VEILLEBF_PROVIDER_API_KEY", LEEKPAY_SECRET_KEY)
PROVIDER_SITE_ID = os.getenv("VEILLEBF_PROVIDER_SITE_ID", LEEKPAY_PUBLIC_KEY)
PROVIDER_SECRET = os.getenv("VEILLEBF_PROVIDER_SECRET", LEEKPAY_WEBHOOK_SECRET)

# --- Divers ---
IS_DEV = os.getenv("VEILLEBF_ENV", "dev").lower() in ("dev", "development", "local")
