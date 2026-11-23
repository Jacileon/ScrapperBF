#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server_front.py
===============
Serveur Web & API REST haute performance pour la plateforme Veille BF
Alimenté directement par SQLite marches_publics_burkina.db.

Usage :
    python server_front.py
    (Accessible sur http://127.0.0.1:8000)
"""

import os
import json
import sqlite3
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = Path("marches_publics_burkina.db")
WEB_DIR = Path("web/app")

app = FastAPI(
    title="Veille BF - API Marchés Publics",
    description="API REST et Portail d'exploration des marchés publics du Burkina Faso (DGCMEF)",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ----------------- ROUTES STATIQUES & REDIRECTIONS -----------------
LEGACY_REDIRECTS = {
    "upgrade": "/markets.html",
    "experts": "/authorities.html",
    "companies": "/authorities.html",
    "authority": "/authorities.html",
    "applications": "/markets.html",
    "capability-profile": "/dashboard.html",
    "assistant": "/search.html",
    "recommendations": "/markets.html",
    "alerts": "/markets.html",
    "login": "/dashboard.html",
    "register": "/dashboard.html",
    "forgot-password": "/dashboard.html",
}

@app.get("/")
def index():
    return RedirectResponse(url="/dashboard.html")

@app.get("/{page}.html")
def serve_html(page: str):
    if page in LEGACY_REDIRECTS:
        return RedirectResponse(url=LEGACY_REDIRECTS[page])
    file_path = WEB_DIR / f"{page}.html"
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Page introuvable")

if (WEB_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")

# ----------------- ROUTES API REST -----------------
@app.get("/api/stats")
def get_stats():
    """Statistiques consolidées en direct de la base SQLite"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*), SUM(COALESCE(budget_previsionnel_fcfa, 0)) FROM annonces_avis")
    tot_annonces, tot_budget = c.fetchone()
    
    c.execute("SELECT COUNT(*) FROM detail_lots")
    tot_lots = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT numero_bulletin) FROM annonces_avis")
    tot_bulletins = c.fetchone()[0]

    # Audit qualité : marchés conformes vs à vérifier (les avis déjà vérifiés sont comptés comme conformes)
    c.execute("""
        SELECT COUNT(*) FROM annonces_avis 
        WHERE (remarque NOT LIKE '%Vérifié%' AND remarque NOT LIKE '%verifie%')
          AND (
               (remarque IS NOT NULL AND remarque != '' AND remarque != 'null') 
            OR budget_previsionnel_fcfa IS NULL 
            OR budget_previsionnel_fcfa = 0
            OR reference_dossier IS NULL 
            OR reference_dossier = ''
            OR reference_dossier = 'null'
          )
    """)
    review_count = c.fetchone()[0]
    compliant_count = tot_annonces - review_count

    # Répartition catégories
    c.execute("""
        SELECT COALESCE(categorie_marche, 'Autre'), COUNT(*), SUM(COALESCE(budget_previsionnel_fcfa, 0))
        FROM annonces_avis GROUP BY 1 ORDER BY 2 DESC
    """)
    categories = [{"categorie": r[0], "count": r[1], "budget_fcfa": r[2]} for r in c.fetchall()]

    # Répartition secteurs métier
    c.execute("""
        SELECT COALESCE(secteur_activite, 'Services Généraux & Divers'), COUNT(*), SUM(COALESCE(budget_previsionnel_fcfa, 0))
        FROM annonces_avis GROUP BY 1 ORDER BY 2 DESC
    """)
    sectors = [{"sector": r[0], "count": r[1], "budget_fcfa": r[2]} for r in c.fetchall()]

    # Répartition types
    c.execute("SELECT COALESCE(type_procedure, 'Autre'), COUNT(*) FROM annonces_avis GROUP BY 1 ORDER BY 2 DESC")
    types_proc = [{"type": r[0], "count": r[1]} for r in c.fetchall()]

    conn.close()
    return {
        "total_annonces": tot_annonces,
        "total_budget_fcfa": tot_budget,
        "budget_formate": f"{round(tot_budget / 1e9, 2)} Md FCFA".replace(".", ","),
        "total_lots": tot_lots,
        "total_bulletins": tot_bulletins,
        "compliant_count": compliant_count,
        "review_count": review_count,
        "categories": categories,
        "sectors": sectors,
        "types_procedures": types_proc
    }

