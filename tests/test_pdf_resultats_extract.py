"""Tests hors-ligne des fonctions pures du segmenteur RÉSULTATS (sans PDF)."""
from pdf_resultats_extract import (
    is_black, is_orange, is_grey, is_green, is_yellow,
    is_lot_band_color, classify_lot_band_color,
    find_lot_markers, _bars_and_lots, detect_macro_section,
    _EMETTEUR_REGION_RE, MACRO_MINISTERES, MACRO_REGIONS,
)


def test_is_black_accepts_scalar_and_triplet():
    assert is_black(0.0) is True
    assert is_black((0, 0, 0)) is True
    assert is_black((0.05, 0.05, 0.05)) is True


def test_is_black_rejects_non_black():
    assert is_black(0.5) is False
    assert is_black((1, 1, 1)) is False
    assert is_black(None) is False


def test_is_orange_detects_lot_bands():
    assert is_orange((0.957, 0.69, 0.514)) is True
    assert is_orange((1.0, 0.851, 0.4)) is True


def test_is_orange_rejects_others():
    assert is_orange((0, 0, 0)) is False
    assert is_orange((1, 1, 1)) is False
    assert is_orange(0.8) is False
    assert is_orange(None) is False


def test_macro_detection_ministeres():
    t = "RESULTATS PROVISOIRES DES MINISTERES, INSTITUTIONS ET MAITRISES D'OUVRAGES DELEGUEES"
    assert detect_macro_section(t, None) == MACRO_MINISTERES


def test_macro_detection_regions():
    assert detect_macro_section("RESULTATS PROVISOIRES DES REGIONS", MACRO_MINISTERES) == MACRO_REGIONS


def test_macro_detection_ignores_sommaire_and_keeps_current():
    # La page Sommaire cite les deux sections : on ne doit pas basculer.
    t = "Sommaire\nRESULTATS PROVISOIRES DES MINISTERES ... DES REGIONS ..."
    assert detect_macro_section(t, MACRO_MINISTERES) == MACRO_MINISTERES


def test_macro_detection_no_header_keeps_current():
    assert detect_macro_section("Un texte quelconque sans en-tête", MACRO_REGIONS) == MACRO_REGIONS


def test_emetteur_region_regex():
    assert _EMETTEUR_REGION_RE.match("REGION DE BANKUI")
    assert _EMETTEUR_REGION_RE.match("COMMUNE DE OUAGADOUGOU")
    assert _EMETTEUR_REGION_RE.match("CONSEIL REGIONAL DU SAHEL")
    assert not _EMETTEUR_REGION_RE.match("MINISTERE DE L'ECONOMIE ET DES FINANCES")
    assert not _EMETTEUR_REGION_RE.match("SOCIETE NATIONALE DE GESTION")


def test_is_grey_green_yellow_lot_bands():
    # Bandes grises (scalaires & triplets)
    assert is_grey(0.851) is True
    assert is_grey((0.749, 0.749, 0.749)) is True
    assert is_grey((0.835, 0.863, 0.894)) is True
    assert is_grey((0.0, 0.0, 0.0)) is False
    assert is_grey((1.0, 1.0, 1.0)) is False

    # Bandes vertes
    assert is_green((0.573, 0.816, 0.314)) is True
    assert is_green((0.886, 0.937, 0.851)) is True
    assert is_green((0.839, 0.89, 0.737)) is True
    assert is_green((1.0, 1.0, 1.0)) is False

    # Bandes jaunes
    assert is_yellow((1.0, 1.0, 0.0)) is True
    assert is_yellow((1.0, 0.949, 0.8)) is True
    assert is_yellow((1.0, 1.0, 1.0)) is False

    # Classification globale des bandes de lots
    assert classify_lot_band_color((1.0, 1.0, 0.0)) == "jaune"
    assert classify_lot_band_color((0.573, 0.816, 0.314)) == "verte"
    assert classify_lot_band_color((0.749, 0.749, 0.749)) == "grise"
    assert classify_lot_band_color((0.957, 0.69, 0.514)) == "orange"
    assert is_lot_band_color(0.851) is True
    assert is_lot_band_color((0.0, 0.0, 0.0)) is False


def test_find_lot_markers_variants():
    txt = "Préambule\nLOT1 : Batterie\nLot 2. Entretien\nLOT 3\nLot Unique : Support"
    lots = find_lot_markers(txt)
    assert len(lots) == 4
    assert lots[0] == "Lot 1 : Batterie"
    assert lots[1] == "Lot 2 : Entretien"
    assert lots[2] == "Lot 3"
    assert lots[3] == "Lot Unique : Support"


def test_bars_and_lots_detects_petite_bande_jaune_grise_verte():
    class FakeCrop:
        def __init__(self, text):
            self._text = text
        def extract_text(self):
            return self._text

    class FakePage:
        width = 600.0
        height = 800.0
        curves = []
        rects = [
            {"x0": 30, "top": 50, "x1": 570, "bottom": 62, "width": 540, "height": 12, "non_stroking_color": (0.0, 0.0, 0.0)},
            {"x0": 200, "top": 120, "x1": 370, "bottom": 129, "width": 170, "height": 9, "non_stroking_color": (1.0, 1.0, 0.0)},
            {"x0": 30, "top": 220, "x1": 570, "bottom": 229, "width": 540, "height": 9, "non_stroking_color": (0.573, 0.816, 0.314)},
            {"x0": 30, "top": 320, "x1": 570, "bottom": 329, "width": 540, "height": 9, "non_stroking_color": 0.851},
            {"x0": 150, "top": 340, "x1": 250, "bottom": 349, "width": 100, "height": 9, "non_stroking_color": 0.851},
        ]
        def crop(self, bbox):
            y = bbox[1]
            mapping = {
                50: "MINISTERE DE L'ECONOMIE",
                120: "LOT N°1 : Comptoir de vente",
                220: "Lot 2 : Cloture grillage",
                320: "Lot 3 : Extincteurs",
                340: "Observations",
            }
            return FakeCrop(mapping.get(y, ""))

    bars, lots = _bars_and_lots(FakePage(), 600.0)
    assert len(bars) == 1
    assert bars[0]["text"] == "MINISTERE DE L'ECONOMIE"
    assert len(lots) == 3
    assert [l["color"] for l in lots] == ["jaune", "verte", "grise"]
    assert lots[0]["width_ratio"] < 0.35
