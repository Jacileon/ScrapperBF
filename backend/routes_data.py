#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_data.py
======================
Routes métier (données marchés publics), reprises du serveur d'origine,
enrichies du verrouillage par offre :
  - /api/stats, /api/markets, /api/authorities ... : ouvertes (vitrine),
    avec décompte de quota pour les comptes Gratuit connectés.
  - /api/export/csv        : offre Pro+ (feature "export").
  - /api/resultats         : offre Pro+ (feature "resultats").
  - /api/entreprises       : offre Pro+ (feature "entreprises").
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from backend.db import get_db
from backend.deps import (consume_quota, get_current_user_optional,
                          require_feature)

router = APIRouter(prefix="/api", tags=["data"])


# --------------------------------------------------------------------------- #
# Vitrine (ouvertes, quotas pour le Gratuit connecté)
# --------------------------------------------------------------------------- #
@router.get("/stats")
def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(COALESCE(budget_previsionnel_fcfa, 0)) FROM annonces_avis")
    tot_annonces, tot_budget = c.fetchone()
    tot_budget = tot_budget or 0
    c.execute("SELECT COUNT(*) FROM detail_lots")
    tot_lots = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT numero_bulletin) FROM annonces_avis")
    tot_bulletins = c.fetchone()[0]
    c.execute(
        """SELECT COALESCE(categorie_marche, 'Autre'), COUNT(*), SUM(COALESCE(budget_previsionnel_fcfa, 0))
           FROM annonces_avis GROUP BY 1 ORDER BY 2 DESC"""
    )
    categories = [{"categorie": r[0], "count": r[1], "budget_fcfa": r[2]} for r in c.fetchall()]
    c.execute(
        """SELECT COALESCE(secteur_activite, 'Services Généraux & Divers'), COUNT(*), SUM(COALESCE(budget_previsionnel_fcfa, 0))
           FROM annonces_avis GROUP BY 1 ORDER BY 2 DESC"""
    )
    sectors = [{"sector": r[0], "count": r[1], "budget_fcfa": r[2]} for r in c.fetchall()]
    c.execute("SELECT COALESCE(type_procedure, 'Autre'), COUNT(*) FROM annonces_avis GROUP BY 1 ORDER BY 2 DESC")
    types_proc = [{"type": r[0], "count": r[1]} for r in c.fetchall()]
    conn.close()
    return {
        "total_annonces": tot_annonces,
        "total_budget_fcfa": tot_budget,
        "budget_formate": f"{round(tot_budget / 1e9, 2)} Md FCFA".replace(".", ","),
        "total_lots": tot_lots,
        "total_bulletins": tot_bulletins,
        "categories": categories,
        "sectors": sectors,
        "types_procedures": types_proc,
    }


