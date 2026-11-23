#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_resultats_to_front.py
============================
Exporte les RÉSULTATS (attributions) et les ENTREPRISES (soumissionnaires
agrégés) vers le front, dans un fichier séparé afin de ne pas interférer
avec export_db_to_front.py.

Lecture seule de marches_publics_burkina.db.
Génère web/app/assets/data_resultats.js :  window.DATA_RESULTATS = {...}
"""
import sqlite3
import json
from pathlib import Path

DB = Path("marches_publics_burkina.db")
OUT = Path("web/app/assets/data_resultats.js")


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def best(a, b):
    vals = [v for v in (a, b) if v]
    return max(vals) if vals else None


def write(data):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "// Généré par export_resultats_to_front.py — ne pas éditer à la main\n"
        "window.DATA_RESULTATS = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    need = {"resultats_marches", "resultats_lots", "resultats_soumissionnaires"}
    if not need.issubset(tables):
        write({"resultats": [], "entreprises": [], "stats": {}, "ready": False})
        print("Tables de résultats absentes — fichier vide généré.")
        return

    marches = {m["id"]: m for m in rows(cur, "SELECT * FROM resultats_marches")}
    lots = rows(cur, "SELECT * FROM resultats_lots")

    # Nom canonique de l'attributaire par (résultat, lot) -> lien exact avec les entreprises
    win_canon = {}
    for w in rows(cur, "SELECT resultat_id, lot_id, nom_canonique FROM resultats_soumissionnaires WHERE est_attributaire = 1"):
        if w["nom_canonique"]:
            win_canon[(w["resultat_id"], w["lot_id"])] = w["nom_canonique"]

    # ---- RÉSULTATS : une entrée par lot (attribué ou infructueux) ----
    resultats = []
    for lot in lots:
        m = marches.get(lot["resultat_id"], {})
        resultats.append({
            "attributaire_canon": win_canon.get((lot["resultat_id"], lot["id"])) or lot["attributaire_nom"],
            "id": f'{lot["resultat_id"]}#{lot["numero_lot"]}',
            "marche_id": lot["resultat_id"],
            "avis_id": m.get("annonce_avis_id"),
            "objet": m.get("objet"),
            "autorite": m.get("autorite_contractante"),
            "secteur": m.get("secteur_activite"),
            "bulletin": m.get("bulletin"),
            "pages": m.get("pages"),
            "date": m.get("date_parution"),
            "date_depouillement": m.get("date_depouillement"),
            "reference": m.get("reference_dossier"),
            "lot": lot["numero_lot"],
            "intitule": lot["intitule_lot"],
            "nb_plis": lot["nombre_plis_recus"],
            "attributaire": lot["attributaire_nom"],
            "montant": best(lot["montant_attribue_min_fcfa"], lot["montant_attribue_max_fcfa"]),
            "infructueux": bool(lot["est_infructueux"]),
            "motif": lot["motif_infructueux"],
            "delai": lot["delai_execution"],
        })

    # ---- ENTREPRISES : agrégation des soumissionnaires par nom canonique ----
    subs = rows(cur, """
        SELECT s.*, m.secteur_activite AS secteur
        FROM resultats_soumissionnaires s
        LEFT JOIN resultats_marches m ON m.id = s.resultat_id
    """)
    ent = {}
    for s in subs:
        nom = (s["nom_canonique"] or s["nom_soumissionnaire"] or "").strip()
        if not nom:
            continue
        e = ent.setdefault(nom, {
            "nom": nom, "soumissions": 0, "gagnes": 0, "montant_gagne": 0,
            "conformes": 0, "secteurs": set(), "ifu": None, "rccm": None,
            "tel": None, "email": None, "groupement": False,
        })
        e["soumissions"] += 1
        conf = (s["conformite"] or "").lower()
        if "conform" in conf and "non conform" not in conf:
            e["conformes"] += 1
        if s["est_attributaire"]:
            e["gagnes"] += 1
            mt = best(s["montant_corrige_ttc_min"] or s["montant_lu_ttc_min"],
                      s["montant_corrige_ttc_max"] or s["montant_lu_ttc_max"])
            if mt:
                e["montant_gagne"] += mt
        if s["secteur"]:
            e["secteurs"].add(s["secteur"])
        for key, col in (("ifu", "ifu"), ("rccm", "rccm"), ("tel", "telephone"), ("email", "email")):
            if not e[key] and s[col]:
                e[key] = s[col]
        if s["est_groupement"]:
            e["groupement"] = True

    entreprises = []
    for e in ent.values():
        e["secteurs"] = sorted(e["secteurs"])
        e["taux_reussite"] = round(100 * e["gagnes"] / e["soumissions"]) if e["soumissions"] else 0
        entreprises.append(e)
    entreprises.sort(key=lambda x: (-x["gagnes"], -x["montant_gagne"], -x["soumissions"]))

    attributions = [r for r in resultats if r["attributaire"] and not r["infructueux"]]
    stats = {
        "nb_resultats": len(marches),
        "nb_attributions": len(attributions),
        "nb_infructueux": sum(1 for r in resultats if r["infructueux"]),
        "nb_entreprises": len(entreprises),
        "montant_total": sum((r["montant"] or 0) for r in attributions),
    }

    write({"resultats": resultats, "entreprises": entreprises, "stats": stats, "ready": True})
    con.close()
    print(f"OK — {stats['nb_resultats']} résultats, {stats['nb_attributions']} attributions, "
          f"{stats['nb_entreprises']} entreprises, {stats['nb_infructueux']} infructueux.")


if __name__ == "__main__":
    main()
