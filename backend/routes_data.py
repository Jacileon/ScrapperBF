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
        conditions.append("(objet_marche LIKE ? OR autorite_contractante LIKE ? OR reference_dossier LIKE ? OR ministere_tutelle LIKE ? OR numero_bulletin LIKE ?)")
        params.extend([like_q, like_q, like_q, like_q, like_q])
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


@router.get("/markets/{market_id}/similar-open")
def get_similar_open_markets(market_id: str, limit: int = Query(6, ge=1, le=20)):
    """
    Retourne les marchés similaires encore ouverts (date de clôture non échue).
    Scoring basé sur la correspondance de secteur, de catégorie, d'autorité et de mots-clés du titre.
    """
    import re
    from datetime import date
    
    conn = get_db()
    c = conn.cursor()
    target_row = c.execute("SELECT * FROM annonces_avis WHERE id = ?", (market_id,)).fetchone()
    if not target_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Marché non trouvé")
    
    target = dict(target_row)
    t_obj = (target.get("objet_marche") or "").lower()
    t_sec = target.get("secteur_activite")
    t_cat = target.get("categorie_marche")
    t_auth = target.get("autorite_contractante")

    stopwords = {'de', 'des', 'du', 'la', 'le', 'les', 'au', 'aux', 'et', 'en', 'un', 'une', 'pour', 'par', 'dans', 'sur', 'avec', 'sans', 'sous', 'vers', 'chez', 'd', 'l', 'a', 'profit', 'fourniture', 'acquisition', 'travaux', 'projet', 'marche', 'realisation', 'construction', 'services', 'recrutement', 'avis', 'appel', 'offres', 'dossier', 'burkina', 'faso'}
    tokens = re.findall(r'[a-zA-Zàâäéèêëîïôöùûüç]{4,}', t_obj)
    target_kws = [w for w in tokens if w not in stopwords]

    today_iso = date.today().isoformat()

    c.execute("SELECT * FROM annonces_avis WHERE id != ?", (market_id,))
    all_notices = [dict(r) for r in c.fetchall()]
    conn.close()

    candidates = []
    for m in all_notices:
        dl_raw = m.get("date_limite_depot")
        if not dl_raw:
            continue
        m_iso = None
        if "/" in str(dl_raw):
            pts = str(dl_raw).strip().split("/")
            if len(pts) == 3:
                m_iso = f"{pts[2]}-{pts[1].zfill(2)}-{pts[0].zfill(2)}"
        elif "-" in str(dl_raw):
            m_iso = str(dl_raw).strip()[:10]
        
        # Filtrer : la clôture ne doit pas être passée
        if m_iso and m_iso < today_iso:
            continue

        score = 0
        reasons = []
        if t_sec and m.get("secteur_activite") == t_sec:
            score += 40
            reasons.append(f"Même secteur ({t_sec})")
        if t_cat and m.get("categorie_marche") == t_cat:
            score += 15
        if t_auth and m.get("autorite_contractante") == t_auth:
            score += 15
            reasons.append("Même acheteur")
        
        m_obj = (m.get("objet_marche") or "").lower()
        m_tokens = re.findall(r'[a-zA-Zàâäéèêëîïôöùûüç]{4,}', m_obj)
        m_kws = set(w for w in m_tokens if w not in stopwords)
        shared = [w for w in target_kws if w in m_kws]
        if shared:
            score += len(shared) * 25
            reasons.append(f"Mots-clés : {', '.join(shared[:3])}")
        
        if score >= 35:
            candidates.append({
                "market": m,
                "similarity_score": min(score, 100),
                "reasons": reasons,
                "deadline_iso": m_iso
            })
    
    candidates.sort(key=lambda x: (-x["similarity_score"], x["deadline_iso"] or "9999"))
    return {"total": len(candidates), "target_id": market_id, "results": candidates[:limit]}


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
        conditions.append("(nom_canonique LIKE ? OR ifu LIKE ? OR rccm LIKE ? OR telephone LIKE ? OR email LIKE ?)")
        like = f"%{q}%"; params.extend([like, like, like, like, like])
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
    import unicodedata
    from export_resultats_to_front import clean_contact_field, detect_ville

    conn = get_db()
    c = conn.cursor()
    target = nom.strip()

    # Recherche rapide et indexée des alias (sans scan de table complet)
    unacc = "".join(c for c in unicodedata.normalize("NFD", target) if unicodedata.category(c) != "Mn").upper()
    cands = list(dict.fromkeys([target, target.upper(), target.lower(), target.title(), unacc]))
    ph = ",".join("?" * len(cands))

    c.execute(f"""
        SELECT DISTINCT nom_canonique 
        FROM resultats_soumissionnaires 
        WHERE nom_canonique IN ({ph}) 
           OR nom_soumissionnaire IN ({ph})
        ORDER BY CASE WHEN nom_canonique = ? THEN 0 ELSE 1 END
        LIMIT 1
    """, cands + cands + [target])
    canon_res = c.fetchone()

    # Si non trouvé exactement (ex: casse mixte 'La Générale de la Gastronomie (GEGA)'), recherche par sigle ou début de chaîne
    if not canon_res:
        import re
        sigle_m = re.search(r"\(([^)]+)\)", target)
        if sigle_m:
            sigle = sigle_m.group(1).strip()
            c.execute("SELECT DISTINCT nom_canonique FROM resultats_soumissionnaires WHERE nom_canonique LIKE ? OR nom_soumissionnaire LIKE ? LIMIT 1", (f"%({sigle})%", f"%({sigle})%"))
            canon_res = c.fetchone()
        if not canon_res and len(unacc) >= 6:
            c.execute("SELECT DISTINCT nom_canonique FROM resultats_soumissionnaires WHERE nom_canonique LIKE ? LIMIT 1", (f"{target[:12]}%",))
            canon_res = c.fetchone()
    canonical_target = canon_res[0] if (canon_res and canon_res[0]) else target

    c_list = list(dict.fromkeys([canonical_target, canonical_target.upper(), target, target.upper()]))
    ph2 = ",".join("?" * len(c_list))

    c.execute(f"""
        SELECT s.*, m.objet, m.autorite_contractante AS autorite, m.date_parution AS date,
               m.reference_dossier AS reference, m.secteur_activite AS secteur,
               m.annonce_avis_id AS avis_id, m.bulletin,
               l.numero_lot AS lot, l.intitule_lot AS intitule, l.est_infructueux AS infructueux,
               l.montant_attribue_min_fcfa, l.montant_attribue_max_fcfa,
               l.remarques_autorite, l.contacts_entreprises
        FROM resultats_soumissionnaires s
        LEFT JOIN resultats_marches m ON m.id = s.resultat_id
        LEFT JOIN resultats_lots l ON l.id = s.lot_id
        WHERE s.nom_canonique IN ({ph2})
        ORDER BY m.date_parution DESC, s.id DESC
    """, c_list)
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


