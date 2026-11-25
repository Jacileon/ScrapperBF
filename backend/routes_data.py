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


_LIVE_RESULTATS_CACHE = {"ts": 0.0, "json_bytes": None, "building": False}
_CACHE_TTL_SECONDS = 180.0


def _refresh_live_cache_bg():
    import json
    import time
    from backend.config import DB_PATH
    from export_resultats_to_front import build_front_payload
    try:
        payload = build_front_payload(DB_PATH)
        _LIVE_RESULTATS_CACHE["json_bytes"] = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        _LIVE_RESULTATS_CACHE["ts"] = time.time()
    except Exception:
        pass
    finally:
        _LIVE_RESULTATS_CACHE["building"] = False


def _ensure_live_cache_bg():
    import threading
    if not _LIVE_RESULTATS_CACHE["building"]:
        _LIVE_RESULTATS_CACHE["building"] = True
        threading.Thread(target=_refresh_live_cache_bg, daemon=True).start()


@router.get("/data/resultats-live")
def get_resultats_live():
    """Données complètes des résultats et entreprises (bytes JSON pré-sérialisés, réponse < 50ms)."""
    import time
    from pathlib import Path

    now = time.time()
    jb = _LIVE_RESULTATS_CACHE["json_bytes"]
    if jb is None:
        js_path = Path("web/app/assets/data_resultats.js")
        if js_path.exists():
            try:
                raw = js_path.read_text(encoding="utf-8")
                prefix = "window.DATA_RESULTATS = "
                idx = raw.find(prefix)
                if idx != -1:
                    jb = raw[idx + len(prefix):].strip().rstrip(";").encode("utf-8")
                    _LIVE_RESULTATS_CACHE["json_bytes"] = jb
                    _LIVE_RESULTATS_CACHE["ts"] = now
            except Exception:
                jb = None
        if jb is None:
            jb = b'{"resultats":[],"entreprises":[],"stats":{},"ready":false}'
        _ensure_live_cache_bg()
        return Response(content=jb, media_type="application/json")

    if (now - _LIVE_RESULTATS_CACHE["ts"]) >= _CACHE_TTL_SECONDS:
        _ensure_live_cache_bg()

    return Response(content=jb, media_type="application/json")


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
    conditions = [
        "nom_canonique IS NOT NULL",
        "LENGTH(TRIM(nom_canonique)) > 2",
        "UPPER(TRIM(nom_canonique)) NOT IN ('NON','OUI','OFFRE','AUCUN','NEANT','NÉANT','INCONNU','SOUMISSIONNAIRE INCONNU','RETENU','NON RETENU','CONFORME','NON CONFORME','ATTRIBUTAIRE','RAS','N/A','NA','BF','RE (S)','SOUMISSIONNAIRE','ENTREPRISE')",
    ]
    params = []
    if q:
        conditions.append("(nom_canonique LIKE ? OR ifu LIKE ? OR rccm LIKE ? OR telephone LIKE ?)")
        like = f"%{q}%"; params.extend([like, like, like, like])
    where_sql = "WHERE " + " AND ".join(conditions)
    c.execute(f"""
        SELECT nom_canonique AS nom,
               MAX(ifu) AS ifu, MAX(rccm) AS rccm, MAX(telephone) AS telephone,
               MAX(email) AS email, MAX(adresse_bp) AS adresse,
               COUNT(*) AS soumissions,
               SUM(CASE WHEN est_attributaire = 1 THEN 1 ELSE 0 END) AS marches_gagnes,
               ROUND(100.0 * SUM(CASE WHEN est_attributaire = 1 THEN 1 ELSE 0 END) / COUNT(*)) AS taux_reussite,
               COALESCE(SUM(CASE WHEN est_attributaire = 1 THEN COALESCE(montant_corrige_ttc_max, montant_corrige_ttc_min, montant_lu_ttc_max, montant_lu_ttc_min, 0) ELSE 0 END), 0) AS montant_gagne
        FROM resultats_soumissionnaires {where_sql}
        GROUP BY nom_canonique ORDER BY marches_gagnes DESC, soumissions DESC LIMIT ?
    """, params + [limit])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": len(rows), "results": rows}


