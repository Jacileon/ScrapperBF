"""
Structuration LLM d'une unité-émetteur de la section RÉSULTATS.

Entrée : une unité produite par pdf_resultats_extract.segment_resultats()
         (un émetteur = tout ce qui est entre deux « cadres noirs »), qui contient
         un ou plusieurs lots et un tableau multi-colonnes complexe.

Problème (posé par l'utilisateur) : ces tableaux ont des colonnes imbriquées
  Soumissionnaire | Montant lu (HTVA min/max, TTC min/max) | Montant corrigé
  (HTVA min/max, TTC min/max) | Observations
qui s'étalent sur plusieurs pages et dont les cellules sont multi-lignes.
L'extraction texte brute les aplatit ; il faut un LLM pour les restructurer.

Ce module fournit LES INSTRUCTIONS à l'IA (prompt système détaillé + schéma de
sortie) et l'appel via la rotation de providers de la Couche 3. On AIDE le modèle
avec un indice déterministe : le nombre de bandes « Lot » repérées dans la page
(unit["nb_lots_detectes"]) — pour qu'il sache combien de sous-tableaux attendre.

Pas de réseau ici : testé hors-ligne avec des providers injectés.
"""

import json
from typing import Optional

from layer3_extract_llm import call_with_rotation
from resultats_chunker import chunk_unit, merge_lot_results


# Schéma de sortie : un émetteur -> plusieurs lots -> plusieurs soumissionnaires.
def _montant_pair(desc):
    return {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "min": {"type": ["string", "null"], "description": desc + " (minimum, tel qu'écrit)"},
                    "max": {"type": ["string", "null"], "description": desc + " (maximum, tel qu'écrit)"},
                }
            },
            {"type": "null"}
        ]
    }


RESULTATS_SCHEMA = {
    "type": "object",
    "properties": {
        "autorite_contractante": {"type": ["string", "null"], "description": "Nom de l'émetteur (barre noire)"},
        "reference": {"type": ["string", "null"], "description": "N° du dossier / de l'appel, tel qu'écrit"},
        "objet": {"type": ["string", "null"], "description": "Objet global du marché"},
        "financement": {"type": ["string", "null"]},
        "date_depouillement": {"type": ["string", "null"], "description": "Date de dépouillement des offres"},
        "date_deliberation": {"type": ["string", "null"], "description": "Date de délibération de la commission"},
        "methode_selection": {"type": ["string", "null"], "description": "Sélection Qualité-Coût, Moindre Coût, Qualifications consultants, Demande de prix, etc."},
        "score_technique_min_requis": {"type": ["string", "null"], "description": "Seuil technique éliminatoire si mentionné (ex: 70 ou 75 pts)"},
        "decision_arcop_ref": {"type": ["string", "null"], "description": "Référence de décision ARCOP en cas de recours ou contentieux"},
        "est_rectificatif": {"type": ["boolean", "null"], "description": "true si c'est une synthèse rectificative ou erratum"},
        "remarques_extracteur": {"type": ["string", "null"], "description": "Alerte ou null"},
        "nombre_lots": {"type": ["integer", "null"], "description": "Nombre EXACT de lots dans ce tableau"},
        "budget_previsionnel": _montant_pair("Budget / Enveloppe prévisionnelle globale"),
        "lots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "numero": {"type": ["integer", "null"]},
                    "intitule": {"type": ["string", "null"], "description": "Libellé du lot (bande orange « Lot N : … »)"},
                    "nombre_plis_recus": {"type": ["integer", "null"], "description": "Nombre de plis reçus pour ce lot"},
                    "budget_lot": _montant_pair("Montant / Budget prévisionnel du lot"),
                    "moyenne_offres": {"type": ["string", "null"], "description": "Moyenne des offres financières des soumissionnaires"},
                    "borne_anormalement_basse": {"type": ["string", "null"], "description": "Borne inférieure / Borne anormalement basse"},
                    "seuil_tolerance_5pct": {"type": ["string", "null"], "description": "Seuil de tolérance (5% ou autre)"},
                    "borne_anormalement_elevee": {"type": ["string", "null"], "description": "Borne supérieure / Borne anormalement élevée"},
                    "soumissionnaires": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nom": {"type": ["string", "null"]},
                                "ifu": {"type": ["string", "null"], "description": "Numéro IFU si mentionné"},
                                "rccm": {"type": ["string", "null"], "description": "Numéro RCCM si mentionné"},
                                "contacts": {"type": ["string", "null"], "description": "Téléphone, email, BP si mentionnés"},
                                "score_technique": {"type": ["string", "null"], "description": "Note technique obtenue sur 100 si marché de prestations/consultants"},
                                "est_groupement": {"type": ["boolean", "null"], "description": "true si le soumissionnaire est un groupement d'entreprises"},
                                "montant_lu_htva": _montant_pair("Montant lu HTVA (min et max si commandes)"),
                                "montant_corrige_htva": _montant_pair("Montant corrigé HTVA (min et max si commandes)"),
                                "montant_lu_ttc": _montant_pair("Montant lu TTC (min et max si commandes)"),
                                "montant_corrige_ttc": _montant_pair("Montant corrigé TTC (min et max si commandes)"),
                                "conformite": {"type": ["string", "null"], "description": "conforme | non conforme | non recevable | …"},
                                "classement": {"type": ["string", "null"], "description": "1er | 2ème | Non classé | …"},
                                "categorie_rejet": {"type": ["string", "null"], "description": "OFFRE_ANORMALEMENT_BASSE | TECHNIQUE | ADMINISTRATIF | FINANCIER | null"},
                                "observations": {"type": ["string", "null"], "description": "Motif de rejet, écart arithmétique ou observation recopiée fidèlement"},
                            },
                        },
                    },
                    "attributaire_provisoire": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "nom": {"type": ["string", "null"]},
                                    "montant_min_ttc": {"type": ["string", "null"]},
                                    "montant_max_ttc": {"type": ["string", "null"]},
                                    "delai_execution": {"type": ["string", "null"]},
                                },
                            },
                            {"type": "null"}
                        ]
                    },
                    "infructueux": {"type": ["boolean", "null"], "description": "true si le lot est déclaré infructueux"},
                    "motif_infructueux": {"type": ["string", "null"], "description": "Motif si infructueux"},
                    "remarques_extracteur": {"type": ["string", "null"], "description": "Alerte ou doute spécifique à ce lot, ou null si certain"},
                },
            },
        },
    },
    "required": ["autorite_contractante", "lots"],
}


