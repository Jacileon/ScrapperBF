"""
prod_pipeline/colors.py — Charte couleur officielle DGCMEF avec marges de tolérance.

Définition colorimétrique et géométrique des marqueurs structurels :
1. NOIR (Cadre émetteur - Section Résultats) :
   - Ministères, institutions et collectivités territoriales.
   - Noir profond avec marge pour artefacts de compression ou rendu vectoriel.
2. ORANGE / OR (Séparateurs de lots - Section Résultats) :
   - Bandeaux de sous-division « Lot N : ... ».
3. ROUGE (Bandeau de Catégorie - Section Avis) :
   - « Fournitures et services courants », « Travaux », « Prestations intellectuelles ».
4. JAUNE (Bandeau d'Émetteur - Section Avis) :
   - Autorité contractante (ministère, commune, agence).
5. CYAN / BLEU (Bandeau d'Objet - Section Avis) :
   - Début d'un avis d'appel d'offres distinct.

Tous les espaces colorimétriques rencontrés dans les PDF sont supportés :
- Scalaire (Niveaux de gris : 0.0 à 1.0 ou 0 à 255)
- RGB (Triplets float 0.0-1.0 ou int 0-255)
- CMYK (Quadruplets float 0.0-1.0 ou int 0-100)
- Hexadécimal ('#000000', etc.)
"""

from typing import Any, Dict, List, Optional, Tuple, Union

# Rôles structurels
ROLE_NOIR = "NOIR"        # Émetteur Résultats (cadre noir)
ROLE_ORANGE = "ORANGE"    # Lot Résultats (bande orange)
ROLE_GRIS = "GRIS"        # Lot Résultats (bande grise)
ROLE_VERT = "VERT"        # Lot Résultats (bande verte)
ROLE_ROUGE = "ROUGE"      # Catégorie Avis
ROLE_JAUNE = "JAUNE"      # Émetteur Avis ou Lot Résultats (bande jaune)
ROLE_CYAN = "CYAN"        # Objet Avis (début d'annonce)


def normalize_to_rgb(color: Any) -> Optional[Tuple[float, float, float]]:
    """
    Normalise n'importe quelle représentation de couleur en triplet RGB (r, g, b)
    où chaque canal est un flottant compris entre 0.0 et 1.0.
    """
    if color is None:
        return None

    # 1. Scalaire = Niveaux de gris
    if isinstance(color, (int, float)):
        val = float(color)
        if val > 1.0:
            val = max(0.0, min(1.0, val / 255.0))
        else:
            val = max(0.0, min(1.0, val))
        return (val, val, val)

    # 2. Chaîne hexadécimale (ex: '#00B0F0')
    if isinstance(color, str):
        c = color.strip().lstrip("#")
        if len(c) == 6:
            try:
                r = int(c[0:2], 16) / 255.0
                g = int(c[2:4], 16) / 255.0
                b = int(c[4:6], 16) / 255.0
                return (r, g, b)
            except ValueError:
                return None
        return None

    # 3. Liste ou tuple
    if isinstance(color, (list, tuple)):
        # Grayscale dans un tuple (1 valeur)
        if len(color) == 1:
            return normalize_to_rgb(color[0])

        # RGB (3 valeurs)
        if len(color) == 3:
            try:
                vals = [float(v) for v in color]
            except (ValueError, TypeError):
                return None
            # Si les valeurs sont sur 0-255
            if any(v > 1.0 for v in vals):
                return (
                    max(0.0, min(1.0, vals[0] / 255.0)),
                    max(0.0, min(1.0, vals[1] / 255.0)),
                    max(0.0, min(1.0, vals[2] / 255.0)),
                )
            return (
                max(0.0, min(1.0, vals[0])),
                max(0.0, min(1.0, vals[1])),
                max(0.0, min(1.0, vals[2])),
            )

        # CMYK (4 valeurs) -> Conversion en RGB
        if len(color) == 4:
            try:
                c, m, y, k = [float(v) for v in color]
            except (ValueError, TypeError):
                return None
            # Si les valeurs sont sur 0-100 ou 0-255
            if any(v > 1.0 for v in (c, m, y, k)):
                scale = 255.0 if any(v > 100.0 for v in (c, m, y, k)) else 100.0
                c, m, y, k = c / scale, m / scale, y / scale, k / scale
            
            c = max(0.0, min(1.0, c))
            m = max(0.0, min(1.0, m))
            y = max(0.0, min(1.0, y))
            k = max(0.0, min(1.0, k))

            r = (1.0 - c) * (1.0 - k)
            g = (1.0 - m) * (1.0 - k)
            b = (1.0 - y) * (1.0 - k)
            return (r, g, b)

    return None


