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

import json
from datetime import datetime
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.config import CORS_ORIGINS, WEB_DIR
from backend.db import init_saas_schema
from backend.deps import get_current_user_optional, plan_of
from backend.plans import plan_at_least
from backend.routes_admin import router as admin_router
from backend.routes_auth import router as auth_router
from backend.routes_billing import router as billing_router
from backend.routes_alertes import router as alertes_router
from backend.routes_api import router as api_v1_router
from backend.routes_coffre import router as coffre_router
from backend.routes_data import router as data_router
from backend.routes_dossiers import router as dossiers_router
from backend.routes_equipe import router as equipe_router
from backend.routes_groupements import router as groupements_router
from backend.routes_intel import router as intel_router
from backend.routes_notifications import router as notifications_router
from backend.routes_profil import router as profil_router
from backend.routes_public import router as public_router
from backend.routes_radar import router as radar_router
from backend.routes_suivis import router as suivis_router
from backend.routes_support import router as support_router

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
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(data_router)
app.include_router(suivis_router)
app.include_router(notifications_router)
app.include_router(profil_router)
app.include_router(intel_router)
app.include_router(radar_router)
app.include_router(dossiers_router)
app.include_router(alertes_router)
app.include_router(groupements_router)
app.include_router(equipe_router)
app.include_router(coffre_router)
app.include_router(api_v1_router)
app.include_router(public_router)
app.include_router(support_router)


@app.middleware("http")
async def _no_cache_ui(request: Request, call_next):
    response = await call_next(request)
    p = request.url.path.lower()
    if p.endswith(".html") or p.endswith("shell.js") or p.endswith("ui.js"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


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
    "assistant": "/markets.html",
    "directory": "/dashboard.html",
    "intelligence": "/authorities.html",
    "search": "/markets.html",
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

PDF_DIR = WEB_DIR.parent.parent / "telechargements_pdf"
CALENDAR_FILE = WEB_DIR.parent.parent / "data_bulletins_calendrier.json"

_CALENDAR_CACHE: dict = {"mtime": 0, "map": {}}

def _lookup_bulletin_date(filename: str) -> tuple[int | None, int | None, str | None]:
    """Extrait l'année, le mois et la date d'un bulletin PDF depuis data_bulletins_calendrier.json."""
    if not CALENDAR_FILE.exists():
        return None, None, None
    try:
        cur_mtime = CALENDAR_FILE.stat().st_mtime
        if cur_mtime != _CALENDAR_CACHE["mtime"]:
            data = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
            m = {}
            for b in data:
                fn = (b.get("pdf_filename") or "").strip().lower()
                if fn:
                    m[fn] = (b.get("year"), b.get("month"), b.get("date"))
            _CALENDAR_CACHE["mtime"] = cur_mtime
            _CALENDAR_CACHE["map"] = m
        clean_key = filename.strip().lower()
        return _CALENDAR_CACHE["map"].get(clean_key, (None, None, None))
    except Exception:
        return None, None, None


@app.get("/bulletins_pdf/{filename:path}")
def serve_bulletin_pdf(filename: str, request: Request):
    """
    Sert les bulletins PDF officiels avec contrôle d'accès SaaS :
    - Bulletin du mois en cours : accessible à tous (gratuit / visiteur).
    - Archives des mois antérieurs : réservées aux offres Pro et Entreprise.
    """
    clean_fn = unquote(filename).strip()
    pdf_path = (PDF_DIR / clean_fn).resolve()

    # Contrôle de sécurité contre le directory traversal
    if not pdf_path.exists() or not pdf_path.is_file() or not pdf_path.is_relative_to(PDF_DIR.resolve()):
        raise HTTPException(status_code=404, detail="Bulletin PDF introuvable.")

    b_year, b_month, b_date = _lookup_bulletin_date(clean_fn)
    now = datetime.now()
    current_year, current_month = now.year, now.month

    # Si le bulletin est du mois en cours, accès libre pour tous
    is_current_month = (b_year == current_year and b_month == current_month)

    if not is_current_month:
        user = get_current_user_optional(request)
        user_plan = plan_of(user)

        if not plan_at_least(user_plan, "pro"):
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return RedirectResponse(
                    url=f"/pricing.html?gate=archives_pdf&bulletin={clean_fn}",
                    status_code=303,
                )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "upgrade_required",
                    "feature": "archives_pdf",
                    "bulletin": clean_fn,
                    "bulletin_date": b_date,
                    "plan_requis": "pro",
                    "plan_actuel": user_plan,
                    "message": (
                        "L'accès aux archives PDF des mois précédents est réservé aux offres Pro et Entreprise. "
                        "L'offre gratuite permet de consulter les bulletins officiels du mois en cours."
                    ),
                },
            )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=clean_fn,
        content_disposition_type="inline",
    )