@router.get("/data/entreprise")
def get_entreprise_detail(nom: str = Query(..., min_length=1)):
    """Fiche détaillée dynamique d'une entreprise depuis SQLite (coordonnées, marchés gagnés, toutes soumissions & remarques)."""
    from export_resultats_to_front import clean_contact_field, detect_ville

    conn = get_db()
    c = conn.cursor()
    target = nom.strip()
    c.execute("""
        SELECT s.*, m.objet, m.autorite_contractante AS autorite, m.date_parution AS date,
               m.reference_dossier AS reference, m.secteur_activite AS secteur,
               m.annonce_avis_id AS avis_id, m.bulletin,
               l.numero_lot AS lot, l.intitule_lot AS intitule, l.est_infructueux AS infructueux,
               l.montant_attribue_min_fcfa, l.montant_attribue_max_fcfa,
               l.remarques_autorite, l.contacts_entreprises
        FROM resultats_soumissionnaires s
        LEFT JOIN resultats_marches m ON m.id = s.resultat_id
        LEFT JOIN resultats_lots l ON l.id = s.lot_id
        WHERE UPPER(TRIM(COALESCE(s.nom_canonique, s.nom_soumissionnaire))) = UPPER(?)
        ORDER BY m.date_parution DESC, s.id DESC
    """, (target,))
    sub_rows = [dict(r) for r in c.fetchall()]
    conn.close()

    if not sub_rows:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    profile = {
        "nom": sub_rows[0].get("nom_canonique") or target,
        "soumissions": len(sub_rows),
        "gagnes": 0,
        "conformes": 0,
        "montant_gagne": 0,
        "secteurs": set(),
        "ifu": None,
        "rccm": None,
        "tel": None,
        "email": None,
        "adresse": None,
        "ville": None,
        "groupement": False,
    }
    wins = []
    soumissions_list = []
    seen_wins = set()

    for r in sub_rows:
        conf = (r.get("conformite") or "").lower()
        if "conform" in conf and "non conform" not in conf:
            profile["conformes"] += 1
        if r.get("secteur"):
            profile["secteurs"].add(r["secteur"])
        if r.get("est_groupement"):
            profile["groupement"] = True

        c_tel, c_bp = clean_contact_field(r.get("telephone"), r.get("adresse_bp"))
        if not profile["ifu"] and r.get("ifu"):
            profile["ifu"] = str(r["ifu"]).strip()
        if not profile["rccm"] and r.get("rccm"):
            profile["rccm"] = str(r["rccm"]).strip()
        if not profile["tel"] and c_tel:
            profile["tel"] = c_tel
        if not profile["email"] and r.get("email"):
            profile["email"] = str(r["email"]).strip()
        if not profile["adresse"] and c_bp:
            profile["adresse"] = c_bp
        if not profile["ville"]:
            profile["ville"] = detect_ville(c_bp) or detect_ville(r.get("observations_motifs"))

        mt_offre = (
            r.get("montant_corrige_ttc_max") or r.get("montant_corrige_ttc_min")
            or r.get("montant_lu_ttc_max") or r.get("montant_lu_ttc_min")
            or r.get("montant_corrige_htva_max") or r.get("montant_corrige_htva_min")
            or r.get("montant_lu_htva_max") or r.get("montant_lu_htva_min")
        )
        mt_lot = r.get("montant_attribue_max_fcfa") or r.get("montant_attribue_min_fcfa") or mt_offre
        if r.get("est_attributaire"):
            profile["gagnes"] += 1
            if mt_offre:
                profile["montant_gagne"] += mt_offre
            wkey = (r.get("resultat_id"), r.get("lot"))
            if wkey not in seen_wins:
                seen_wins.add(wkey)
                wins.append({
                    "resultat_id": r.get("resultat_id"),
                    "avis_id": r.get("avis_id"),
                    "objet": r.get("objet"),
                    "autorite": r.get("autorite"),
                    "date": r.get("date"),
                    "reference": r.get("reference"),
                    "lot": r.get("lot"),
                    "intitule": r.get("intitule"),
                    "montant": mt_lot,
                    "remarques_autorite": r.get("remarques_autorite"),
                })

        soumissions_list.append({
            "resultat_id": r.get("resultat_id"),
            "avis_id": r.get("avis_id"),
            "objet": r.get("objet"),
            "autorite": r.get("autorite"),
            "date": r.get("date"),
            "lot": r.get("lot"),
            "est_attributaire": bool(r.get("est_attributaire")),
            "conformite": r.get("conformite"),
            "montant_offre": mt_offre,
            "observations": r.get("observations_motifs") or r.get("remarques_autorite"),
        })

    profile["secteurs"] = sorted(profile["secteurs"])
    profile["taux_reussite"] = round(100 * profile["gagnes"] / profile["soumissions"]) if profile["soumissions"] else 0
    return {"entreprise": profile, "wins": wins, "soumissions": soumissions_list}


_LIVE_RESULTATS_CACHE = {"ts": 0.0, "json_bytes": None, "building": False}
_CACHE_TTL_SECONDS = 180.0


def _refresh_live_cache_bg():
    import json
    import time
    from backend.config import DB_PATH
    from export_resultats_to_front import build_front_payload
    try:
        payload = build_front_payload(DB_PATH)
        _LIVE_RESULTATS_CACHE["json_bytes"] = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        _LIVE_RESULTATS_CACHE["ts"] = time.time()
    except Exception:
        pass
    finally:
        _LIVE_RESULTATS_CACHE["building"] = False


def _ensure_live_cache_bg():
    import threading
    if not _LIVE_RESULTATS_CACHE["building"]:
        _LIVE_RESULTATS_CACHE["building"] = True
        threading.Thread(target=_refresh_live_cache_bg, daemon=True).start()


@router.get("/data/resultats-live")
def get_resultats_live():
    """Données complètes des résultats et entreprises (bytes JSON pré-sérialisés, réponse < 50ms)."""
    import time
    from pathlib import Path

    now = time.time()
    jb = _LIVE_RESULTATS_CACHE["json_bytes"]
    if jb is None:
        js_path = Path("web/app/assets/data_resultats.js")
        if js_path.exists():
            try:
                raw = js_path.read_text(encoding="utf-8")
                prefix = "window.DATA_RESULTATS = "
                idx = raw.find(prefix)
                if idx != -1:
                    jb = raw[idx + len(prefix):].strip().rstrip(";").encode("utf-8")
                    _LIVE_RESULTATS_CACHE["json_bytes"] = jb
                    _LIVE_RESULTATS_CACHE["ts"] = now
            except Exception:
                jb = None
        if jb is None:
            jb = b'{"resultats":[],"entreprises":[],"stats":{},"ready":false}'
        _ensure_live_cache_bg()
        return Response(content=jb, media_type="application/json")

    if (now - _LIVE_RESULTATS_CACHE["ts"]) >= _CACHE_TTL_SECONDS:
        _ensure_live_cache_bg()

    return Response(content=jb, media_type="application/json")
