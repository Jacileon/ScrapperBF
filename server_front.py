#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server_front.py
===============
Point d'entrée du serveur Veille BF (compat déploiement : `server_front:app`).

L'application est désormais assemblée dans le package `backend/` :
  - backend/main.py     : app FastAPI (CORS, routers, static)
  - backend/routes_*    : auth, facturation (offres/abonnements/paiement), données
  - backend/plans.py    : les 3 offres (Gratuit / Pro / Entreprise)
  - backend/payments/   : fournisseurs de paiement (sandbox, manual, ... )

Usage :
    python server_front.py            # http://127.0.0.1:8000
    (ou en prod : uvicorn server_front:app)
"""

import uvicorn

from backend.main import app  # noqa: F401  (exposé pour `server_front:app`)

if __name__ == "__main__":
    print("=" * 70)
    print(" VEILLE BF - SaaS MARCHES PUBLICS (FASTAPI)")
    print("=" * 70)
    print(" Serveur demarre sur : http://127.0.0.1:8000")
    print(" - Tableau de bord   : http://127.0.0.1:8000/dashboard.html")
    print(" - Offres / Tarifs   : http://127.0.0.1:8000/pricing.html")
    print(" - Connexion         : http://127.0.0.1:8000/login.html")
    print(" - Documentation API : http://127.0.0.1:8000/docs")
    print("=" * 70)
    uvicorn.run("server_front:app", host="127.0.0.1", port=8000, log_level="info")
