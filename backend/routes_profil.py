#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_profil.py
========================
Profil de candidature, scoring « Mes chances », fil personnalisé et
tableau de bord personnel de l'utilisateur.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import get_current_user_optional, require_user
from backend.scoring import score_marche

router = APIRouter(prefix="/api", tags=["profil"])


# --------------------------------------------------------------------------- #
# Profil de candidature
# --------------------------------------------------------------------------- #
class ProfilIn(BaseModel):
    secteurs: Optional[List[str]] = None
    region: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    agrements: Optional[str] = None
    anciennete_annees: Optional[int] = None
    en_groupement: Optional[bool] = None
    marches_soumis: Optional[int] = None
    marches_gagnes: Optional[int] = None


def _ensure_user_details(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_details (
            user_id INTEGER PRIMARY KEY,
            nom_entreprise TEXT,
            secteur_principal TEXT,
            secteurs_secondaires TEXT,
            annee_creation INTEGER,
            ville TEXT,
            pays TEXT DEFAULT 'Burkina Faso',
            ifu TEXT,
            rccm TEXT,
            forme_juridique TEXT,
            fonction_poste TEXT,
            maj_le TEXT
        )
    """)
    conn.commit()


def _load_profil(conn, user_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM profils_candidature WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["secteurs"] = json.loads(d.get("secteurs") or "[]")
    except Exception:
        d["secteurs"] = []
    d["en_groupement"] = bool(d.get("en_groupement"))
    return d


class IdentiteIn(BaseModel):
    nom_entreprise: Optional[str] = None
    secteur_principal: Optional[str] = None
    secteurs_secondaires: Optional[str] = None
    annee_creation: Optional[int] = None
    ville: Optional[str] = None
    pays: Optional[str] = "Burkina Faso"
    ifu: Optional[str] = None
    rccm: Optional[str] = None
    forme_juridique: Optional[str] = None
    nom_complet: Optional[str] = None
    organisation: Optional[str] = None
    fonction_poste: Optional[str] = None
    telephone: Optional[str] = None


@router.get("/entreprises/search")
def search_entreprises_autocomplete(q: str = ""):
    q = (q or "").strip()
    if len(q) < 2:
        return {"results": []}
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT nom_canonique, ifu, rccm, telephone, email, ville, secteurs_json, nb_soumissions, nb_gagnes
               FROM entreprises
               WHERE nom_canonique LIKE ? OR ifu LIKE ? OR rccm LIKE ?
               ORDER BY nb_gagnes DESC, nb_soumissions DESC
               LIMIT 12""",
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                secs = json.loads(d.get("secteurs_json") or "[]")
            except Exception:
                secs = []
            nom_up = (d.get("nom_canonique") or "").upper()
            forme = "SARL" if "SARL" in nom_up else ("SUARL" if "SUARL" in nom_up else ("SAS" if " SAS" in nom_up else ("SA" if " SA" in nom_up or nom_up.endswith(" SA") else ("GIE" if "GIE" in nom_up else ""))))
            out.append({
                "nom": d.get("nom_canonique"),
                "ifu": d.get("ifu") or "",
                "rccm": d.get("rccm") or "",
                "telephone": d.get("telephone") or "",
                "ville": d.get("ville") or "",
                "secteurs": secs,
                "forme_juridique": forme,
                "nb_soumissions": d.get("nb_soumissions") or 0,
                "nb_gagnes": d.get("nb_gagnes") or 0,
            })
        return {"results": out}
    finally:
        conn.close()


@router.get("/profil")
def get_profil(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        _ensure_user_details(conn)
        p = _load_profil(conn, user["id"])
        u_row = conn.execute(
            "SELECT id, email, nom, organisation, telephone, plan_id, role, cree_le FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
        det_row = conn.execute("SELECT * FROM user_details WHERE user_id = ?", (user["id"],)).fetchone()
        return {
            "profil": p,
            "complet": bool(p and p.get("secteurs")),
            "user": dict(u_row) if u_row else user,
            "details": dict(det_row) if det_row else {},
        }
    finally:
        conn.close()


@router.put("/profil/identite")
def put_identite(body: IdentiteIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        _ensure_user_details(conn)
        if body.nom_complet is not None or body.organisation is not None or body.telephone is not None:
            conn.execute(
                """UPDATE users
                   SET nom = COALESCE(?, nom),
                       organisation = COALESCE(?, organisation),
                       telephone = COALESCE(?, telephone)
                   WHERE id = ?""",
                (
                    body.nom_complet.strip() if body.nom_complet else None,
                    body.organisation.strip() if body.organisation is not None else None,
                    body.telephone.strip() if body.telephone is not None else None,
                    user["id"],
                ),
            )
        conn.execute(
            """INSERT INTO user_details
                 (user_id, nom_entreprise, secteur_principal, secteurs_secondaires, annee_creation,
                  ville, pays, ifu, rccm, forme_juridique, fonction_poste, maj_le)
               VALUES (?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                 nom_entreprise=excluded.nom_entreprise,
                 secteur_principal=excluded.secteur_principal,
                 secteurs_secondaires=excluded.secteurs_secondaires,
                 annee_creation=excluded.annee_creation,
                 ville=excluded.ville,
                 pays=excluded.pays,
                 ifu=excluded.ifu,
                 rccm=excluded.rccm,
                 forme_juridique=excluded.forme_juridique,
                 fonction_poste=excluded.fonction_poste,
                 maj_le=CURRENT_TIMESTAMP""",
            (
                user["id"],
                body.nom_entreprise,
                body.secteur_principal,
                body.secteurs_secondaires,
                body.annee_creation,
                body.ville,
                body.pays or "Burkina Faso",
                body.ifu,
                body.rccm,
                body.forme_juridique,
                body.fonction_poste,
            ),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.put("/profil")
def put_profil(body: ProfilIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        secteurs_json = json.dumps(body.secteurs or [], ensure_ascii=False)
        conn.execute(
            """INSERT INTO profils_candidature
                 (user_id, secteurs, region, budget_min, budget_max, agrements,
                  anciennete_annees, en_groupement, marches_soumis, marches_gagnes, maj_le)
               VALUES (?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                 secteurs=excluded.secteurs, region=excluded.region,
                 budget_min=excluded.budget_min, budget_max=excluded.budget_max,
                 agrements=excluded.agrements, anciennete_annees=excluded.anciennete_annees,
                 en_groupement=excluded.en_groupement, marches_soumis=excluded.marches_soumis,
                 marches_gagnes=excluded.marches_gagnes, maj_le=CURRENT_TIMESTAMP""",
            (user["id"], secteurs_json, body.region, body.budget_min, body.budget_max,
             body.agrements, body.anciennete_annees, int(bool(body.en_groupement)),
             body.marches_soumis or 0, body.marches_gagnes or 0),
        )
        conn.commit()
        return {"ok": True, "profil": _load_profil(conn, user["id"])}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Scoring « Mes chances »
# --------------------------------------------------------------------------- #
@router.get("/scoring/{avis_id}")
def get_scoring(avis_id: str, request: Request):
    user = get_current_user_optional(request)
    conn = get_db()
    try:
        avis = conn.execute("SELECT * FROM annonces_avis WHERE id = ?", (avis_id,)).fetchone()
        if not avis:
            raise HTTPException(status_code=404, detail="Marché introuvable.")
        profil = _load_profil(conn, user["id"]) if user else None
        return score_marche(conn, dict(avis), profil)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Fil personnalisé « fait pour moi »
# --------------------------------------------------------------------------- #
def _days_left(date_limite: Optional[str]) -> Optional[int]:
    if not date_limite:
        return None
    try:
        import re
        s = date_limite.strip()
        m = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', s)
        if m:
            d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
            return (d - datetime.now().date()).days
        m_iso = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
        if m_iso:
            d = datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))).date()
            return (d - datetime.now().date()).days
    except Exception:
        pass
    return None


@router.get("/moi/fil")
def fil_personnalise(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        profil = _load_profil(conn, user["id"])
        if not profil or not profil.get("secteurs"):
            return {"profil_requis": True, "results": []}
        secteurs = profil["secteurs"]
        placeholders = ",".join("?" * len(secteurs))
        params = list(secteurs)
        budget_sql = ""
        if profil.get("budget_min"):
            budget_sql += " AND budget_previsionnel_fcfa >= ?"; params.append(profil["budget_min"])
        if profil.get("budget_max"):
            budget_sql += " AND budget_previsionnel_fcfa <= ?"; params.append(profil["budget_max"])
        rows = conn.execute(
            f"""SELECT id, objet_marche AS objet, autorite_contractante AS autorite,
                       secteur_activite AS secteur, type_procedure AS type,
                       date_limite_depot AS date_limite, budget_previsionnel_fcfa AS budget
                FROM annonces_avis
                WHERE secteur_activite IN ({placeholders}) {budget_sql}
                ORDER BY rowid DESC LIMIT 400""",
            params,
        ).fetchall()
        # Garder les marchés dont la date limite est future (ou inconnue), trier par urgence
        out = []
        for r in rows:
            d = dict(r)
            dl = _days_left(d["date_limite"])
            d["jours_restants"] = dl
            if dl is None or dl >= 0:
                out.append(d)
        out.sort(key=lambda x: (x["jours_restants"] is None, x["jours_restants"] if x["jours_restants"] is not None else 9999))
        return {"profil_requis": False, "total": len(out), "results": out[:40]}
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Tableau de bord personnel
# --------------------------------------------------------------------------- #
@router.get("/moi/stats")
def mes_stats(user: dict = Depends(require_user)):
    conn = get_db()
    uid = user["id"]
    try:
        suivis = conn.execute("SELECT COUNT(*) FROM suivis WHERE user_id=?", (uid,)).fetchone()[0]
        radar = conn.execute("SELECT COUNT(*) FROM radar_concurrents WHERE user_id=?", (uid,)).fetchone()[0]
        non_lus = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND lu=0", (uid,)).fetchone()[0]
        dstats = {r["statut"]: r["n"] for r in conn.execute(
            "SELECT statut, COUNT(*) AS n FROM dossiers WHERE user_id=? GROUP BY statut", (uid,)
        ).fetchall()}
        deposes = (dstats.get("depose", 0) + dstats.get("gagne", 0) + dstats.get("perdu", 0))
        gagnes = dstats.get("gagne", 0)
        taux = round(100.0 * gagnes / deposes) if deposes else None
        return {
            "suivis": suivis,
            "radar": radar,
            "notifications_non_lues": non_lus,
            "dossiers": dstats,
            "soumissions": deposes,
            "gagnes": gagnes,
            "taux_reussite": taux,
        }
    finally:
        conn.close()
