#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/jobs.py
===============
Génération des notifications et envoi des alertes.

- generate_for_user(user_id) : alerte résultat (boucle fermée) + radar concurrent
  + échéances (« dernière chance »). Appelé paresseusement à l'ouverture du fil.
- generate_all() : pour un cron (balaye tous les utilisateurs concernés).
- envoyer_alertes_du_jour() : pousse aux abonnés d'alertes les marchés correspondants
  via la couche backend.notifications (log par défaut, email/WhatsApp si configuré).
"""

from __future__ import annotations

import json
from datetime import datetime

from backend import alertes_resultats
from backend import notifications as notif
from backend.db import get_db


def _fmt(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ") + " FCFA"
    except Exception:
        return "—"


def _days_left(s: str):
    try:
        return (datetime.strptime(s.strip()[:10], "%d/%m/%Y").date() - datetime.now().date()).days
    except Exception:
        return None


def _insert(conn, user_id, type_, avis_id, key, titre, message, payload):
    conn.execute(
        """INSERT OR IGNORE INTO notifications
             (user_id, type, avis_id, resultat_id, titre, message, payload_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, type_, avis_id, key, titre, message, json.dumps(payload, ensure_ascii=False)),
    )


def generate_radar(conn, user_id: int) -> int:
    """Alerte quand une entreprise surveillée a (récemment) remporté un marché."""
    created = 0
    noms = [r[0] for r in conn.execute(
        "SELECT entreprise_nom FROM radar_concurrents WHERE user_id = ?", (user_id,)
    ).fetchall()]
    for nom in noms:
        win = conn.execute(
            """SELECT m.id AS rid, m.objet AS objet, m.autorite_contractante AS autorite,
                      m.annonce_avis_id AS avis_id,
                      l.montant_attribue_max_fcfa AS mtmax, l.montant_attribue_min_fcfa AS mtmin
               FROM resultats_soumissionnaires s
               JOIN resultats_marches m ON m.id = s.resultat_id
               LEFT JOIN resultats_lots l ON l.id = s.lot_id
               WHERE s.nom_canonique = ? AND s.est_attributaire = 1
               ORDER BY m.date_extraction DESC LIMIT 1""",
            (nom,),
        ).fetchone()
        if not win:
            continue
        key = f"{win['rid']}#{nom}"
        if conn.execute(
            "SELECT 1 FROM notifications WHERE user_id=? AND type='radar' AND resultat_id=?",
            (user_id, key),
        ).fetchone():
            continue
        montant = win["mtmax"] or win["mtmin"]
        msg = (f"{nom} a remporté « {(win['objet'] or 'un marché')[:70]} »"
               + (f" pour {_fmt(montant)}" if montant else "") + ".")
        _insert(conn, user_id, "radar", win["avis_id"], key, "Concurrent surveillé", msg,
                {"entreprise": nom, "objet": win["objet"], "autorite": win["autorite"], "montant": montant})
        created += 1
    return created


def generate_echeances(conn, user_id: int) -> int:
    """« Dernière chance » : rappel J-3 et J-1 sur les marchés suivis."""
    created = 0
    rows = conn.execute(
        """SELECT s.avis_id AS avis_id, a.objet_marche AS objet, a.date_limite_depot AS dl
           FROM suivis s JOIN annonces_avis a ON a.id = s.avis_id
           WHERE s.user_id = ? AND s.statut != 'abandonne'""",
        (user_id,),
    ).fetchall()
    for r in rows:
        d = _days_left(r["dl"] or "")
        if d is None:
            continue
        for seuil in (3, 1):
            if d == seuil:
                key = f"deadline-{r['avis_id']}-{seuil}"
                if conn.execute(
                    "SELECT 1 FROM notifications WHERE user_id=? AND type='echeance' AND resultat_id=?",
                    (user_id, key),
                ).fetchone():
                    continue
                msg = (f"Plus que {seuil} jour" + ("s" if seuil > 1 else "")
                       + f" pour déposer : « {(r['objet'] or 'marché suivi')[:70]} ».")
                _insert(conn, user_id, "echeance", r["avis_id"], key, "⏰ Échéance proche", msg,
                        {"jours": seuil, "objet": r["objet"]})
                created += 1
    return created


