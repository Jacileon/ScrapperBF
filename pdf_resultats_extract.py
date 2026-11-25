"""
Segmentation de la section RÉSULTATS d'un Quotidien DGCMEF.

Structure (confirmée visuellement sur les bulletins réels) :
  - Deux macro-sections, dans l'ordre :
      1) "RÉSULTATS PROVISOIRES DES MINISTÈRES, INSTITUTIONS ET MAÎTRISES
         D'OUVRAGES DÉLÉGUÉES"
      2) "RÉSULTATS PROVISOIRES DES RÉGIONS" (collectivités territoriales)
  - Pour CHAQUE émetteur (ex. « MINISTERE DE L'ECONOMIE ET DES FINANCES »), une
    BARRE NOIRE pleine largeur, texte blanc : c'est le « cadre noir » qui ouvre
    le tableau de cet émetteur. La barre noire suivante ouvre l'émetteur suivant.
  - À l'intérieur d'un tableau, des BANDES ORANGE « Lot N : … » séparent les lots.
  - Le tableau s'étale souvent sur plusieurs pages ; il n'y a pas de répétition
    d'en-tête -> on ne coupe PAS au changement de page, seulement aux barres noires.

Ce module est 100 % déterministe (pdfplumber, pas de LLM) : il découpe chaque
unité-émetteur (barre noire -> barre noire suivante), compte les lots détectés,
et produit un `flat_text` prêt à être envoyé au LLM (voir resultats_llm.py) pour
structurer le contenu multi-colonnes du tableau.

Les fonctions de bas niveau (is_black, is_orange, detect_macro_section) sont
pures et testées hors-ligne.
"""

import re
import sys
import json
from pathlib import Path
from typing import Optional

MACRO_MINISTERES = "MINISTERES"
MACRO_REGIONS = "REGIONS"

_MINISTERES_RE = re.compile(r"MINIST[ÈE]RES?|INSTITUTIONS|MA[ÎI]TRISES?\s+D.OUVRAGES?", re.I)
_REGIONS_RE = re.compile(r"R[ÉE]GIONS?|COLLECTIVIT[ÉE]S?\s+TERRITORIALES?", re.I)
_RESULTATS_HDR_RE = re.compile(r"R[ÉE]SULTATS\s+PROVISOIRES", re.I)
_LOT_RE = re.compile(r"^\s*lot\s*(?:n\s*[°o]\s*)?(?:\d{1,3}|unique)\b", re.I)
_LOT_NUM_BANNER_RE = re.compile(
    r"^\s*(\d{1,2})\s*[:.]\s*(?:Acquisition|Fourniture|Travaux|Entretien|R[ée]fection|"
    r"Prestation|Confection|Nettoyage|Maintenance|R[ée]alisation|Achat|Construction|"
    r"[ÉE]quipement|Gardiennage|Location|Suivi)",
    re.I,
)
# Détection des lots par le TEXTE (complétée par les bandes orange, grises, vertes, jaunes) :
# « Lot 1 : … », « LOT N°2 : … », « Lot 1. … », « LOT 3 », « Lot Unique : … ».
_LOT_TEXT_RE = re.compile(
    r"(?im)^\s*lot\s*(?:n\s*[°o]\s*)?(\d{1,3}|unique)\s*(?:[:.\-–]\s*([^\n]{0,120})|\s*$)"
)


def _normalize_lot_num(raw: str) -> str:
    s = (raw or "").strip()
    return "Unique" if s.lower() == "unique" else s


def find_lot_markers(flat_text: str) -> list:
    """Repère les lots dans le texte aplati. Retourne une liste de libellés
    courts « Lot N : … », dédupliquée par numéro (ordre d'apparition)."""
    out, seen = [], set()
    for m in _LOT_TEXT_RE.finditer(flat_text or ""):
        num = _normalize_lot_num(m.group(1))
        if num in seen:
            continue
        seen.add(num)
        title = re.sub(r"\s+", " ", (m.group(2) or "")).strip()
        label = f"Lot {num} : {title}" if title else f"Lot {num}"
        out.append(label)
    return out
# Les en-têtes décoratifs de section ne sont pas du texte sélectionnable, mais
# la 2e macro-section (collectivités) se trahit par le nom de l'émetteur :
# « RÉGION DE … », « COMMUNE DE … », « CONSEIL RÉGIONAL … », etc.
_EMETTEUR_REGION_RE = re.compile(
    r"^(R[ÉE]GION|CONSEIL\s+R[ÉE]GIONAL|COMMUNE|MAIRIE|PROVINCE|CONSEIL\s+MUNICIPAL)\b", re.I)


