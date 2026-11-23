"""
prod_pipeline/light_ocr.py — Module LightOCR & Détection de corruption textuelle.

Objectifs :
1. Détection automatique de la nécessité d'un OCR (`needs_ocr`) :
   - Pages scannées ou images sans couche de texte sélectionnable (taille < 40 caractères).
   - Polices PDF corrompues / CID fonts mal mappées (taux de charabia >= seuil).
   - Caractères de remplacement Unicode (ex: \\ufffd) anormaux.
2. Architecture de fournisseurs OCR légers et injectables (`build_ocr_provider`) :
   - Tesseract local (via PATH, pytesseract ou chemin direct TESSERACT_CMD).
   - Backend injectable pour les tests hors-ligne ou intégration d'APIs tierces.
   - Dégradation gracieuse : Si aucun binaire OCR n'est présent, le pipeline ne crashe JAMAIS ;
     il marque proprement le bloc avec `_alerte_humaine: True` et `_statut_ocr: "MANQUANT"`.
3. Rendu d'image mémoire haute définition via `pypdfium2` sans écriture disque superflue.
"""

import io
import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple

import pypdfium2 as pdfium

try:
    from judge import garbling_score
except ImportError:
    def garbling_score(text: str) -> float:
        """Calcul simplifié de charabia si judge n'est pas importable."""
        if not text or len(text.strip()) == 0:
            return 1.0
        cleaned = text.strip()
        vowels = set("aeiouyàâäéèêëîïôöûüAEIOUYÀÂÄÉÈÊËÎÏÔÖÛÜ")
        alpha_count = sum(1 for c in cleaned if c.isalpha())
        if alpha_count == 0:
            return 0.5
        vowel_count = sum(1 for c in cleaned if c in vowels)
        ratio_vowels = vowel_count / alpha_count
        weird_chars = sum(1 for c in cleaned if c in "\ufffd\x00\x01\x02\x03\x04\x05\x06\x07\x08")
        if ratio_vowels < 0.15 or ratio_vowels > 0.70 or (weird_chars / len(cleaned)) > 0.05:
            return 0.40
        return 0.0

log = logging.getLogger("scrapperbf.light_ocr")

OCR_GARBLING_THRESHOLD = 0.22
MIN_TEXT_LENGTH_THRESHOLD = 40


def get_ocr_config() -> Dict[str, Any]:
    """Lit la configuration OCR depuis les variables d'environnement."""
    enable_env = os.environ.get("ENABLE_OCR", "1").strip().lower()
    enabled = enable_env not in ("0", "false", "no", "off")
    lang = os.environ.get("OCR_LANG", "fra").strip()
    cmd = os.environ.get("TESSERACT_CMD", "").strip()
    return {
        "enabled": enabled,
        "lang": lang,
        "tesseract_cmd": cmd or None
    }


def needs_ocr(text: str) -> Tuple[bool, str]:
    """
    Détermine si une page ou un bloc de texte nécessite un repli OCR.
    Retourne (bool, motif).
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH_THRESHOLD:
        return True, "page_vide_ou_scannée"

    score = garbling_score(text)
    if score >= OCR_GARBLING_THRESHOLD:
        return True, f"texte_corrompu_charabia_{score:.2f}"

    return False, "texte_valide"


def render_page_image_bytes(pdf_path: str, page_idx: int, scale: float = 2.0) -> bytes:
    """Rend une page PDF en mémoire au format PNG."""
    doc = pdfium.PdfDocument(pdf_path)
    page = doc[page_idx]
    image = page.render(scale=scale).to_pil()
    doc.close()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _resolve_tesseract_binary(custom_cmd: Optional[str] = None) -> Optional[str]:
    """Recherche l'exécutable tesseract sur le système."""
    if custom_cmd and Path(custom_cmd).is_file():
        return custom_cmd

    which = shutil.which("tesseract")
    if which:
        return which

    # Chemins usuels sur Windows
    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe")

    for c in candidates:
        if c.is_file():
            return str(c)

    return None


def build_ocr_provider(custom_provider: Optional[Callable[[bytes], str]] = None) -> Optional[Callable[[bytes], str]]:
    """
    Construit le fournisseur OCR actif.
    Retourne None si l'OCR est désactivé ou si aucun backend n'est disponible.
    """
    if custom_provider is not None:
        return custom_provider

    config = get_ocr_config()
    if not config["enabled"]:
        log.info("LightOCR est désactivé via ENABLE_OCR=0")
        return None

    # 1. Vérification pytesseract
    try:
        import pytesseract
        from PIL import Image

        tess_bin = _resolve_tesseract_binary(config.get("tesseract_cmd"))
        if tess_bin:
            pytesseract.pytesseract.tesseract_cmd = tess_bin

        def pytesseract_runner(img_bytes: bytes) -> str:
            img = Image.open(io.BytesIO(img_bytes))
            return pytesseract.image_to_string(img, lang=config["lang"])

        # Test rapide si l'exécutable est joignable
        if tess_bin:
            log.info("LightOCR configuré avec Tesseract local : %s (Langue : %s)", tess_bin, config["lang"])
            return pytesseract_runner
    except Exception:
        pass

    log.debug("Aucun moteur OCR local (Tesseract) n'est installé.")
    return None


def recover_page_text_if_needed(
    pdf_path: str,
    page_idx: int,
    current_text: str,
    provider: Optional[Callable[[bytes], str]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Examine le texte extrait de la page. Si corrompu ou vide, tente le repli OCR.
    Retourne (texte_final, rapport_diagnostic).
    """
    should_ocr, reason = needs_ocr(current_text)
    if not should_ocr:
        return current_text, {
            "ocr_necessaire": False,
            "ocr_applique": False,
            "motif": reason,
            "alerte_humaine": False
        }

    ocr_engine = provider or build_ocr_provider()
    if ocr_engine is None:
        log.warning("Page %d nécessite un OCR (%s), mais aucun moteur OCR n'est configuré.", page_idx + 1, reason)
        return current_text, {
            "ocr_necessaire": True,
            "ocr_applique": False,
            "motif": reason,
            "statut": "BACKEND_ABSENT",
            "alerte_humaine": True
        }

    try:
        img_bytes = render_page_image_bytes(pdf_path, page_idx)
        recovered_text = ocr_engine(img_bytes) or ""

        old_score = garbling_score(current_text)
        new_score = garbling_score(recovered_text)

        # Si le texte OCR est meilleur ou si l'ancien était quasi vide
        if len(recovered_text.strip()) > len(current_text.strip()) or new_score < old_score:
            log.info("Page %d récupérée avec succès via LightOCR (%d caractères)", page_idx + 1, len(recovered_text))
            return recovered_text, {
                "ocr_necessaire": True,
                "ocr_applique": True,
                "motif": reason,
                "ancien_score_charabia": old_score,
                "nouveau_score_charabia": new_score,
                "alerte_humaine": True  # Toujours signaler pour contrôle qualité
            }
        else:
            return current_text, {
                "ocr_necessaire": True,
                "ocr_applique": False,
                "motif": "ocr_sans_amelioration",
                "alerte_humaine": True
            }
    except Exception as e:
        log.error("Échec de l'exécution LightOCR sur la page %d : %s", page_idx + 1, e)
        return current_text, {
            "ocr_necessaire": True,
            "ocr_applique": False,
            "erreur": str(e),
            "alerte_humaine": True
        }