def generate_for_user(user_id: int) -> int:
    """Toutes les notifications manquantes pour un utilisateur."""
    total = alertes_resultats.generate_for_user(user_id)
    conn = get_db()
    try:
        total += generate_radar(conn, user_id)
        total += generate_echeances(conn, user_id)
        conn.commit()
    finally:
        conn.close()
    return total


def generate_all() -> int:
    conn = get_db()
    try:
        uids = set(r[0] for r in conn.execute("SELECT DISTINCT user_id FROM suivis").fetchall())
        uids |= set(r[0] for r in conn.execute("SELECT DISTINCT user_id FROM radar_concurrents").fetchall())
    finally:
        conn.close()
    return sum(generate_for_user(uid) for uid in uids)


def envoyer_alertes_du_jour(limit_par_alerte: int = 5) -> dict:
    """Pousse aux abonnés d'alertes les marchés correspondants (couche notifications)."""
    conn = get_db()
    envois = 0
    try:
        alertes = [dict(r) for r in conn.execute(
            "SELECT * FROM alertes WHERE actif = 1"
        ).fetchall()]
        for al in alertes:
            cond, params = [], []
            if al.get("secteur"):
                cond.append("secteur_activite = ?"); params.append(al["secteur"])
            if al.get("type_marche"):
                cond.append("type_procedure LIKE ?"); params.append(f"%{al['type_marche']}%")
            where = ("WHERE " + " AND ".join(cond)) if cond else ""
            rows = conn.execute(
                f"""SELECT objet_marche AS objet, autorite_contractante AS autorite,
                           date_limite_depot AS dl
                    FROM annonces_avis {where} ORDER BY rowid DESC LIMIT ?""",
                params + [limit_par_alerte],
            ).fetchall()
            if not rows:
                continue
            lignes = [f"• {(r['objet'] or 'Marché')[:70]} — dépôt {r['dl'] or 'n.c.'}" for r in rows]
            message = "Vos nouveaux marchés :\n" + "\n".join(lignes)
            res = notif.send(al.get("canal") or "log", al.get("cible"),
                             "Veille BF — alerte du jour", message)
            if res.get("ok"):
                envois += 1
    finally:
        conn.close()
    return {"alertes": len(alertes), "envois": envois}


def envoyer_digest_hebdo() -> dict:
    """Résumé hebdomadaire par utilisateur ayant un contact d'alerte."""
    conn = get_db()
    envois = 0
    try:
        cibles = conn.execute(
            """SELECT user_id, canal, cible FROM alertes
               WHERE user_id IS NOT NULL AND cible IS NOT NULL GROUP BY user_id"""
        ).fetchall()
        for c in cibles:
            uid = c["user_id"]
            suivis = conn.execute("SELECT COUNT(*) FROM suivis WHERE user_id=?", (uid,)).fetchone()[0]
            radar = conn.execute("SELECT COUNT(*) FROM radar_concurrents WHERE user_id=?", (uid,)).fetchone()[0]
            notifs = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id=? AND lu=0", (uid,)
            ).fetchone()[0]
            msg = (f"Votre semaine Veille BF : {suivis} marché(s) suivi(s), "
                   f"{radar} concurrent(s) surveillé(s), {notifs} notification(s) non lue(s).")
            if notif.send(c["canal"] or "log", c["cible"], "Veille BF — votre semaine", msg).get("ok"):
                envois += 1
    finally:
        conn.close()
    return {"cibles": len(cibles), "envois": envois}


if __name__ == "__main__":
    n = generate_all()
    print(f"[jobs] {n} notification(s) générée(s).")
    print("[jobs] alertes:", envoyer_alertes_du_jour())
    print("[jobs] digest hebdo:", envoyer_digest_hebdo())