def is_black(color: Any, threshold: float = 0.18) -> bool:
    """
    Détecte le NOIR (Cadre d'émetteur de résultats).
    Tolérance par défaut : intensité globale < 0.18 (RGB < 46 sur 255).
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return (r < threshold and g < threshold and b < threshold) or ((r + g + b) / 3.0 < threshold)


def is_orange(color: Any) -> bool:
    """
    Détecte l'ORANGE / OR (Bandeau de lot dans les résultats).
    Tolérance calibrée : Rouge dominant (> 0.70), Vert moyen (0.35 à 0.95), Bleu bas (< 0.70).
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return (r > 0.70 and 0.35 <= g <= 0.95 and b < 0.70 and (r - b) >= 0.18)


def is_red(color: Any) -> bool:
    """
    Détecte le ROUGE (Bandeau Catégorie de la section Avis).
    Tolérance calibrée : Rouge dominant (> 0.65), Vert bas (< 0.55), Bleu bas (< 0.55).
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return (r > 0.65 and g < 0.55 and b < 0.55 and (r - g) >= 0.18 and (r - b) >= 0.18)


def is_yellow(color: Any) -> bool:
    """
    Détecte le JAUNE (Bandeau Émetteur de la section Avis ou Lot Résultats).
    Tolérance calibrée : Rouge et Vert élevés (> 0.65 / 0.60), Bleu faible (< 0.55).
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return (r > 0.65 and g > 0.60 and b < 0.55 and (r - b) >= 0.20 and (g - b) >= 0.20)


def is_grey(color: Any) -> bool:
    """
    Détecte le GRIS (Bandeau / petite bande de lot ou sous-section dans les résultats).
    Couvre les niveaux de gris scalaires (0.35..0.965) et triplets gris/gris-bleuté neutres.
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    mean = (r + g + b) / 3.0
    spread = max(r, g, b) - min(r, g, b)
    return (0.35 <= mean <= 0.965) and (spread <= 0.08)


def is_green(color: Any) -> bool:
    """
    Détecte le VERT (Bandeau / petite bande de lot dans les résultats : vert franc, sauge, pastel, menthe).
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    if min(r, g, b) > 0.96:
        return False
    return (g > 0.35 and (g - r) >= 0.03 and (g - b) >= 0.03)


def classify_lot_color(color: Any) -> Optional[str]:
    """Identifie la couleur d'une bande de lot Résultats ('ORANGE', 'JAUNE', 'VERT', 'GRIS') ou None."""
    if is_yellow(color):
        return ROLE_JAUNE
    if is_green(color):
        return ROLE_VERT
    if is_orange(color):
        return ROLE_ORANGE
    if is_grey(color):
        return ROLE_GRIS
    return None


def is_cyan(color: Any) -> bool:
    """
    Détecte le CYAN / BLEU CLAIR / BLEU PUR (Bandeau Objet / Début d'annonce Avis).
    Tolérance calibrée :
      - Soit Cyan / Bleu clair : r < 0.65, g > 0.50, b > 0.50, (b - r) >= 0.15
      - Soit Bleu soutenu / pur : r < 0.50, g < 0.60, b > 0.60
    """
    rgb = normalize_to_rgb(color)
    if rgb is None:
        return False
    r, g, b = rgb
    is_pure_cyan = (r < 0.65 and g > 0.45 and b > 0.45 and (b - r) >= 0.15)
    is_deep_blue = (r < 0.50 and g < 0.60 and b > 0.55 and (b - r) >= 0.20)
    return is_pure_cyan or is_deep_blue


def classify_color(color: Any) -> Optional[str]:
    """
    Assigne le rôle structurel selon la charte couleur DGCMEF avec marges de tolérance.
    Retourne 'NOIR', 'ORANGE', 'ROUGE', 'JAUNE', 'CYAN', ou None.
    """
    if is_black(color):
        return ROLE_NOIR
    if is_red(color):
        return ROLE_ROUGE
    if is_yellow(color):
        return ROLE_JAUNE
    if is_cyan(color):
        return ROLE_CYAN
    if is_orange(color):
        return ROLE_ORANGE
    return None


def is_valid_banner_geometry(
    rect: Dict[str, Any],
    page_width: float,
    min_width_ratio: float = 0.25,
    min_height: float = 4.0,
    max_height: float = 90.0
) -> bool:
    """
    Vérifie si les dimensions d'un rectangle correspondent géométriquement
    à un bandeau de titre / cadre (en éliminant puces, bordures fines et cadres de pleine page).
    """
    w = rect.get("width", 0)
    h = rect.get("height", 0)
    return (w >= page_width * min_width_ratio) and (min_height <= h <= max_height)


is_banner_rect = is_valid_banner_geometry


def dedup_rectangles(rects: List[Dict[str, Any]], y_tolerance: float = 6.0) -> List[Dict[str, Any]]:
    """
    Déduplique les rectangles superposés (souvent émis en double par les générateurs
    PDF pour le remplissage et le contour) en regroupant par position Y arrondie.
    """
    seen = set()
    out = []
    for r in sorted(rects, key=lambda x: x.get("top", 0)):
        key = round(r.get("top", 0) / y_tolerance)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
