#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/main.py
===============
Assemble l'application FastAPI du SaaS Veille BF :
  - CORS (restreint, credentials activés pour les cookies de session)
  - routers : auth, billing, données métier
  - service des pages HTML statiques + assets
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.config import CORS_ORIGINS, WEB_DIR
from backend.db import init_saas_schema
from backend.routes_auth import router as auth_router
from backend.routes_billing import router as billing_router
from backend.routes_alertes import router as alertes_router
from backend.routes_data import router as data_router
from backend.routes_dossiers import router as dossiers_router
from backend.routes_intel import router as intel_router
from backend.routes_notifications import router as notifications_router
from backend.routes_profil import router as profil_router
from backend.routes_radar import router as radar_router
from backend.routes_suivis import router as suivis_router

app = FastAPI(
    title="Veille BF — SaaS Marchés Publics",
    description="Plateforme SaaS de veille des marchés publics du Burkina Faso (DGCMEF).",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Garantit la présence des tables SaaS même si migrate_saas.py n'a pas été lancé.
    init_saas_schema()


# ----------------- Routers API -----------------
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(data_router)
app.include_router(suivis_router)
app.include_router(notifications_router)
app.include_router(profil_router)
app.include_router(intel_router)
app.include_router(radar_router)
app.include_router(dossiers_router)
app.include_router(alertes_router)


# ----------------- Pages & redirections -----------------
# Anciennes pages neutralisées (redirigées). login/register/forgot/checkout/account/
# pricing sont désormais de vraies pages et NE sont PAS redirigées.
LEGACY_REDIRECTS = {
    "upgrade": "/pricing.html",
    "experts": "/authorities.html",
    "companies": "/entreprises.html",
    "authority": "/authorities.html",
    "applications": "/markets.html",
    "capability-profile": "/dashboard.html",
    "assistant": "/search.html",
    "recommendations": "/markets.html",
    "alerts": "/markets.html",
}


# Routes propres (URLs lisibles en français) -> page HTML servie, URL conservée.
FRIENDLY_ROUTES = {
    "accueil": "accueil",
    "offres": "pricing",
    "tarifs": "pricing",
    "connexion": "login",
    "inscription": "register",
    "mot-de-passe-oublie": "forgot-password",
    "compte": "account",
    "paiement": "checkout",
    "tableau-de-bord": "dashboard",
    "mes-marches": "suivis",
    "mon-espace": "profil",
    "profil": "profil",
    "radar": "radar",
    "intelligence": "intelligence",
    "marches": "markets",
    "resultats": "resultats",
    "entreprises": "entreprises",
    "autorites": "authorities",
    "bulletins": "directory",
    "recherche": "search",
}


def _serve_page(page: str):
    file_path = WEB_DIR / f"{page}.html"
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Page introuvable")


@app.get("/")
def index():
    # Page d'accueil publique explicative (repli : dashboard si absente).
    if (WEB_DIR / "accueil.html").exists():
        return _serve_page("accueil")
    return RedirectResponse(url="/dashboard.html")


@app.get("/{page}.html")
def serve_html(page: str):
    if page in LEGACY_REDIRECTS:
        return RedirectResponse(url=LEGACY_REDIRECTS[page])
    return _serve_page(page)


@app.get("/{slug}")
def serve_friendly(slug: str):
    # Alias d'URL propres -> fichier HTML (sert sans changer l'URL).
    if slug in FRIENDLY_ROUTES:
        return _serve_page(FRIENDLY_ROUTES[slug])
    raise HTTPException(status_code=404, detail="Page introuvable")


if (WEB_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")