@router.get("/data/resultat")
def get_resultat_detail(id: str = Query(..., min_length=1), lot: Optional[str] = Query(None)):
    """Détail complet d'un résultat d'attribution : marché, lots, délibérations et soumissionnaires."""
    conn = get_db()
    c = conn.cursor()
    raw_id = id.strip()
    marche_id = raw_id.split("#")[0].strip()
    lot_filter = lot or (raw_id.split("#")[1].strip() if "#" in raw_id else None)

    c.execute("SELECT * FROM resultats_marches WHERE id = ?", (marche_id,))
    row_m = c.fetchone()
    if not row_m:
        c.execute("SELECT * FROM resultats_marches WHERE annonce_avis_id = ? OR id LIKE ? LIMIT 1", (marche_id, f"%{marche_id}%"))
        row_m = c.fetchone()

    if not row_m:
        conn.close()
        raise HTTPException(status_code=404, detail="Résultat introuvable")

    marche = dict(row_m)

    # Récupérer l'avis d'origine s'il est lié (permet l'affichage split-view instantané)
    avis_origine = None
    if marche.get("annonce_avis_id"):
        c.execute("""
            SELECT id, numero_bulletin, date_parution, pages, categorie_marche, type_procedure,
                   reference_dossier, autorite_contractante, ministere_tutelle, objet_marche,
                   allotissement_type, nombre_lots, budget_previsionnel_fcfa,
                   garantie_soumission_fcfa, cout_acquisition_dossier_fcfa,
                   source_financement, exercice_budgetaire, date_limite_depot,
                   heure_limite_depot, delai_execution_jours, lieu_depot_offres,
                   date_heure_ouverture_plis, qualifications_ou_agrement, contacts_renseignements
            FROM annonces_avis WHERE id = ?
        """, (marche["annonce_avis_id"],))
        row_a = c.fetchone()
        if row_a:
            avis_origine = dict(row_a)
            c.execute("SELECT numero_lot, titre, montant_fcfa, caution_fcfa FROM detail_lots WHERE annonce_id = ? ORDER BY id ASC", (marche["annonce_avis_id"],))
            avis_origine["lots"] = [dict(al) for al in c.fetchall()]

    # Récupérer les lots
    c.execute("SELECT * FROM resultats_lots WHERE resultat_id = ? ORDER BY numero_lot ASC", (marche["id"],))
    lots = [dict(l) for l in c.fetchall()]

    # Normaliser les seuils (calcul auto tolérance 5% si borne_inf présente mais tolérance absente)
    for l in lots:
        binf = l.get("borne_inf_basse_fcfa")
        tol = l.get("seuil_tolerance_5pct_fcfa")
        if binf and not tol:
            l["seuil_tolerance_5pct_fcfa"] = round(binf * 0.95)
            l["seuil_tolerance_calcule"] = True

    # Récupérer tous les soumissionnaires triés strictement par lot puis rang croissant (1er, 2e, 3e...)
    c.execute("""
        SELECT s.*, l.numero_lot 
        FROM resultats_soumissionnaires s
        LEFT JOIN resultats_lots l ON l.id = s.lot_id
        WHERE s.resultat_id = ?
        ORDER BY l.numero_lot ASC,
                 CASE WHEN s.rang_numerique IS NOT NULL AND s.rang_numerique > 0 THEN 0 ELSE 1 END,
                 s.rang_numerique ASC,
                 s.est_attributaire DESC,
                 s.id ASC
    """, (marche["id"],))
    soums = [dict(s) for s in c.fetchall()]
    conn.close()

    # Organiser les soumissionnaires par lot
    soums_by_lot = {}
    for s in soums:
        num_lot = str(s.get("numero_lot") or s.get("lot_id") or "1")
        soums_by_lot.setdefault(num_lot, []).append(s)

    for l in lots:
        num_lot = str(l.get("numero_lot") or "1")
        l["soumissionnaires"] = soums_by_lot.get(num_lot, [])

    return {
        "marche": marche,
        "lots": lots,
        "avis": avis_origine,
        "selected_lot": lot_filter,
    }


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