@app.get("/api/markets")
def list_markets(
    q: Optional[str] = Query(None, description="Mots-clés dans objet, autorité, référence"),
    categorie: Optional[str] = Query(None, description="Travaux, Fournitures, Prestations..."),
    sector: Optional[str] = Query(None, description="Secteur métier (BTP, Santé, Informatique...)"),
    type_proc: Optional[str] = Query(None, description="Demande de prix, Appel d'offres..."),
    remarque: Optional[str] = Query(None, description="Filtre par remarque d'extraction"),
    needs_review: Optional[bool] = Query(None, description="Marchés nécessitant une vérification humaine"),
    min_budget: Optional[int] = Query(None, description="Budget minimum en FCFA"),
    max_budget: Optional[int] = Query(None, description="Budget maximum en FCFA"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Recherche paginée de marchés avec filtres multicritères et filtre qualité"""
    conn = get_db()
    c = conn.cursor()

    conditions = []
    params = []

    if q:
        like_q = f"%{q}%"
        conditions.append("(objet_marche LIKE ? OR autorite_contractante LIKE ? OR reference_dossier LIKE ? OR ministere_tutelle LIKE ?)")
        params.extend([like_q, like_q, like_q, like_q])

    if categorie:
        conditions.append("categorie_marche LIKE ?")
        params.append(f"%{categorie}%")

    if sector:
        conditions.append("secteur_activite LIKE ?")
        params.append(f"%{sector}%")

    if type_proc:
        conditions.append("type_procedure LIKE ?")
        params.append(f"%{type_proc}%")

    if needs_review is True:
        conditions.append("(remarque NOT LIKE '%Vérifié%' AND remarque NOT LIKE '%verifie%') AND ((remarque IS NOT NULL AND remarque != '' AND remarque != 'null') OR budget_previsionnel_fcfa IS NULL OR budget_previsionnel_fcfa = 0 OR reference_dossier IS NULL OR reference_dossier = '' OR reference_dossier = 'null')")
    elif needs_review is False:
        conditions.append("(remarque LIKE '%Vérifié%' OR remarque LIKE '%verifie%' OR ((remarque IS NULL OR remarque = '' OR remarque = 'null') AND budget_previsionnel_fcfa > 0 AND reference_dossier IS NOT NULL AND reference_dossier != '' AND reference_dossier != 'null'))")

    if remarque:
        conditions.append("remarque LIKE ?")
        params.append(f"%{remarque}%")

    if min_budget is not None:
        conditions.append("budget_previsionnel_fcfa >= ?")
        params.append(min_budget)

    if max_budget is not None:
        conditions.append("budget_previsionnel_fcfa <= ?")
        params.append(max_budget)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Count total
    c.execute(f"SELECT COUNT(*) FROM annonces_avis {where_clause}", params)
    total = c.fetchone()[0]

    # Query items
    query = f"""
        SELECT id, numero_bulletin, date_parution, pages, categorie_marche, type_procedure,
               reference_dossier, autorite_contractante, ministere_tutelle, objet_marche,
               allotissement_type, nombre_lots, budget_previsionnel_fcfa, date_limite_depot,
               heure_limite_depot, source_financement, remarque, secteur_activite
        FROM annonces_avis
        {where_clause}
        ORDER BY rowid ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": rows
    }

@app.get("/api/markets/{market_id}")
def get_market(market_id: str):
    """Fiche exhaustive d'un marché avec tous ses lots relationnels"""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM annonces_avis WHERE id = ?", (market_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Marché non trouvé")

    market_data = dict(row)
    c.execute("SELECT numero_lot, titre, description, montant_fcfa, caution_fcfa FROM detail_lots WHERE annonce_id = ?", (market_id,))
    market_data["lots"] = [dict(r) for r in c.fetchall()]

    conn.close()
    return market_data

@app.get("/api/lots")
def list_lots(
    q: Optional[str] = Query(None, description="Titre ou description du lot"),
    limit: int = Query(50, ge=1, le=200)
):
    """Recherche parmi les 946 lots relationnels de la base"""
    conn = get_db()
    c = conn.cursor()
    if q:
        c.execute("""
            SELECT l.*, a.autorite_contractante, a.date_limite_depot 
            FROM detail_lots l 
            JOIN annonces_avis a ON l.annonce_id = a.id
            WHERE l.titre LIKE ? OR l.description LIKE ?
            LIMIT ?
        """, (f"%{q}%", f"%{q}%", limit))
    else:
        c.execute("""
            SELECT l.*, a.autorite_contractante, a.date_limite_depot 
            FROM detail_lots l 
            JOIN annonces_avis a ON l.annonce_id = a.id
            LIMIT ?
        """, (limit,))
    lots = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": len(lots), "lots": lots}