def _to_rgb(color) -> Optional[tuple]:
    """Normalise scalaire, 1-tuple, RGB (0-1 ou 0-255) ou CMYK en triplet (r, g, b) dans [0, 1]."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        v = float(color)
        if v > 1.0:
            v = v / 255.0
        v = max(0.0, min(1.0, v))
        return (v, v, v)
    if isinstance(color, (list, tuple)):
        if len(color) == 1:
            return _to_rgb(color[0])
        if len(color) == 3:
            try:
                vals = [float(x) for x in color]
            except (TypeError, ValueError):
                return None
            if any(x > 1.0 for x in vals):
                vals = [x / 255.0 for x in vals]
            return tuple(max(0.0, min(1.0, x)) for x in vals)
        if len(color) == 4:
            try:
                c, m, y, k = [float(x) for x in color]
            except (TypeError, ValueError):
                return None
            if any(x > 1.0 for x in (c, m, y, k)):
                scale = 255.0 if any(x > 100.0 for x in (c, m, y, k)) else 100.0
                c, m, y, k = c / scale, m / scale, y / scale, k / scale
            c, m, y, k = (max(0.0, min(1.0, x)) for x in (c, m, y, k))
            return ((1.0 - c) * (1.0 - k), (1.0 - m) * (1.0 - k), (1.0 - y) * (1.0 - k))
    return None


def is_black(color) -> bool:
    """Rectangle à remplissage noir (barre d'émetteur). Accepte le gris scalaire
    0.0 comme les triplets (0,0,0)."""
    rgb = _to_rgb(color)
    if rgb is None:
        return False
    return all(v < 0.12 for v in rgb)


def is_orange(color) -> bool:
    """Bande orange/or/pêche des séparateurs de lot."""
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return False
    rgb = _to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return r > 0.9 and 0.5 < g < 0.93 and b < 0.66


def is_yellow(color) -> bool:
    """Bande jaune (y compris petite bande jaune « LOT N°… ») des séparateurs de lot."""
    rgb = _to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return r >= 0.70 and g >= 0.65 and b < 0.88 and (r - b) >= 0.15 and (g - b) >= 0.12


def is_green(color) -> bool:
    """Bande verte (vert franc, sauge, pastel, menthe) des séparateurs de lot."""
    rgb = _to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    if min(r, g, b) > 0.96:
        return False
    return g > 0.35 and (g - r) >= 0.03 and (g - b) >= 0.03


def is_grey(color) -> bool:
    """Bande grise (scalaire ou RGB neutre / gris-bleuté) des séparateurs de lot."""
    rgb = _to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    mean = (r + g + b) / 3.0
    spread = max(r, g, b) - min(r, g, b)
    return (0.35 <= mean <= 0.965) and (spread <= 0.08)


def classify_lot_band_color(color) -> Optional[str]:
    """Retourne la couleur normalisée d'une bande de lot ('orange', 'jaune', 'verte', 'grise', 'autre') ou None."""
    rgb = _to_rgb(color)
    if rgb is None:
        return None
    # Exclure noir (émetteur) et blanc pur (fond de cellule)
    if is_black(color) or min(rgb) > 0.965:
        return None
    if is_orange(color):
        return "orange"
    if is_yellow(color):
        return "jaune"
    if is_green(color):
        return "verte"
    if is_grey(color):
        return "grise"
    # Autres teintes pastel utilisées occasionnellement pour des lots (bleu clair, lavande/rose)
    r, g, b = rgb
    if max(rgb) > 0.55 and (max(rgb) - min(rgb)) >= 0.06:
        return "autre"
    return None


def is_lot_band_color(color) -> bool:
    """Vrai si la couleur correspond à une bande de lot (orange, grise, verte, jaune ou pastel)."""
    return classify_lot_band_color(color) is not None


def detect_macro_section(page_text: str, current: Optional[str]) -> Optional[str]:
    """Met à jour la macro-section courante d'après l'en-tête décoratif
    « RÉSULTATS PROVISOIRES DES … » de la page (sinon garde l'état courant).

    On ignore la page Sommaire (table des matières), qui cite les DEUX sections
    et fausserait la détection."""
    if not page_text:
        return current
    if re.search(r"\bsommaire\b", page_text[:200], re.I):
        return current
    head = page_text[:400]
    if not _RESULTATS_HDR_RE.search(head):
        return current
    has_min = bool(_MINISTERES_RE.search(head))
    has_reg = bool(_REGIONS_RE.search(head))
    if has_min and not has_reg:
        return MACRO_MINISTERES
    if has_reg and not has_min:
        return MACRO_REGIONS
    return current


def _crop_text(page, rect, pad_bottom: float = 1.0) -> str:
    try:
        c = page.crop((rect["x0"], rect["top"], rect["x1"], rect["bottom"] + pad_bottom))
        return " ".join((c.extract_text() or "").split())
    except Exception:
        return ""


def _bars_and_lots(page, width: float):
    """Retourne (barres_noires, bandes_lot) dédupliquées pour une page.

    Détecte :
      - Barres noires d'émetteur (largeur >= 45% de la page, hauteur 6..60 px)
      - Bandes de lots pleine largeur OU petites bandes (largeur >= 14% de la page,
        hauteur 6..90 px) en orange, gris, vert, jaune ou teinte pastel.
    """
    bars, lots = [], []
    shapes = list(getattr(page, "rects", []) or []) + list(getattr(page, "curves", []) or [])
    min_bar_w = width * 0.45
    min_lot_w = width * 0.14

    for r in shapes:
        h = r.get("height", 0)
        w = r.get("width", 0)
        if h < 6 or h > 90 or w < min_lot_w:
            continue
        col = r.get("non_stroking_color")
        if is_black(col):
            if w >= min_bar_w and h <= 60:
                bars.append((r, "noir"))
        else:
            lot_col = classify_lot_band_color(col)
            if lot_col:
                lots.append((r, lot_col))

    def dedup(items, want_lot):
        seen, out = set(), []
        for r, col_kind in sorted(items, key=lambda x: x[0]["top"]):
            txt = _crop_text(page, r)
            if want_lot:
                is_lot = bool(_LOT_RE.match(txt))
                if not is_lot:
                    is_lot = (r.get("width", 0) >= width * 0.55 and r.get("height", 0) <= 24
                              and bool(_LOT_NUM_BANNER_RE.match(txt)))
                if not is_lot:
                    continue
            else:
                if len(txt) < 4:
                    continue
            key = (round(r["top"] / 4), txt[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "top": r["top"],
                "text": txt,
                "color": col_kind,
                "width_ratio": round(r.get("width", 0) / width, 2) if width else 0.0,
            })
        return out

    return dedup(bars, False), dedup(lots, True)


def _text_between(pages, p0, top0, p1, top1) -> str:
    """Texte entre deux ancres (page, y), barres noires comprises exclues."""
    parts = []
    for pi in range(p0, p1 + 1):
        pg = pages[pi]
        top = top0 + 10 if pi == p0 else 0
        bottom = top1 if pi == p1 else pg.height
        if bottom <= top:
            continue
        try:
            parts.append(pg.crop((0, top, pg.width, bottom)).extract_text() or "")
        except Exception:
            pass
    return "\n".join(p for p in parts if p).strip()


def segment_resultats(path: str, numero: Optional[str] = None,
                      label: Optional[str] = None, page_range=None) -> list:
    """Découpe la section RÉSULTATS en unités-émetteur (une par barre noire).

    Chaque unité : {emetteur, macro_section, page_debut, page_fin,
    nb_lots_detectes, lots, flat_text, + provenance}.

    `page_range` (tuple 0-based inclusif (start,end), ou None) restreint la
    collecte à la zone RÉSULTATS (voir section_split.split_sections)."""
    import pdfplumber

    if numero is None or label is None:
        name = Path(path).stem.replace("_", " ")
        m = re.search(r"quotidien\s*n?[°o]?\s*(\d{3,4})\s*(bis)?", name, re.I)
        core = (m.group(1) + ("bis" if m.group(2) else "")) if m else Path(path).stem
        numero = numero or ("N" + core)
        label = label or ("Quotidien N°" + core)

    pdf = pdfplumber.open(path)
    pages = pdf.pages
    if not pages:
        pdf.close()
        return []
    start_page = max(0, page_range[0]) if page_range else 0
    last_page = min(page_range[1], len(pages) - 1) if page_range else len(pages) - 1
    if start_page > last_page:
        pdf.close()
        return []

    # 1) Collecte des barres noires (émetteurs) et des lots, page par page.
    bars = []   # {page, top, emetteur}
    lots = []   # {page, top, text, color, width_ratio}
    for pi, pg in enumerate(pages):
        if page_range is not None and not (start_page <= pi <= last_page):
            continue
        b, l = _bars_and_lots(pg, pg.width)
        for r in b:
            bars.append({"page": pi, "top": r["top"], "emetteur": r["text"]})
        for r in l:
            lots.append({
                "page": pi,
                "top": r["top"],
                "text": r["text"],
                "color": r.get("color", "orange"),
                "width_ratio": r.get("width_ratio", 0.0),
            })

    # Macro-section : ministères d'abord, puis bascule DÉFINITIVE sur les
    # collectivités dès le premier émetteur « RÉGION/COMMUNE/… » (les en-têtes
    # décoratifs ne sont pas du texte sélectionnable, le nom d'émetteur si).
    macro = MACRO_MINISTERES
    for bar in bars:
        if _EMETTEUR_REGION_RE.match(bar["emetteur"]):
            macro = MACRO_REGIONS
        bar["macro"] = macro

    # 2) Découpage : chaque barre -> unité jusqu'à la barre suivante.
    units = []
    for i, bar in enumerate(bars):
        nxt = bars[i + 1] if i + 1 < len(bars) else None
        p1 = nxt["page"] if nxt else last_page
        t1 = nxt["top"] if nxt else pages[p1].height
        flat = _text_between(pages, bar["page"], bar["top"], p1, t1)
        band_lots = [
            lo for lo in lots
            if (lo["page"], lo["top"]) > (bar["page"], bar["top"])
            and (nxt is None or (lo["page"], lo["top"]) < (nxt["page"], nxt["top"]))
        ]
        # Lots repérés par le TEXTE + complétés par les bandes colorées (orange, grise, verte, jaune).
        lots_texte = find_lot_markers(flat)
        merged_lots = list(lots_texte)
        seen_keys = set()
        for lt in merged_lots:
            m_k = re.search(r"lot\s*(?:n\s*[°o]\s*)?(\d{1,3}|unique)", lt, re.I)
            if m_k:
                seen_keys.add(m_k.group(1).lower())
        for lo in band_lots:
            txt_b = lo["text"]
            m_k = re.search(r"(?:lot\s*(?:n\s*[°o]\s*)?(\d{1,3}|unique)|^\s*(\d{1,2})\s*[:.])", txt_b, re.I)
            key_b = (m_k.group(1) or m_k.group(2)).lower() if m_k else txt_b[:30].lower()
            if key_b not in seen_keys:
                seen_keys.add(key_b)
                merged_lots.append(txt_b)

        nb_orange = sum(1 for lo in band_lots if lo.get("color") == "orange")
        nb_grises = sum(1 for lo in band_lots if lo.get("color") == "grise")
        nb_vertes = sum(1 for lo in band_lots if lo.get("color") == "verte")
        nb_jaunes = sum(1 for lo in band_lots if lo.get("color") == "jaune")
        nb = max(len(merged_lots), len(band_lots))
        units.append({
            "emetteur": bar["emetteur"],
            "macro_section": bar["macro"] or MACRO_MINISTERES,
            "page_debut": bar["page"] + 1,
            "page_fin": p1 + 1,
            "nb_lots_detectes": nb,
            "lots": merged_lots,
            "lot_bands": band_lots,
            "nb_lots_bandes_orange": nb_orange,
            "nb_lots_bandes_grises": nb_grises,
            "nb_lots_bandes_vertes": nb_vertes,
            "nb_lots_bandes_jaunes": nb_jaunes,
            "nb_lots_bandes_total": len(band_lots),
            "flat_text": flat,
            "_numero": numero, "_source_pdf": label, "_source": Path(path).name,
        })
    pdf.close()
    return units


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_resultats_extract.py <pdf> [<pdf> ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        units = segment_resultats(p)
        from collections import Counter
        by_macro = Counter(u["macro_section"] for u in units)
        tot_lots = sum(u["nb_lots_detectes"] for u in units)
        print(f"\n### {Path(p).name} : {len(units)} émetteurs, {tot_lots} lots "
              f"({dict(by_macro)})")
        for u in units[:8]:
            print(f"  [{u['macro_section'][:4]}] p{u['page_debut']}-{u['page_fin']} "
                  f"| {u['nb_lots_detectes']} lot(s) | {u['emetteur'][:60]}")