@router.get("/markets")
def list_markets(
    request: Request,
    q: Optional[str] = Query(None),
    categorie: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    type_proc: Optional[str] = Query(None),
    min_budget: Optional[int] = Query(None),
    max_budget: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = get_current_user_optional(request)
    # Une recherche filtrée (présence de q) décompte le quota Gratuit
    if user and q:
        consume_quota(user, "recherches_par_jour", "compteur_recherches")

    conn = get_db()
    c = conn.cursor()
    conditions, params = [], []
    if q:
        like_q = f"%{q}%"
        conditions.append("(objet_marche LIKE ? OR autorite_contractante LIKE ? OR reference_dossier LIKE ? OR ministere_tutelle LIKE ?)")
        params.extend([like_q, like_q, like_q, like_q])
    if categorie:
        conditions.append("categorie_marche LIKE ?"); params.append(f"%{categorie}%")
    if sector:
        conditions.append("secteur_activite LIKE ?"); params.append(f"%{sector}%")
    if type_proc:
        conditions.append("type_procedure LIKE ?"); params.append(f"%{type_proc}%")
    if min_budget is not None:
        conditions.append("budget_previsionnel_fcfa >= ?"); params.append(min_budget)
    if max_budget is not None:
        conditions.append("budget_previsionnel_fcfa <= ?"); params.append(max_budget)
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    c.execute(f"SELECT COUNT(*) FROM annonces_avis {where_clause}", params)
    total = c.fetchone()[0]
    query = f"""
        SELECT id, numero_bulletin, date_parution, pages, categorie_marche, type_procedure,
               reference_dossier, autorite_contractante, ministere_tutelle, objet_marche,
               allotissement_type, nombre_lots, budget_previsionnel_fcfa, date_limite_depot,
               heure_limite_depot, source_financement, remarque, secteur_activite
        FROM annonces_avis {where_clause} ORDER BY rowid ASC LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": total, "limit": limit, "offset": offset, "results": rows}


@router.get("/markets/{market_id}")
def get_market(market_id: str, request: Request):
    user = get_current_user_optional(request)
    if user:
        consume_quota(user, "fiches_par_jour", "compteur_fiches")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT * FROM annonces_avis WHERE id = ?", (market_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Marché non trouvé")
    market_data = dict(row)
    c.execute("SELECT numero_lot, titre, description, montant_fcfa, caution_fcfa FROM detail_lots WHERE annonce_id = ?", (market_id,))
    market_data["lots"] = [dict(r) for r in c.fetchall()]
    conn.close()
    return market_data


@router.get("/authorities")
def list_authorities(
    q: Optional[str] = Query(None),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    conn = get_db()
    c = conn.cursor()
    conditions = ["autorite_contractante IS NOT NULL", "autorite_contractante != ''"]
    params = []
    if q:
        conditions.append("(autorite_contractante LIKE ? OR ministere_tutelle LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    where_sql = "WHERE " + " AND ".join(conditions)
    c.execute(f"""
        SELECT autorite_contractante as name, MAX(ministere_tutelle) as ministry,
               MAX(lieu_depot_offres) as lieu_depot, COUNT(*) as count,
               SUM(COALESCE(budget_previsionnel_fcfa, 0)) as total_amount,
               SUM(COALESCE(nombre_lots, 1)) as total_lots
        FROM annonces_avis {where_sql}
        GROUP BY autorite_contractante ORDER BY count DESC, total_amount DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": len(rows), "results": rows}


# --------------------------------------------------------------------------- #
# Fonctionnalités premium (verrouillées par offre)
# --------------------------------------------------------------------------- #
@router.get("/export/csv")
def export_csv_file(user: dict = Depends(require_feature("export"))):
    """Export complet CSV — réservé aux offres Pro et Entreprise."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM annonces_avis ORDER BY rowid ASC")
    rows = c.fetchall()
    headers = [col[0] for col in c.description]
    csv_lines = [";".join(headers)]
    for r in rows:
        line = []
        for val in r:
            line.append("" if val is None else str(val).replace(";", ",").replace("\n", " ").replace("\r", ""))
        csv_lines.append(";".join(line))
    conn.close()
    content = "﻿" + "\n".join(csv_lines)
    return Response(
        content=content, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marches_publics_burkina_complet.csv"},
    )


@router.get("/resultats")
def list_resultats(
    user: dict = Depends(require_feature("resultats")),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=300),
    offset: int = Query(0, ge=0),
):
    """Résultats / attributions détaillés — offre Pro+."""
    conn = get_db()
    c = conn.cursor()
    conditions, params = [], []
    if q:
        conditions.append("(objet LIKE ? OR autorite_contractante LIKE ? OR reference_dossier LIKE ?)")
        like = f"%{q}%"; params.extend([like, like, like])
    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    total = c.execute(f"SELECT COUNT(*) FROM resultats_marches {where_sql}", params).fetchone()[0]
    c.execute(f"""
        SELECT id, bulletin, date_parution, autorite_contractante, reference_dossier,
               objet, secteur_activite, methode_selection, date_deliberation, nombre_lots
        FROM resultats_marches {where_sql} ORDER BY rowid DESC LIMIT ? OFFSET ?
    """, params + [limit, offset])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": total, "limit": limit, "offset": offset, "results": rows}


@router.get("/entreprises")
def list_entreprises(
    user: dict = Depends(require_feature("entreprises")),
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Répertoire des entreprises soumissionnaires (CRM) — offre Pro+."""
    conn = get_db()
    c = conn.cursor()
    conditions = ["nom_canonique IS NOT NULL", "nom_canonique != ''"]
    params = []
    if q:
        conditions.append("(nom_canonique LIKE ? OR ifu LIKE ? OR rccm LIKE ?)")
        like = f"%{q}%"; params.extend([like, like, like])
    where_sql = "WHERE " + " AND ".join(conditions)
    c.execute(f"""
        SELECT nom_canonique AS nom,
               MAX(ifu) AS ifu, MAX(rccm) AS rccm, MAX(telephone) AS telephone, MAX(email) AS email,
               COUNT(*) AS soumissions,
               SUM(CASE WHEN est_attributaire = 1 THEN 1 ELSE 0 END) AS marches_gagnes
        FROM resultats_soumissionnaires {where_sql}
        GROUP BY nom_canonique ORDER BY soumissions DESC LIMIT ?
    """, params + [limit])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": len(rows), "results": rows}