@app.get("/api/authorities")
def list_authorities(
    q: Optional[str] = Query(None, description="Nom ou tutelle"),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Liste exhaustive des 246 autorités contractantes réelles avec leurs métriques consolidées"""
    conn = get_db()
    c = conn.cursor()
    conditions = ["autorite_contractante IS NOT NULL", "autorite_contractante != ''"]
    params = []
    if q:
        conditions.append("(autorite_contractante LIKE ? OR ministere_tutelle LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    where_sql = "WHERE " + " AND ".join(conditions)

    c.execute(f"""
        SELECT autorite_contractante as name,
               MAX(ministere_tutelle) as ministry,
               MAX(lieu_depot_offres) as lieu_depot,
               COUNT(*) as count,
               SUM(COALESCE(budget_previsionnel_fcfa, 0)) as total_amount,
               SUM(COALESCE(nombre_lots, 1)) as total_lots
        FROM annonces_avis
        {where_sql}
        GROUP BY autorite_contractante
        ORDER BY count DESC, total_amount DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": len(rows), "results": rows}

@app.get("/api/authorities/{authority_name:path}")
def get_authority(authority_name: str):
    """Fiche détaillée exhaustive d'une autorité contractante avec tous ses marchés réels"""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM annonces_avis
        WHERE autorite_contractante = ?
        ORDER BY date_limite_depot DESC, rowid DESC
    """, (authority_name,))
    markets = [dict(r) for r in c.fetchall()]

    if not markets:
        c.execute("""
            SELECT * FROM annonces_avis
            WHERE autorite_contractante LIKE ?
            ORDER BY date_limite_depot DESC, rowid DESC
        """, (f"%{authority_name}%",))
        markets = [dict(r) for r in c.fetchall()]

    if not markets:
        conn.close()
        raise HTTPException(status_code=404, detail="Autorité non trouvée")

    tot_budget = sum(m.get("budget_previsionnel_fcfa") or 0 for m in markets)
    tot_lots = sum(m.get("nombre_lots") or 1 for m in markets)

    categories = {}
    procedures = {}
    financements = {}
    lieux_depot = set()
    contacts = set()

    for m in markets:
        cat = m.get("categorie_marche") or "Non spécifiée"
        categories[cat] = categories.get(cat, 0) + 1
        proc = m.get("type_procedure") or "Non spécifiée"
        procedures[proc] = procedures.get(proc, 0) + 1
        fin = m.get("source_financement")
        if fin and len(fin.strip()) > 2:
            financements[fin.strip()] = financements.get(fin.strip(), 0) + 1
        ld = m.get("lieu_depot_offres")
        if ld and len(ld.strip()) > 3:
            lieux_depot.add(ld.strip())
        ct = m.get("contacts_renseignements")
        if ct and len(ct.strip()) > 3:
            contacts.add(ct.strip())

    conn.close()
    return {
        "name": markets[0].get("autorite_contractante"),
        "ministry": markets[0].get("ministere_tutelle"),
        "total_markets": len(markets),
        "total_budget_fcfa": tot_budget,
        "total_lots": tot_lots,
        "categories": categories,
        "procedures": procedures,
        "financements": financements,
        "lieux_depot": list(lieux_depot),
        "contacts": list(contacts),
        "markets": markets
    }

@app.get("/api/refresh")
def refresh_cache():
    """Déclenche la ré-exportation de la base vers data.js"""
    from export_db_to_front import export_data
    export_data()
    return {"status": "ok", "message": "Cache data.js et data.json régénérés avec succès"}

@app.get("/api/export/csv")
def export_csv_file():
    """Génère et télécharge le fichier CSV complet de la base"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM annonces_avis ORDER BY rowid ASC")
    rows = c.fetchall()
    
    headers = [col[0] for col in c.description]
    csv_lines = [";".join(headers)]
    for r in rows:
        line = []
        for val in r:
            if val is None:
                line.append("")
            else:
                s = str(val).replace(";", ",").replace("\n", " ").replace("\r", "")
                line.append(s)
        csv_lines.append(";".join(line))
    conn.close()

    content = "\ufeff" + "\n".join(csv_lines)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marches_publics_burkina_complet.csv"}
    )

if __name__ == "__main__":
    print("=" * 70)
    print(" VEILLE BF - SERVEUR FRONT & API MARCHE PUBLICS (FASTAPI)")
    print("=" * 70)
    print(" Serveur démarré sur : http://127.0.0.1:8000")
    print(" - Tableau de bord   : http://127.0.0.1:8000/dashboard.html")
    print(" - Liste des marchés : http://127.0.0.1:8000/markets.html")
    print(" - Recherche avancée : http://127.0.0.1:8000/search.html")
    print(" - Documentation API : http://127.0.0.1:8000/docs")
    print("=" * 70)
    uvicorn.run("server_front:app", host="127.0.0.1", port=8000, log_level="info")