RESULTATS_SYSTEM_PROMPT = """Tu es un expert de la lecture des tableaux de RÉSULTATS provisoires des marchés
publics du Burkina Faso (Quotidien DGCMEF). On te donne le texte APLATI d'un seul
émetteur (tout ce qui se trouve entre deux « cadres noirs »). Ce texte provient
d'un ou plusieurs tableaux multi-colonnes qui se lisent mal une fois mis à plat.

STRUCTURE À RECONSTRUIRE (impérative) :
1. Un émetteur peut contenir PLUSIEURS LOTS. Chaque lot est introduit par une
   bande « Lot N : <intitulé> ». S'il n'y a aucune bande « Lot », c'est qu'il y a
   un lot unique (non numéroté) : rends alors un seul lot.
   -> Donne le nombre EXACT de lots dans "nombre_lots".
2. SEUILS ET MÉTRIQUES RÉGLEMENTAIRES (crucial) :
   - Extrais précisément au niveau de l'émetteur ou du lot :
     * "methode_selection" (ex: Qualité-Coût, Moindre Coût, Demande de prix...)
     * "score_technique_min_requis" (ex: "70 points" ou "75 points")
     * "decision_arcop_ref" (ex: décision ARCOP suite à recours ou contentieux)
     * "est_rectificatif" : true si mention "synthèse rectificative" ou "erratum"
     * "nombre_plis_recus" (ex: 6 ou 02)
     * "budget_lot" : minimum et maximum (si marché à commandes) ou montant forfaitaire
     * "moyenne_offres" (ex: "57 994 640")
     * "borne_anormalement_basse" / "borne_inferieure" (ex: "49 507 278")
     * "seuil_tolerance_5pct" (ex: "47 031 914")
     * "borne_anormalement_elevee" / "borne_superieure"
3. Pour CHAQUE lot, le tableau liste les SOUMISSIONNAIRES. Les colonnes sont :
     - Soumissionnaire (nom complet de l'entreprise ou groupement ou personne physique)
     - Coordonnées : IFU, RCCM, Téléphone, Email, BP si mentionnés dans la case
     - "est_groupement" : true si groupement de plusieurs entreprises
     - "score_technique" : note technique sur 100 si marché de consultants/prestations
     - « Montant lu » : décomposé en HTVA (Minimum ET Maximum si marché à commandes) ET TTC (Minimum ET Maximum)
     - « Montant corrigé » : décomposé en HTVA (Minimum ET Maximum) ET TTC (Minimum ET Maximum)
     - Classement / Rang (1er, 2ème, Non classé, etc.)
     - "categorie_rejet" : OFFRE_ANORMALEMENT_BASSE | TECHNIQUE | ADMINISTRATIF | FINANCIER | null
     - Observations (conformité + motif précis de rejet ou conformité)
   Beaucoup de cellules valent « -- » (non renseigné) : recopie-les en null.
   Les nombres sont parfois coupés sur plusieurs lignes dans le texte aplati :
   recompose le montant complet (ex. « 354 030 680 »), sans jamais inventer de chiffre.
4. Identifie l'ATTRIBUTAIRE PROVISOIRE de chaque lot : souvent une ligne « ✓ Lot N :
   <entreprise> pour un montant minimum TTC de … et un montant maximum TTC de …
   avec un délai d'exécution de … ». Si le lot est déclaré « infructueux », mets
   infructueux=true, remplis "motif_infructueux" et laisse l'attributaire vide.

RÈGLES :
- SIGNALEMENT DES DOUTES (remarques_extracteur) :
  Si un chiffre est flou, si le texte est coupé, si une colonne est ambiguë ou si l'attribution est incertaine,
  ne devine JAMAIS. Renseigne le champ "remarques_extracteur" pour m'alerter précisément sur ton incertitude.
  Si toutes les données sont claires et certaines, laisse "remarques_extracteur" à null.
- Ne DÉDUIS jamais un montant ; recopie exactement ce qui est écrit (espaces inclus),
  ou null si absent/« -- ».
- Associe chaque soumissionnaire au bon lot (ne mélange pas les lots).
- Réponds UNIQUEMENT par un objet JSON conforme au schéma fourni, sans texte autour.
"""


