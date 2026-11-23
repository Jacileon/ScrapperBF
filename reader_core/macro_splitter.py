"""
reader_core/macro_splitter.py — Étape 1 : Macro-Split AVIS vs RÉSULTATS

Double Stratégie de Partition :
  - Stratégie A (Prioritaire) : Lecture et analyse du tableau de sommaire imprimé (page 2),
    extraction des références de pages via regex r"(?<!b\.)\bp\.?\s*(\d{1,4})\b",
    calcul du décalage (delta calibration) entre numéros imprimés et index réels du PDF.
  - Stratégie B (Repli robuste) : Analyse géométrique et visuelle de chaque page :
    * Détection des barres noires / bannières transversales (spécifiques aux RÉSULTATS).
    * Détection des bandeaux colorés cyan/rouge/jaune (spécifiques aux AVIS).

Retour : Dictionnaire avec indices 0-based inclusifs :
  {
      "AVIS": (start_idx, end_idx) ou None,
      "RESULTATS": (start_idx, end_idx) ou None,
      "methode": "sommaire" | "marqueurs",
      "n_pages": int,
      "sommaire": {...} optionnel
  }
"""

import re
import logging
from typing import Optional, Dict, Tuple, List, Any
import pdfplumber

log = logging.getLogger("scrapperbf.macro_splitter")

# Regex conforme aux spécifications
_PAGE_REF = re.compile(r"(?<!b\.)\bp\.?\s*(\d{1,4})\b", re.IGNORECASE)
_CTX_RESULTATS = re.compile(r"r[ée]sultats|d[ée]pouillements", re.IGNORECASE)
_CTX_AVIS = re.compile(r"\bavis\b|appels?\s+d['’\s]*offres", re.IGNORECASE)

# Tolérance couleur pour la stratégie B (repli)
def is_black(c) -> bool:
    if c is None:
        return False
    if isinstance(c, (int, float)):
        return c < 0.15
    if isinstance(c, (list, tuple)):
        return all(x < 0.15 for x in c[:3])
    return False

def is_color_band(c) -> bool:
    """Détecte les bandeaux colorés (cyan, rouge, jaune, magenta)."""
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return False
    r, g, b = c[0], c[1], c[2]
    # Rouge (catégorie)
    if r > 0.70 and g < 0.45 and b < 0.45:
        return True
    # Jaune (autorité)
    if r > 0.70 and g > 0.70 and b < 0.50:
        return True
    # Cyan (objet / début d'avis)
    if r < 0.60 and g > 0.60 and b > 0.60:
        return True
    # Magenta / violet parfois utilisé
    if r > 0.60 and g < 0.45 and b > 0.60:
        return True
    return False


def _find_sommaire_text(pdf) -> Optional[str]:
    """Extrait le texte du sommaire en page 2 (ou 1 si décalage exceptionnel)."""
    if len(pdf.pages) < 2:
        return None
    # Priorité à la page d'index 1 (page 2 physique)
    for idx in (1, 0):
        t = pdf.pages[idx].extract_text() or ""
        if re.search(r"\bsommaire\b", t, re.IGNORECASE):
            return t
    return None


def parse_sommaire(text: str) -> List[Dict[str, Any]]:
    """
    Extrait les entrées du sommaire associées à leur contexte :
    [{"context": "RESULTATS" | "AVIS", "page": int}, ...]
    """
    ctx = None
    out = []
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _CTX_RESULTATS.search(line):
            ctx = "RESULTATS"
        elif _CTX_AVIS.search(line):
            ctx = "AVIS"

        for m in _PAGE_REF.finditer(line):
            out.append({"context": ctx, "page": int(m.group(1))})
    return out


def sommaire_section_pages(entries: List[Dict[str, Any]]) -> Dict[str, Tuple[int, int]]:
    """Détermine les numéros de pages imprimées (min, max) pour chaque section."""
    by_ctx = {}
    for e in entries:
        c = e.get("context")
        p = e.get("page")
        if c and p and p >= 1:
            by_ctx.setdefault(c, []).append(p)
    res = {}
    for c, pages in by_ctx.items():
        res[c] = (min(pages), max(pages))
    return res


def _calibrate_delta(pdf, secs: Dict[str, Tuple[int, int]]) -> int:
    """
    Calcule le décalage (delta) entre le numéro imprimé et l'index 0-based du PDF.
    Vérifie la présence d'un titre de section pour valider l'alignement.
    """
    ref_printed = secs.get("RESULTATS", (None,))[0] or secs.get("AVIS", (None,))[0]
    if not ref_printed:
        return 0
    # En pratique sur la DGCMEF : la page imprimée 3 correspond souvent à l'index 2 (delta = -1)
    for delta in (-1, 0, -2, 1):
        idx = ref_printed + delta
        if 0 <= idx < len(pdf.pages):
            txt = pdf.pages[idx].extract_text() or ""
            if _CTX_RESULTATS.search(txt) or _CTX_AVIS.search(txt):
                return delta
    return -1


