#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_resultats_to_front.py
============================
Exporte les RÉSULTATS (attributions) et les ENTREPRISES (soumissionnaires
agrégés) vers le front, dans un fichier séparé afin de ne pas interférer
avec export_db_to_front.py.

Lecture seule de marches_publics_burkina.db.
Génère web/app/assets/data_resultats.js : window.DATA_RESULTATS = {...}
"""
import sqlite3
import json
import re
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


def clean_contact_field(raw_tel, raw_bp):
    """
    Sépare et filtre les téléphones et adresses BP/ville.
    Élimine les notes administratives/procédurales.
    """
    tel_out = (raw_tel or "").strip()
    bp_out = (raw_bp or "").strip()

    if not tel_out:
        return None, (bp_out if bp_out else None)

    # Détection de notes administratives/procédurales dans le téléphone
    admin_patterns = [
        r"confirmation.*",
        r"lettre\s+n[°o].*",
        r"offre\s+(?:financière|technique|conforme|rejetée).*",
        r"rabais.*",
        r"sous\s+réserve.*",
        r"variation.*constatée.*"
    ]
    for pat in admin_patterns:
        if re.search(pat, tel_out, re.IGNORECASE):
            return None, (bp_out if bp_out else None)

    # Extraction BP ou adresse intégrée dans tel_out
    bp_match = re.search(r"((?:s/c\s*)?\d+\s*BP\s*\d+[^,\n]+)", tel_out, re.IGNORECASE)
    if bp_match:
        found_bp = bp_match.group(1).strip()
        if not bp_out:
            bp_out = found_bp
        tel_out = tel_out.replace(bp_match.group(0), "")

    # Nettoyer préfixes "Tel :", "Tél :", "Tel:", etc.
    tel_out = re.sub(r"^(?:,\s*)?(?:t[eé]l\s*[:\.]?\s*)+", "", tel_out, flags=re.IGNORECASE).strip()
    tel_out = tel_out.strip(" ,;:-")

    # Valider qu'il y a au moins un vrai numéro BF (8 chiffres, ne commençant pas par 00 comme les IFU)
    valid_nums = []
    for m_num in re.findall(r"(?:\+?226[\s\.-]*)?((?:0[1-7]|2[0-7]|5[0-8]|6\d|7\d)(?:[\s\.\-]?\d{2}){3})", tel_out):
        digits = re.sub(r"\D", "", m_num)
        if len(digits) == 8 and not digits.startswith("00"):
            valid_nums.append(digits)
    if valid_nums:
        tel_out = " / ".join(dict.fromkeys(valid_nums))
    else:
        tel_out = ""

    return (tel_out if tel_out else None), (bp_out if bp_out else None)


def detect_ville(text):
    if not text:
        return None
    t = text.lower()
    villes = [
        ("ouagadougou", "Ouagadougou"),
        ("ouaga", "Ouagadougou"),
        ("bobo-dioulasso", "Bobo-Dioulasso"),
        ("bobo", "Bobo-Dioulasso"),
        ("koudougou", "Koudougou"),
        ("ouahigouya", "Ouahigouya"),
        ("fada n'gourma", "Fada N'Gourma"),
        ("fada", "Fada N'Gourma"),
        ("dédougou", "Dédougou"),
        ("dedougou", "Dédougou"),
        ("banfora", "Banfora"),
        ("kaya", "Kaya"),
        ("tenkodogo", "Tenkodogo"),
        ("ziniaré", "Ziniaré"),
        ("ziniare", "Ziniaré"),
        ("manga", "Manga"),
        ("dori", "Dori"),
        ("gaoua", "Gaoua"),
        ("saaba", "Saaba"),
        ("pô", "Pô"),
        ("po", "Pô"),
        ("koupéla", "Koupéla"),
        ("koupela", "Koupéla")
    ]
    for pattern, name in villes:
        if re.search(r"\b" + re.escape(pattern) + r"\b", t):
            return name
    return None


def write(data):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "// Généré par export_resultats_to_front.py — ne pas éditer à la main\n"
        "window.DATA_RESULTATS = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )


def build_front_payload(db_path: Path = DB) -> dict:
    if not db_path.exists():
        return {"resultats": [], "entreprises": [], "stats": {}, "ready": False}

    con = sqlite3.connect(db_path, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    cur = con.cursor()
    tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    need = {"resultats_marches", "resultats_lots", "resultats_soumissionnaires"}
    if not need.issubset(tables):
        con.close()
        return {"resultats": [], "entreprises": [], "stats": {}, "ready": False}

    marches = {m["id"]: m for m in rows(cur, "SELECT * FROM resultats_marches")}
    lots = rows(cur, "SELECT * FROM resultats_lots")

    # Noms canoniques des attributaires par (résultat, lot) -> lien exact avec les entreprises (y compris multi-attributaires)
    win_canons = {}
    for w in rows(cur, "SELECT resultat_id, lot_id, nom_canonique FROM resultats_soumissionnaires WHERE est_attributaire = 1"):
        if w["nom_canonique"]:
            win_canons.setdefault((w["resultat_id"], w["lot_id"]), []).append(w["nom_canonique"])

    # ---- RÉSULTATS : une entrée par lot (attribué ou infructueux) ----
    resultats = []
    for lot in lots:
        m = marches.get(lot["resultat_id"], {})
        lot_winners = list(dict.fromkeys(win_canons.get((lot["resultat_id"], lot["id"]), [])))
        attr_display = lot["attributaire_nom"] or (" ; ".join(lot_winners) if lot_winners else None)
        resultats.append({
            "attributaire_canon": (lot_winners[0] if lot_winners else None) or lot["attributaire_nom"],
            "attributaires_canons": lot_winners,
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
            "attributaire": attr_display,
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
    _INVALID_NAMES = {
        "NON", "OUI", "OFFRE", "AUCUN", "NEANT", "NÉANT", "INCONNU",
        "SOUMISSIONNAIRE INCONNU", "RETENU", "NON RETENU", "CONFORME",
        "NON CONFORME", "ATTRIBUTAIRE", "RAS", "N/A", "NA", "-", "...",
        "PAS", "SANS", "BF", "RE (S)", "SOUMISSIONNAIRE", "ENTREPRISE",
    }
    ent = {}
    for s in subs:
        nom = (s["nom_canonique"] or s["nom_soumissionnaire"] or "").strip()
        nom_up = nom.upper()
        if not nom or len(nom) <= 2 or nom.isdigit() or nom_up in _INVALID_NAMES:
            continue
        e = ent.setdefault(nom, {
            "nom": nom, "soumissions": 0, "gagnes": 0, "montant_gagne": 0,
            "conformes": 0, "secteurs": set(), "ifu": None, "rccm": None,
            "tel": None, "email": None, "adresse": None, "ville": None, "groupement": False,
        })
        e["soumissions"] += 1
        conf = (s["conformite"] or "").lower()
        if "conform" in conf and "non conform" not in conf:
            e["conformes"] += 1
        if s["est_attributaire"]:
            e["gagnes"] += 1
            mt = best(
                s["montant_corrige_ttc_min"] or s["montant_lu_ttc_min"] or s["montant_corrige_htva_min"] or s["montant_lu_htva_min"],
                s["montant_corrige_ttc_max"] or s["montant_lu_ttc_max"] or s["montant_corrige_htva_max"] or s["montant_lu_htva_max"],
            )
            if mt:
                e["montant_gagne"] += mt
        if s["secteur"]:
            e["secteurs"].add(s["secteur"])

        # Coordonnées avec nettoyage
        c_tel, c_bp = clean_contact_field(s.get("telephone"), s.get("adresse_bp"))
        if not e["ifu"] and s.get("ifu"):
            e["ifu"] = str(s["ifu"]).strip()
        if not e["rccm"] and s.get("rccm"):
            e["rccm"] = str(s["rccm"]).strip()
        if not e["tel"] and c_tel:
            e["tel"] = c_tel
        if not e["email"] and s.get("email"):
            e["email"] = str(s["email"]).strip()
        if not e["adresse"] and c_bp:
            e["adresse"] = c_bp

        # Détection de ville
        if not e["ville"]:
            detected = detect_ville(c_bp) or detect_ville(s.get("telephone")) or detect_ville(s.get("observations_motifs"))
            if detected:
                e["ville"] = detected

        if s.get("est_groupement"):
            e["groupement"] = True

    entreprises = []
    villes_set = set()
    for e in ent.values():
        e["secteurs"] = sorted(e["secteurs"])
        e["taux_reussite"] = round(100 * e["gagnes"] / e["soumissions"]) if e["soumissions"] else 0
        if e["ville"]:
            villes_set.add(e["ville"])
        entreprises.append(e)
    entreprises.sort(key=lambda x: (-x["gagnes"], -x["montant_gagne"], -x["soumissions"]))

    attributions = [r for r in resultats if r["attributaire"] and not r["infructueux"]]
    stats = {
        "nb_resultats": len(marches),
        "nb_attributions": len(attributions),
        "nb_infructueux": sum(1 for r in resultats if r["infructueux"]),
        "nb_entreprises": len(entreprises),
        "montant_total": sum((r["montant"] or 0) for r in attributions),
        "villes": sorted(villes_set),
    }

    payload = {"resultats": resultats, "entreprises": entreprises, "stats": stats, "ready": True}
    con.close()
    return payload


def main():
    if not DB.exists():
        print(f"Base de données {DB} introuvable.")
        return
    payload = build_front_payload(DB)
    if not payload.get("ready"):
        write(payload)
        print("Tables de résultats absentes — fichier vide généré.")
        return
    write(payload)
    stats = payload["stats"]
    print(f"OK — {stats['nb_resultats']} résultats, {stats['nb_attributions']} attributions, "
          f"{stats['nb_entreprises']} entreprises, {stats['nb_infructueux']} infructueux, {len(stats['villes'])} villes.")


if __name__ == "__main__":
    main()
