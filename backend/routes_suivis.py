#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_suivis.py
========================
Favoris : suivre un marché, lister ses marchés suivis, changer leur statut,
les retirer. Socle de l'alerte résultat « boucle fermée » (backend/alertes_resultats.py).
Toutes les routes exigent un utilisateur connecté.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api/suivis", tags=["suivis"])

_STATUTS = {"suivi", "je_soumissionne", "abandonne"}


class SuiviIn(BaseModel):
    avis_id: str
    statut: Optional[str] = None
    note: Optional[str] = None


class SuiviPatch(BaseModel):
    statut: Optional[str] = None
    note: Optional[str] = None


@router.get("")
def list_suivis(user: dict = Depends(require_user)):
    """Cockpit des marchés suivis : infos DAO complètes, avancement dossier, lots & résultat."""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT s.avis_id, s.statut, s.note, s.cree_le,
                   a.objet_marche                 AS objet,
                   a.autorite_contractante        AS autorite,
                   a.ministere_tutelle            AS ministere,
                   a.secteur_activite             AS secteur,
                   a.categorie_marche             AS categorie,
                   a.type_procedure               AS type,
                   a.numero_bulletin              AS bulletin,
                   a.pages                        AS pages,
                   a.date_parution                AS date_parution,
                   a.date_limite_depot            AS date_limite,
                   a.heure_limite_depot           AS heure_limite,
                   a.budget_previsionnel_fcfa     AS budget,
                   a.garantie_soumission_fcfa     AS caution,
                   a.cout_acquisition_dossier_fcfa AS cout_dao,
                   a.source_financement           AS financement,
                   a.exercice_budgetaire          AS exercice,
                   a.reference_dossier            AS reference,
                   a.nombre_lots                  AS nombre_lots,
                   a.allotissement_type           AS allotissement,
                   a.lieu_depot_offres            AS lieu_depot,
                   a.date_heure_ouverture_plis    AS date_ouverture,
                   a.lieu_ouverture_plis          AS lieu_ouverture,
                   a.delai_execution_jours        AS delai_execution,
                   a.delai_validite_offres_jours  AS delai_validite,
                   a.qualifications_ou_agrement   AS qualifications,
                   a.contacts_renseignements      AS contacts,
                   a.marche_reserve               AS marche_reserve,
                   a.signataire_nom_fonction      AS signataire,
                   d.id                           AS dossier_id,
                   (SELECT COUNT(*) FROM dossier_pieces dp WHERE dp.dossier_id = d.id) AS pieces_total,
                   (SELECT SUM(CASE WHEN dp.coche = 1 THEN 1 ELSE 0 END) FROM dossier_pieces dp WHERE dp.dossier_id = d.id) AS pieces_cochees,
                   (SELECT r.id FROM resultats_marches r
                      WHERE r.annonce_avis_id = s.avis_id LIMIT 1) AS resultat_id,
                   (SELECT rl.attributaire_nom FROM resultats_lots rl
                      JOIN resultats_marches rm ON rm.id = rl.resultat_id
                      WHERE rm.annonce_avis_id = s.avis_id AND rl.attributaire_nom IS NOT NULL
                      LIMIT 1) AS attributaire_nom,
                   (SELECT COALESCE(rl.montant_attribue_max_fcfa, rl.montant_attribue_min_fcfa)
                      FROM resultats_lots rl
                      JOIN resultats_marches rm ON rm.id = rl.resultat_id
                      WHERE rm.annonce_avis_id = s.avis_id
                      LIMIT 1) AS montant_attribue,
                   (SELECT MAX(rl.est_infructueux) FROM resultats_lots rl
                      JOIN resultats_marches rm ON rm.id = rl.resultat_id
                      WHERE rm.annonce_avis_id = s.avis_id) AS est_infructueux
            FROM suivis s
            LEFT JOIN annonces_avis a ON a.id = s.avis_id
            LEFT JOIN dossiers d ON d.user_id = s.user_id AND d.avis_id = s.avis_id
            WHERE s.user_id = ?
            ORDER BY s.cree_le DESC
            """,
            (user["id"],),
        ).fetchall()
        results = [dict(r) for r in rows]
        cockpit_stats = {
            "total": len(results),
            "je_soumissionne": sum(1 for x in results if x.get("statut") == "je_soumissionne"),
            "avec_resultat": sum(1 for x in results if x.get("resultat_id")),
            "budget_cumule": sum(int(x["budget"]) for x in results if x.get("budget")),
        }
        return {"results": results, "total": len(results), "cockpit_stats": cockpit_stats}
    finally:
        conn.close()


@router.get("/ids")
def list_suivi_ids(user: dict = Depends(require_user)):
    """Liste légère des avis_id suivis (pour griser/activer les boutons côté front)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT avis_id FROM suivis WHERE user_id = ?", (user["id"],)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


@router.post("")
def add_suivi(body: SuiviIn, user: dict = Depends(require_user)):
    """Suivre un marché (idempotent : met à jour le statut si déjà suivi)."""
    statut = body.statut if body.statut in _STATUTS else "suivi"
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM annonces_avis WHERE id = ?", (body.avis_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Marché introuvable.")
        conn.execute(
            """INSERT INTO suivis (user_id, avis_id, statut, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, avis_id)
               DO UPDATE SET statut = excluded.statut,
                             note = COALESCE(excluded.note, suivis.note)""",
            (user["id"], body.avis_id, statut, body.note),
        )
        conn.commit()
        return {"ok": True, "avis_id": body.avis_id, "statut": statut}
    finally:
        conn.close()


@router.patch("/{avis_id}")
def update_suivi(avis_id: str, body: SuiviPatch, user: dict = Depends(require_user)):
    """Changer le statut (ex. « je_soumissionne ») ou la note d'un marché suivi."""
    fields, params = [], []
    if body.statut is not None:
        if body.statut not in _STATUTS:
            raise HTTPException(status_code=400, detail="Statut invalide.")
        fields.append("statut = ?")
        params.append(body.statut)
    if body.note is not None:
        fields.append("note = ?")
        params.append(body.note)
    if not fields:
        return {"ok": True}
    params.extend([user["id"], avis_id])
    conn = get_db()
    try:
        cur = conn.execute(
            f"UPDATE suivis SET {', '.join(fields)} WHERE user_id = ? AND avis_id = ?",
            params,
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Suivi introuvable.")
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/{avis_id}")
def remove_suivi(avis_id: str, user: dict = Depends(require_user)):
    """Retirer un marché des suivis."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM suivis WHERE user_id = ? AND avis_id = ?",
            (user["id"], avis_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