def build_resultats_prompt(unit: dict) -> str:
    """Construit le message utilisateur : indices déterministes + texte aplati."""
    lots = unit.get("lots") or []
    nb = unit.get("nb_lots_detectes", len(lots))
    indices = [
        f"Émetteur (cadre noir) : {unit.get('emetteur', '?')}",
        f"Macro-section : {unit.get('macro_section', '?')}",
        f"Pages : {unit.get('page_debut')}–{unit.get('page_fin')}",
        f"Bandes « Lot » repérées automatiquement : {nb}",
    ]
    if lots:
        indices.append("Intitulés de lots repérés :")
        indices += [f"  - {l}" for l in lots]
    return (
        "Indices (découpage déterministe, à vérifier) :\n"
        + "\n".join(indices)
        + "\n\nSchéma de sortie attendu (informatif) :\n"
        + json.dumps(RESULTATS_SCHEMA, ensure_ascii=False)
        + "\n\nTexte aplati du tableau à structurer :\n"
        "------------------------------------------------------------\n"
        + (unit.get("flat_text") or "")
        + "\n------------------------------------------------------------\n"
    )


def _structure_one(unit: dict, max_retries: int, providers: Optional[list]) -> Optional[dict]:
    """Un seul appel LLM pour un (morceau d')émetteur."""
    prompt = build_resultats_prompt(unit)
    return call_with_rotation(
        prompt, RESULTATS_SCHEMA, max_retries=max_retries,
        system_prompt=RESULTATS_SYSTEM_PROMPT, strict=False, providers=providers,
    )


def extract_resultats_unit(unit: dict, max_retries: int = 3,
                           providers: Optional[list] = None,
                           max_chars: int = 12000) -> Optional[dict]:
    """Structure une unité-émetteur en lots + soumissionnaires + attributaires.

    Si le texte tient en un appel (<= max_chars), appel unique. Sinon, découpage
    aux frontières de lots (resultats_chunker) puis fusion dédupliquée : l'intégrité
    est préservée même sur une unité géante (ex. 4503bis). Rend le dict structuré +
    provenance, ou None si tout échoue."""
    flat = unit.get("flat_text", "") or ""

    if len(flat) <= max_chars:
        result = _structure_one(unit, max_retries, providers)
        nb_chunks = 1
        if result is None:
            return None
    else:
        chunks = chunk_unit(unit, max_chars=max_chars)
        parts = []
        for ch in chunks:
            r = _structure_one(ch, max_retries, providers)
            if r is not None:
                parts.append(r)
        if not parts:
            return None
        result = merge_lot_results(parts)
        nb_chunks = len(chunks)

    for k in ("_numero", "_source_pdf", "_source", "page_debut", "page_fin",
              "macro_section", "emetteur"):
        if k in unit:
            result.setdefault(k, unit[k])
    nb_struct = len(result.get("lots") or [])
    result["_nb_chunks"] = nb_chunks
    result["_nb_lots_detectes"] = unit.get("nb_lots_detectes")
    result["_coherence_lots"] = (
        nb_struct == unit.get("nb_lots_detectes")
        or (unit.get("nb_lots_detectes", 0) <= 1 and nb_struct >= 1)
    )
    return result


if __name__ == "__main__":
    import sys
    from pdf_resultats_extract import segment_resultats
    if len(sys.argv) < 2:
        print("Usage: python resultats_llm.py <pdf>   # affiche le prompt de la 1re unité (sans appel réseau)")
        sys.exit(1)
    units = segment_resultats(sys.argv[1])
    if not units:
        print("Aucune unité RÉSULTATS détectée.")
        sys.exit(0)
    print("=== SYSTEM PROMPT ===")
    print(RESULTATS_SYSTEM_PROMPT)
    print("\n=== USER PROMPT (1re unité) ===")
    print(build_resultats_prompt(units[0])[:2500])