def _sommaire_ranges(secs: Dict[str, Tuple[int, int]], delta: int, total_pages: int) -> Optional[Dict[str, Optional[Tuple[int, int]]]]:
    """Convertit les pages imprimées en plages d'indices 0-based sécurisées."""
    res_range = None
    avis_range = None

    if "RESULTATS" in secs:
        p0, p1 = secs["RESULTATS"]
        i0 = max(0, p0 + delta)
        i1 = min(total_pages - 1, p1 + delta)
        if i0 <= i1:
            res_range = (i0, i1)

    if "AVIS" in secs:
        p0, p1 = secs["AVIS"]
        i0 = max(0, p0 + delta)
        i1 = min(total_pages - 1, p1 + delta)
        if i0 <= i1:
            avis_range = (i0, i1)

    # Si les deux existent, s'assurer de la continuité et non-chevauchement aberrant
    if res_range and avis_range:
        if res_range[0] < avis_range[0]:
            # RÉSULTATS avant AVIS : ajuster la borne de fin des résultats
            res_range = (res_range[0], min(res_range[1], avis_range[0] - 1))
            # Les avis vont jusqu'à la fin du document si non borné
            avis_range = (avis_range[0], max(avis_range[1], total_pages - 1))
        return {"AVIS": avis_range, "RESULTATS": res_range}

    if res_range or avis_range:
        return {"AVIS": avis_range, "RESULTATS": res_range}

    return None


def _page_has_black_bar(page) -> bool:
    """Vérifie si la page comporte une barre noire transversale (en-tête résultats)."""
    w = page.width
    for r in page.rects:
        if r["width"] > w * 0.50 and r["height"] >= 6:
            if is_black(r.get("non_stroking_color")):
                return True
    return False


def _page_has_color_band(page) -> bool:
    """Vérifie si la page comporte un bandeau coloré (en-tête avis)."""
    w = page.width
    for r in page.rects:
        if r["width"] > w * 0.30 and r["height"] >= 6:
            if is_color_band(r.get("non_stroking_color")):
                return True
    return False


def _label_page(text: str, has_black_bar: bool, has_color_band: bool) -> str:
    """Attribue une étiquette à une page : 'R' (Résultats), 'A' (Avis), '.' (Incertain)."""
    if has_black_bar:
        return "R"
    if has_color_band:
        return "A"
    # Repli par mots-clés forts dans l'en-tête
    head = text[:350].lower()
    if "résultats des dépouillements" in head or "resultats des depouillements" in head:
        return "R"
    if "avis de demande de prix" in head or "avis d'appel d'offres" in head:
        return "A"
    return "."


def split_sections(pdf_path: str) -> Dict[str, Any]:
    """
    Fonction principale de Macro-Split.
    Partitionne le document en zones de pages AVIS et RÉSULTATS.
    """
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        if n == 0:
            return {"AVIS": None, "RESULTATS": None, "methode": "empty", "n_pages": 0}

        # -------------------------------------------------------------
        # Stratégie A : Lecture du Sommaire en page 2
        # -------------------------------------------------------------
        som_text = _find_sommaire_text(pdf)
        if som_text:
            entries = parse_sommaire(som_text)
            secs = sommaire_section_pages(entries)
            if secs:
                delta = _calibrate_delta(pdf, secs)
                ranges = _sommaire_ranges(secs, delta, n)
                if ranges and (ranges.get("AVIS") or ranges.get("RESULTATS")):
                    ranges.update(methode="sommaire", n_pages=n, sommaire=secs)
                    log.info("Macro-Split [Sommaire Page 2] : %d pages -> AVIS=%s, RÉSULTATS=%s",
                             n, ranges["AVIS"], ranges["RESULTATS"])
                    return ranges
            log.info("Macro-Split : sommaire présent mais incomplet -> passage en Stratégie B (Marqueurs)")

        # -------------------------------------------------------------
        # Stratégie B (Repli) : Détection des marqueurs visuels par page
        # -------------------------------------------------------------
        labels = []
        for pg in pdf.pages:
            has_b = _page_has_black_bar(pg)
            has_c = _page_has_color_band(pg)
            txt = pg.extract_text() or ""
            labels.append(_label_page(txt, has_b, has_c))

        # Calculer les plages à partir des séquences de labels 'R' et 'A'
        r_indices = [i for i, lbl in enumerate(labels) if lbl == "R"]
        a_indices = [i for i, lbl in enumerate(labels) if lbl == "A"]

        res_range = (min(r_indices), max(r_indices)) if r_indices else None
        avis_range = (min(a_indices), max(a_indices)) if a_indices else None

        # Si les résultats s'arrêtent là où les avis commencent
        if res_range and avis_range and res_range[0] < avis_range[0]:
            res_range = (res_range[0], min(res_range[1], avis_range[0] - 1))
            avis_range = (avis_range[0], n - 1)

        result = {
            "AVIS": avis_range,
            "RESULTATS": res_range,
            "methode": "marqueurs",
            "n_pages": n,
            "labels": "".join(labels),
        }
        log.info("Macro-Split [Marqueurs Visuels] : %d pages -> AVIS=%s, RÉSULTATS=%s",
                 n, result["AVIS"], result["RESULTATS"])
        return result
