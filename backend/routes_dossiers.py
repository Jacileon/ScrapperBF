#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/routes_dossiers.py
==========================
Suivi de dossier (préparation de soumission) : statut, checklist de pièces à
cocher, et agenda .ics des dates limites (marchés suivis + dossiers).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend import pdfgen
from backend.db import get_db
from backend.deps import require_user

router = APIRouter(prefix="/api", tags=["dossiers"])

_STATUTS = {"a_etudier", "en_preparation", "depose", "gagne", "perdu"}

# Pièces type d'un dossier de marché public au Burkina Faso.
PIECES_DEFAUT = [
    "Lettre de soumission",
    "Garantie de soumission (caution)",
    "Attestation de situation fiscale (DGI)",
    "Attestation CNSS",
    "Registre du commerce (RCCM)",
    "Numéro IFU",
    "Agrément technique (si exigé)",
    "Références de marchés similaires",
    "Offre technique",
    "Offre financière (bordereau des prix)",
]


class DossierIn(BaseModel):
    avis_id: str


class DossierPatch(BaseModel):
    statut: str


class PieceIn(BaseModel):
    libelle: str


class PiecePatch(BaseModel):
    coche: Optional[bool] = None
    libelle: Optional[str] = None


def _dossier_id(conn, user_id: int, avis_id: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM dossiers WHERE user_id = ? AND avis_id = ?", (user_id, avis_id)
    ).fetchone()
    return row["id"] if row else None


