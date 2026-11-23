"""
prod_pipeline/macro_splitter.py — Macro-Split dual-stratégie (Sommaire p.2 + repli visuel).

Stratégies de découpage :
- Stratégie A (Prioritaire) : Analyse structurée du sommaire imprimé en page 2.
  - Découpage géométrique de la colonne de droite (évite la contamination des coordonnées administratives de gauche).
  - Détection déterministe des rubriques RÉSULTATS (MIMOD, Régions) et AVIS (Fournitures, Travaux, Prestations).
  - Calibration automatique du delta de pagination (page imprimée vs index réel PDF).
- Stratégie B (Repli / Fallback) : Parcours des pages et détection des marqueurs visuels.
  - Barres noires transversales -> RÉSULTATS (MIMOD puis Régions).
  - Bandeaux couleur (Cyan, Jaune, Rouge) -> AVIS.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pdfplumber

from prod_pipeline.colors import (
    classify_color, is_banner_rect, is_black, is_red, is_cyan, is_yellow,
    ROLE_NOIR, ROLE_ROUGE, ROLE_JAUNE, ROLE_CYAN
)

log = logging.getLogger("scrapperbf.macro_splitter")

_REGION_KW_RE = re.compile(
    r"\b(r[ée]gions?|conseils?\s+r[ée]gionaux|conseils?\s+r[ée]gional|communes?|mairies?|collectivit[ée]s?\s+territoriales?)\b",
    re.IGNORECASE
)
_MIMOD_KW_RE = re.compile(
    r"\b(minist[èe]res?|institutions?|mimod|ma[îi]trises?\s+d.ouvrages?)\b",
    re.IGNORECASE
)


def _clean_slug(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    name = re.sub(r'\s+', '_', name)
    return name


def parse_sommaire_page2(pdf_path: str, numero_bulletin: str) -> List[Dict[str, Any]]:
    """
    Stratégie A : Analyse déterministe de la table des matières en page 2.
    """
    sections = []
    num_clean = _clean_slug(numero_bulletin)

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if total_pages < 2:
            return []

        p2 = pdf.pages[1]
        w, h = p2.width, p2.height

        # 1. Extraction ciblée de la colonne droite pour isoler le sommaire
        try:
            right_crop = p2.crop((w * 0.35, 0, w, h))
            raw_text = right_crop.extract_text() or ""
        except Exception:
            raw_text = ""

        # Si le crop droit ne contient pas assez de texte, se rabattre sur la page entière
        if len(raw_text.strip()) < 50 or "p." not in raw_text.lower():
            raw_text = p2.extract_text() or ""

        if not raw_text:
            return []

        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

        current_context = None      # "Resultats" ou "Avis"
        current_category = None     # "MIMOD" ou "Region"
        current_name_parts = []

        # Motif de détection d'une ligne de sommaire avec numéro de page
        # Évite strictement "B.P." (adresse postale)
        p_pattern = re.compile(
            r'(.*?)\.?\b(?<!B\.)P\.\s*(\d+)(?:\s*[àa-]\s*(\d+))?',
            re.IGNORECASE
        )

        for line in lines:
            upper = line.upper()

            # Mise à jour du macro-contexte
            if "RESULTAT" in upper or "DEPOUILLEMENT" in upper or "DÉPOUILLEMENT" in upper:
                current_context = "Resultats"
                current_category = "MIMOD" # Par défaut dans les résultats, MIMOD vient en 1er
            elif "AVIS" in upper and "AVIS IMPORTANT" not in upper and "AVIS DE" not in upper:
                current_context = "Avis"
                current_category = "MIMOD" # Par défaut dans les avis, MIMOD vient en 1er

            # Détection de changement de catégorie (MIMOD vs Région)
            if _MIMOD_KW_RE.search(line):
                current_category = "MIMOD"
            elif _REGION_KW_RE.search(line) and "avenue" not in line.lower() and "bp" not in line.lower():
                current_category = "Region"

            # Recherche du numéro de page
            m = p_pattern.search(line)
            if m:
                label_part = re.sub(r'\.+$', '', m.group(1)).strip()
                page_start = int(m.group(2))
                page_end = int(m.group(3)) if m.group(3) else None

                if label_part:
                    current_name_parts.append(label_part)
                full_label = " ".join(current_name_parts)

                # Détection fine de la sous-famille
                type_marche = ""
                if re.search(r'fourniture', full_label, re.I):
                    type_marche = "fournitures_et_services_courants"
                elif re.search(r'travaux', full_label, re.I):
                    type_marche = "travaux"
                elif re.search(r'intellectuelle|consultant', full_label, re.I):
                    type_marche = "prestations_intellectuelles"

                # Construction du nom normalisé de la section
                ctx = current_context or "Section"
                cat = current_category or "MIMOD"

                if ctx == "Avis" and type_marche:
                    name = f"{num_clean}-Avis-{cat}-{type_marche}"
                elif ctx == "Resultats":
                    name = f"{num_clean}-Resultats-{cat}"
                else:
                    slug_lbl = _clean_slug(re.sub(r"^[-•*:]\s*", "", full_label)[:35])
                    name = f"{num_clean}-{ctx}-{cat}-{slug_lbl}" if slug_lbl else f"{num_clean}-{ctx}-{cat}"

                sections.append({
                    "name": name,
                    "context": ctx,
                    "category": cat,
                    "type_marche": type_marche,
                    "page_printed_start": page_start,
                    "page_printed_end": page_end,
                    "strategy": "SOMMAIRE"
                })
                current_name_parts = []
            else:
                # Accumulation de morceaux de titres multi-lignes
                clean_l = line.strip()
                if clean_l and not re.search(r'sommaire|quotidien|bulletin|information importante|http', clean_l, re.I):
                    current_name_parts.append(clean_l)

    return sections


def calibrate_and_bound_sections(
    sections: List[Dict[str, Any]],
    total_pages: int,
    delta: int = -1
) -> List[Dict[str, Any]]:
    """
    Calibre les indices 0-based de début et de fin de chaque section
    à partir des pages imprimées du sommaire.
    """
    if not sections:
        return []

    # Trier par page imprimée croissante
    valid_secs = [s for s in sections if s.get("page_printed_start")]
    valid_secs.sort(key=lambda s: s["page_printed_start"])

    for s in valid_secs:
        s["start_idx"] = max(0, min(total_pages - 1, s["page_printed_start"] + delta))

    for i in range(len(valid_secs)):
        sec = valid_secs[i]
        # Si une fin explicite était indiquée dans le sommaire (ex: P. 3 à 130)
        if sec.get("page_printed_end"):
            sec["end_idx"] = max(sec["start_idx"], min(total_pages - 1, sec["page_printed_end"] + delta))
        else:
            # Sinon la section s'arrête juste avant le début de la section suivante
            if i + 1 < len(valid_secs):
                nxt_start = valid_secs[i + 1]["start_idx"]
                sec["end_idx"] = max(sec["start_idx"], nxt_start - 1)
            else:
                sec["end_idx"] = total_pages - 1

    # Filtrer les intervalles cohérents
    out = [s for s in valid_secs if s["start_idx"] <= s["end_idx"]]
    return out


def fallback_visual_macro_split(
    pdf_path: str,
    numero_bulletin: str
) -> List[Dict[str, Any]]:
    """
    Stratégie B : Repli déterministe par balayage des marqueurs visuels
    (Barres noires pour Résultats, Bandeaux colorés pour Avis).
    """
    sections = []
    num_clean = _clean_slug(numero_bulletin)

    first_resultats_page = None
    first_region_resultats_page = None
    first_avis_page = None
    avis_category_pages = {}

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for pi in range(min(1, total_pages), total_pages):
            pg = pdf.pages[pi]
            w = pg.width
            txt = pg.extract_text() or ""

            # 1. Vérification des barres noires (Résultats)
            has_black_bar = False
            black_bar_is_region = False

            for r in pg.rects:
                if is_banner_rect(r, w, min_width_ratio=0.35, min_height=5.0):
                    col = r.get("non_stroking_color")
                    if is_black(col):
                        has_black_bar = True
                        try:
                            crop_txt = pg.crop((r["x0"], r["top"], r["x1"], r["bottom"] + 2)).extract_text() or ""
                            if _REGION_KW_RE.search(crop_txt):
                                black_bar_is_region = True
                        except Exception:
                            pass

            if has_black_bar:
                if first_resultats_page is None and first_avis_page is None:
                    first_resultats_page = pi
                if black_bar_is_region and first_region_resultats_page is None and first_avis_page is None:
                    first_region_resultats_page = pi

            # 2. Vérification des bandeaux couleur (Avis)
            has_avis_banners = False
            for r in pg.rects:
                if is_banner_rect(r, w, min_width_ratio=0.25, min_height=5.0):
                    col = r.get("non_stroking_color")
                    if is_red(col) or is_cyan(col) or is_yellow(col):
                        has_avis_banners = True
                        if is_red(col):
                            try:
                                cat_txt = pg.crop((r["x0"], r["top"], r["x1"], r["bottom"] + 2)).extract_text() or ""
                                if "fourniture" in cat_txt.lower():
                                    avis_category_pages.setdefault("fournitures_et_services_courants", pi)
                                elif "travaux" in cat_txt.lower():
                                    avis_category_pages.setdefault("travaux", pi)
                                elif "intellectuelle" in cat_txt.lower():
                                    avis_category_pages.setdefault("prestations_intellectuelles", pi)
                            except Exception:
                                pass

            if has_avis_banners and first_avis_page is None:
                first_avis_page = pi

    # Assemblage des sections détectées visuellement
    if first_resultats_page is not None:
        res_end = (first_avis_page - 1) if first_avis_page else (total_pages - 1)
        if first_region_resultats_page and first_region_resultats_page > first_resultats_page:
            sections.append({
                "name": f"{num_clean}-Resultats-MIMOD",
                "context": "Resultats",
                "category": "MIMOD",
                "start_idx": first_resultats_page,
                "end_idx": first_region_resultats_page - 1,
                "strategy": "VISUAL_FALLBACK"
            })
            sections.append({
                "name": f"{num_clean}-Resultats-Region",
                "context": "Resultats",
                "category": "Region",
                "start_idx": first_region_resultats_page,
                "end_idx": res_end,
                "strategy": "VISUAL_FALLBACK"
            })
        else:
            sections.append({
                "name": f"{num_clean}-Resultats-MIMOD",
                "context": "Resultats",
                "category": "MIMOD",
                "start_idx": first_resultats_page,
                "end_idx": res_end,
                "strategy": "VISUAL_FALLBACK"
            })

    if first_avis_page is not None:
        sections.append({
            "name": f"{num_clean}-Avis-Global",
            "context": "Avis",
            "category": "MIMOD",
            "start_idx": first_avis_page,
            "end_idx": total_pages - 1,
            "strategy": "VISUAL_FALLBACK"
        })

    return sections


def execute_macro_split(
    pdf_path: str,
    numero_bulletin: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Point d'entrée principal du Macro-Split :
    Tente la Stratégie A (Sommaire p.2), et bascule sur la Stratégie B si nécessaire.
    """
    with pdfplumber.open(pdf_path) as p:
        total_pages = len(p.pages)

    # 1. Stratégie A
    raw_sections = parse_sommaire_page2(pdf_path, numero_bulletin)
    sections = calibrate_and_bound_sections(raw_sections, total_pages=total_pages, delta=-1)

    strategy_used = "SOMMAIRE_P2"
    if not sections or len(sections) < 2:
        log.warning("Stratégie A (Sommaire) insuffisante (%d sections). Bascule sur Stratégie B.", len(sections))
        sections = fallback_visual_macro_split(pdf_path, numero_bulletin)
        strategy_used = "VISUAL_FALLBACK"

    # Détermination des bornes globales AVIS et RÉSULTATS
    res_start = min((s["start_idx"] for s in sections if s["context"] == "Resultats"), default=None)
    res_end = max((s["end_idx"] for s in sections if s["context"] == "Resultats"), default=None)
    avis_start = min((s["start_idx"] for s in sections if s["context"] == "Avis"), default=None)
    avis_end = max((s["end_idx"] for s in sections if s["context"] == "Avis"), default=None)

    meta = {
        "strategy": strategy_used,
        "total_sections": len(sections),
        "resultats_range": (res_start, res_end) if (res_start is not None and res_end is not None) else None,
        "avis_range": (avis_start, avis_end) if (avis_start is not None and avis_end is not None) else None,
        "total_pages": total_pages
    }

    return sections, meta
