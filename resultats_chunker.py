"""
Découpage des unités-émetteur RÉSULTATS trop grandes pour un seul appel LLM,
EN PRÉSERVANT L'INTÉGRITÉ des informations (cas du 4503bis : 1 émetteur, 94 pages).

Comment on garde l'intégrité :
  1. On ne coupe JAMAIS au milieu d'un lot. Les frontières de découpe sont les
     marqueurs « Lot N : … » repérés dans le TEXTE (pas via la couleur, qui n'est
     pas obligatoire). Un chunk contient un ou plusieurs lots ENTIERS.
  2. Chaque chunk rappelle le CONTEXTE : émetteur + préambule (référence,
     financement, en-tête de colonnes), pour que le LLM sache à quoi rattacher
     un tableau qui continue.
  3. Si un SEUL lot dépasse la taille max, on le découpe en sous-morceaux avec
     CHEVAUCHEMENT (quelques lignes répétées de part et d'autre), et on marque la
     continuation : aucune ligne de soumissionnaire n'est perdue à la jointure.
  4. La fusion (merge_lot_results) regroupe par numéro de lot, concatène les
     soumissionnaires en DÉDUPLIQUANT par nom (le chevauchement ne double donc
     rien), et réconcilie attributaire / infructueux.

Purement déterministe (le découpage et la fusion) ; testable hors-ligne.
"""

import re
import unicodedata
from typing import Optional

_LOT_START_RE = re.compile(
    r"(?im)^\s*lot\s*(?:n\s*[°o]\s*)?(\d{1,3}|unique)\s*(?:[:.\-–]|\s*$)"
)