@router.get("/dossiers")
def list_dossiers(user: dict = Depends(require_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT d.id, d.avis_id, d.statut, d.cree_le,
                      a.objet_marche AS objet, a.autorite_contractante AS autorite,
                      a.date_limite_depot AS date_limite
               FROM dossiers d LEFT JOIN annonces_avis a ON a.id = d.avis_id
               WHERE d.user_id = ? ORDER BY d.maj_le DESC""",
            (user["id"],),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            pieces = [dict(p) for p in conn.execute(
                "SELECT id, libelle, coche, ordre FROM dossier_pieces WHERE dossier_id = ? ORDER BY ordre, id",
                (d["id"],),
            ).fetchall()]
            d["pieces"] = pieces
            d["pieces_total"] = len(pieces)
            d["pieces_cochees"] = sum(1 for p in pieces if p["coche"])
            out.append(d)
        return {"results": out, "total": len(out)}
    finally:
        conn.close()


@router.post("/dossiers")
def create_dossier(body: DossierIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM annonces_avis WHERE id = ?", (body.avis_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Marché introuvable.")
        existing = _dossier_id(conn, user["id"], body.avis_id)
        if existing:
            return {"ok": True, "id": existing, "deja": True}
        cur = conn.execute(
            "INSERT INTO dossiers (user_id, avis_id, statut) VALUES (?, ?, 'a_etudier') RETURNING id",
            (user["id"], body.avis_id),
        )
        did = cur.fetchone()[0]
        for i, lib in enumerate(PIECES_DEFAUT):
            conn.execute(
                "INSERT INTO dossier_pieces (dossier_id, libelle, ordre) VALUES (?, ?, ?)",
                (did, lib, i),
            )
        conn.commit()
        return {"ok": True, "id": did}
    finally:
        conn.close()


@router.patch("/dossiers/{avis_id}")
def update_dossier(avis_id: str, body: DossierPatch, user: dict = Depends(require_user)):
    if body.statut not in _STATUTS:
        raise HTTPException(status_code=400, detail="Statut invalide.")
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE dossiers SET statut = ?, maj_le = CURRENT_TIMESTAMP WHERE user_id = ? AND avis_id = ?",
            (body.statut, user["id"], avis_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Dossier introuvable.")
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/dossiers/{avis_id}")
def delete_dossier(avis_id: str, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        conn.execute("DELETE FROM dossiers WHERE user_id = ? AND avis_id = ?", (user["id"], avis_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/dossiers/{avis_id}/pieces")
def add_piece(avis_id: str, body: PieceIn, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        did = _dossier_id(conn, user["id"], avis_id)
        if not did:
            raise HTTPException(status_code=404, detail="Dossier introuvable.")
        n = conn.execute("SELECT COALESCE(MAX(ordre),-1)+1 AS o FROM dossier_pieces WHERE dossier_id = ?", (did,)).fetchone()["o"]
        cur = conn.execute(
            "INSERT INTO dossier_pieces (dossier_id, libelle, ordre) VALUES (?, ?, ?) RETURNING id",
            (did, body.libelle.strip(), n),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return {"ok": True, "id": new_id}
    finally:
        conn.close()


@router.patch("/dossiers/pieces/{piece_id}")
def update_piece(piece_id: int, body: PiecePatch, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        # vérifier appartenance
        own = conn.execute(
            """SELECT 1 FROM dossier_pieces p JOIN dossiers d ON d.id = p.dossier_id
               WHERE p.id = ? AND d.user_id = ?""", (piece_id, user["id"]),
        ).fetchone()
        if not own:
            raise HTTPException(status_code=404, detail="Pièce introuvable.")
        if body.coche is not None:
            conn.execute("UPDATE dossier_pieces SET coche = ? WHERE id = ?", (int(body.coche), piece_id))
        if body.libelle is not None:
            conn.execute("UPDATE dossier_pieces SET libelle = ? WHERE id = ?", (body.libelle.strip(), piece_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/dossiers/pieces/{piece_id}")
def delete_piece(piece_id: int, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        conn.execute(
            """DELETE FROM dossier_pieces WHERE id = ? AND dossier_id IN
               (SELECT id FROM dossiers WHERE user_id = ?)""", (piece_id, user["id"]),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/dossiers/{avis_id}/pdf")
def dossier_pdf(avis_id: str, user: dict = Depends(require_user)):
    """Génère une fiche de soumission PDF (récap marché + checklist)."""
    conn = get_db()
    try:
        a = conn.execute(
            """SELECT objet_marche, autorite_contractante, reference_dossier,
                      date_limite_depot, budget_previsionnel_fcfa, lieu_depot_offres
               FROM annonces_avis WHERE id = ?""", (avis_id,),
        ).fetchone()
        if not a:
            raise HTTPException(status_code=404, detail="Marché introuvable.")
        did = _dossier_id(conn, user["id"], avis_id)
        pieces = []
        if did:
            pieces = [dict(p) for p in conn.execute(
                "SELECT libelle, coche FROM dossier_pieces WHERE dossier_id = ? ORDER BY ordre, id", (did,),
            ).fetchall()]
    finally:
        conn.close()

    societe = user.get("organisation") or user.get("nom") or user.get("email") or "Votre entreprise"

    def fcfa(n):
        try:
            return f"{int(n):,}".replace(",", " ") + " FCFA"
        except Exception:
            return "Non précisé"

    lines = [
        {"text": "FICHE DE SOUMISSION", "size": 17, "bold": True},
        {"text": societe, "size": 12, "gap": 6},
        {"text": "Marché visé", "size": 13, "bold": True, "gap": 14},
        {"text": a["objet_marche"] or "—", "size": 11, "gap": 2},
        {"text": "Autorité : " + (a["autorite_contractante"] or "—"), "gap": 4},
        {"text": "Référence : " + (a["reference_dossier"] or "—")},
        {"text": "Date limite de dépôt : " + (a["date_limite_depot"] or "—")},
        {"text": "Budget prévisionnel : " + fcfa(a["budget_previsionnel_fcfa"])},
        {"text": "Lieu de dépôt : " + (a["lieu_depot_offres"] or "Selon le dossier")},
        {"text": "Pièces à fournir", "size": 13, "bold": True, "gap": 16},
    ]
    if pieces:
        for p in pieces:
            mark = "[X]" if p["coche"] else "[  ]"
            lines.append({"text": f"{mark}  {p['libelle']}", "gap": 2})
    else:
        for lib in PIECES_DEFAUT:
            lines.append({"text": f"[  ]  {lib}", "gap": 2})
    lines.append({"text": "Document généré par Veille BF — à vérifier avec le dossier d'appel d'offres officiel.",
                  "size": 9, "gap": 20})

    pdf = pdfgen.build_pdf(lines)
    fname = "fiche-soumission.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


# --------------------------------------------------------------------------- #
# Agenda .ics des dates limites (marchés suivis + dossiers)
# --------------------------------------------------------------------------- #
def _ics_date(date_limite: str) -> Optional[str]:
    if not date_limite:
        return None
    try:
        import re
        s = date_limite.strip()
        m = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', s)
        if m:
            return f"{int(m.group(3)):04d}{int(m.group(2)):02d}{int(m.group(1)):02d}"
        m_iso = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
        if m_iso:
            return f"{int(m_iso.group(1)):04d}{int(m_iso.group(2)):02d}{int(m_iso.group(3)):02d}"
    except Exception:
        pass
    return None


@router.get("/agenda.ics")
def agenda_ics(request: Request, user: dict = Depends(require_user)):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT DISTINCT a.id, a.objet_marche AS objet, a.autorite_contractante AS autorite,
                      a.date_limite_depot AS date_limite
               FROM annonces_avis a
               WHERE a.id IN (SELECT avis_id FROM suivis WHERE user_id = ?)
                  OR a.id IN (SELECT avis_id FROM dossiers WHERE user_id = ?)""",
            (user["id"], user["id"]),
        ).fetchall()
    finally:
        conn.close()

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Veille BF//Agenda//FR", "CALSCALE:GREGORIAN"]
    for r in rows:
        dt = _ics_date(r["date_limite"] or "")
        if not dt:
            continue
        objet = (r["objet"] or "Marché").replace("\n", " ")[:120]
        auth = (r["autorite"] or "").replace("\n", " ")
        lines += [
            "BEGIN:VEVENT",
            f"UID:vbf-{r['id']}@veillebf",
            f"DTSTART;VALUE=DATE:{dt}",
            f"SUMMARY:Dépôt — {objet}",
            f"DESCRIPTION:{auth}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return Response(content="\r\n".join(lines), media_type="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=veillebf-agenda.ics"})