def _fold(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def _promote_band_markers(flat_text: str, lot_bands: Optional[list]) -> str:
    """Si une petite bande de lot colorée (grise, verte, jaune, orange) n'était pas
    en début de ligne dans le texte aplati (ex: fusion de colonnes), insère un saut de
    ligne juste avant son intitulé afin que split_into_lots découpe proprement dessus."""
    if not flat_text or not lot_bands:
        return flat_text
    out = flat_text
    for b in lot_bands:
        txt = (b.get("text") if isinstance(b, dict) else str(b or "")).strip()
        if not txt:
            continue
        # Préfixe court (ex: "LOT N°1 : Réalisation" ou "1. Acquisition de")
        tokens = txt[:32].split()
        if not tokens:
            continue
        probe = r"\s+".join(re.escape(tok) for tok in tokens)
        # Ne pas casser si déjà en début de ligne
        out = re.sub(r"(?im)(?<=[^\n\s])([ \t]+)(?=" + probe + r")", "\n", out, count=1)
    return out


def split_into_lots(flat_text: str, lot_bands: Optional[list] = None):
    """Découpe le texte en (préambule, [(numero, texte_lot), …]) sur les
    marqueurs « Lot N : / Lot N. / LOT N / Lot Unique : » (y compris ceux issus
    des petites bandes grises, vertes, jaunes ou oranges).
    Préambule = tout ce qui précède le 1er lot (en-tête, référence, financement,
    en-tête de colonnes). S'il n'y a aucun marqueur, le tout est un lot unique numéro 1."""
    text = _promote_band_markers(flat_text or "", lot_bands)
    marks = list(_LOT_START_RE.finditer(text))
    if not marks and lot_bands:
        # Repli sur les marqueurs numérotés sans le mot « Lot » (ex: bandes grises/vertes « 1. Acquisition... »)
        alt_patterns = []
        for b in lot_bands:
            t = (b.get("text") if isinstance(b, dict) else str(b or "")).strip()
            m_alt = re.match(r"^\s*(\d{1,2})\s*[:.]\s*\S{3,}", t)
            if m_alt:
                alt_patterns.append((m_alt.group(1), re.escape(t[:25])))
        if alt_patterns:
            alt_re = re.compile(r"(?im)^\s*(?:" + "|".join(p[1] for p in alt_patterns) + r")")
            alt_marks = list(alt_re.finditer(text))
            if alt_marks:
                preambule = text[: alt_marks[0].start()].strip()
                lots = []
                for i, m in enumerate(alt_marks):
                    end = alt_marks[i + 1].start() if i + 1 < len(alt_marks) else len(text)
                    num_m = re.match(r"^\s*(\d{1,2})", m.group(0))
                    lots.append((num_m.group(1) if num_m else str(i + 1), text[m.start():end].strip()))
                return preambule, lots

    if not marks:
        return text.strip(), [("1", text.strip())]
    preambule = text[: marks[0].start()].strip()
    lots = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        num = "Unique" if m.group(1).lower() == "unique" else m.group(1)
        lots.append((num, text[m.start():end].strip()))
    return preambule, lots


def _split_big_lot(numero: str, lot_text: str, budget: int, overlap_lines: int):
    """Découpe un lot unique trop grand en sous-morceaux, avec chevauchement de
    `overlap_lines` lignes pour ne rien perdre à la jointure."""
    lines = lot_text.split("\n")
    pieces, cur, size = [], [], 0
    for ln in lines:
        cur.append(ln)
        size += len(ln) + 1
        if size >= budget:
            pieces.append(cur)
            cur = cur[-overlap_lines:] if overlap_lines else []  # chevauchement
            size = sum(len(x) + 1 for x in cur)
    if cur:
        pieces.append(cur)
    return ["\n".join(p) for p in pieces] or [lot_text]


def chunk_unit(unit: dict, max_chars: int = 12000, overlap_lines: int = 3,
               split_by_lot: bool = False) -> list:
    """Découpe une unité-émetteur en chunks respectant l'intégrité des lots.
    Si `split_by_lot=True`, force un chunk distinct par lot (idéal pour la génération
    de fichiers .md unitaires parallélisables entre agents sur un même PDF).
    Chaque chunk : {index, total, emetteur, lots_inclus, is_continuation, flat_text, +provenance}."""
    flat = unit.get("flat_text", "") or ""
    emetteur = unit.get("emetteur", "")
    preambule, lots = split_into_lots(flat, lot_bands=unit.get("lot_bands"))
    header = f"ÉMETTEUR (cadre noir) : {emetteur}\n"
    if preambule:
        header += f"PRÉAMBULE (réf./financement/en-tête de colonnes) :\n{preambule[:900]}\n"
    header += "------------------------------------------------------------\n"
    budget = max(2000, max_chars - len(header))

    raw_chunks = []  # (lots_inclus, text, is_continuation)
    cur_lots, cur_text, cur_size = [], [], 0

    def flush():
        if cur_text:
            raw_chunks.append((list(cur_lots), "\n\n".join(cur_text), False))

    for numero, lot_text in lots:
        if len(lot_text) > budget:
            # Lot géant : on vide l'accumulateur puis on le découpe avec overlap.
            flush()
            cur_lots, cur_text, cur_size = [], [], 0
            parts = _split_big_lot(numero, lot_text, budget, overlap_lines)
            for k, part in enumerate(parts):
                raw_chunks.append(([numero], part, k > 0))
            continue
        if split_by_lot:
            flush()
            cur_lots, cur_text, cur_size = [numero], [lot_text], len(lot_text) + 2
            flush()
            cur_lots, cur_text, cur_size = [], [], 0
            continue
        if cur_size + len(lot_text) > budget and cur_text:
            flush()
            cur_lots, cur_text, cur_size = [], [], 0
        cur_lots.append(numero)
        cur_text.append(lot_text)
        cur_size += len(lot_text) + 2
    flush()

    total = len(raw_chunks)
    chunks = []
    for i, (lots_inclus, text, is_cont) in enumerate(raw_chunks):
        cont = ""
        if is_cont:
            cont = (f"\n[SUITE du Lot {lots_inclus[0]} — morceau {i + 1}/{total} ; "
                    "les premières lignes recouvrent la fin du morceau précédent, "
                    "ne les compte pas deux fois.]\n")
        chunks.append({
            "index": i + 1, "total": total,
            "emetteur": emetteur,
            "macro_section": unit.get("macro_section"),
            "lots_inclus": lots_inclus,
            "is_continuation": is_cont,
            "_is_lot_split": split_by_lot or total > 1,
            "flat_text": header + cont + text,
            "nb_lots_detectes": 1 if (is_cont or split_by_lot) else len(lots_inclus),
            "page_debut": unit.get("page_debut"), "page_fin": unit.get("page_fin"),
            "_numero": unit.get("_numero"), "_dossier_index": unit.get("_dossier_index"),
            "_source_pdf": unit.get("_source_pdf"), "_source": unit.get("_source"),
        })
    return chunks


def _lot_key(lot: dict) -> str:
    num = lot.get("numero")
    if num not in (None, ""):
        return f"n{num}"
    return _fold(lot.get("intitule", ""))[:40] or "lot"


def merge_lot_results(results: list) -> dict:
    """Fusionne les sorties LLM des chunks d'UN émetteur en un seul résultat.
    Regroupe par lot, concatène les soumissionnaires en dédupliquant par nom,
    réconcilie attributaire/infructueux. C'est l'étape qui garantit l'intégrité
    malgré le découpage."""
    merged = {}
    autorite = reference = objet = financement = date_delib = None
    for res in results:
        if not isinstance(res, dict):
            continue
        autorite = autorite or res.get("autorite_contractante")
        reference = reference or res.get("reference")
        objet = objet or res.get("objet")
        financement = financement or res.get("financement")
        date_delib = date_delib or res.get("date_deliberation")
        for lot in (res.get("lots") or []):
            if not isinstance(lot, dict):
                continue
            key = _lot_key(lot)
            tgt = merged.setdefault(key, {
                "numero": lot.get("numero"),
                "intitule": lot.get("intitule"),
                "soumissionnaires": [],
                "attributaire_provisoire": None,
                "infructueux": False,
                "_vus": set(),
            })
            tgt["numero"] = tgt["numero"] if tgt["numero"] not in (None, "") else lot.get("numero")
            tgt["intitule"] = tgt["intitule"] or lot.get("intitule")
            for s in (lot.get("soumissionnaires") or []):
                nom = _fold(s.get("nom") if isinstance(s, dict) else s)
                if nom and nom in tgt["_vus"]:
                    continue          # doublon dû au chevauchement : ignoré
                tgt["_vus"].add(nom)
                tgt["soumissionnaires"].append(s)
            if not tgt["attributaire_provisoire"] and lot.get("attributaire_provisoire"):
                tgt["attributaire_provisoire"] = lot["attributaire_provisoire"]
            tgt["infructueux"] = tgt["infructueux"] or bool(lot.get("infructueux"))

    lots_out = []
    for lot in merged.values():
        lot.pop("_vus", None)
        lots_out.append(lot)
    lots_out.sort(key=lambda l: (l.get("numero") is None, l.get("numero") or 0))
    return {
        "autorite_contractante": autorite,
        "reference": reference,
        "objet": objet,
        "financement": financement,
        "date_deliberation": date_delib,
        "nombre_lots": len(lots_out),
        "lots": lots_out,
    }
