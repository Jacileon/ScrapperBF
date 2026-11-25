#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resultats_md_splitter.py
========================
Découpage physique des sections RÉSULTATS (PDF) en fichiers Markdown (.md)
unitaires (1 fichier .md = 1 dossier ou 1 lot), en reprenant exactement la logique
de segmentation (barres noires émetteurs + bandes lots orange, grises, vertes, jaunes).

Avantage pour le parallélisme multi-agents :
  Plusieurs agents travaillent sur le MÊME PDF tout en prenant chacun un .md différent,
  grâce à une prise de tâche atomique par déplacement de fichier (en_attente -> en_cours -> termine).
"""

import argparse
import json
import os
import re
import sqlite3
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pdf_resultats_extract import segment_resultats
from resultats_chunker import chunk_unit
from extract_and_load_resultats import split_unit_into_dossiers, DB_PATH
from split_resultats_sections import detecter_bornes_resultats
from section_split import split_sections

BASE_MD_DIR = Path("resultats_decoupes_md")
QUEUE_STATES = ("en_attente", "en_cours", "termine", "erreur")


def ensure_year_dirs(annee: str, base_dir: Path = BASE_MD_DIR) -> Dict[str, Path]:
    """Crée et retourne les dossiers de file d'attente pour une année."""
    root = base_dir / str(annee)
    dirs = {}
    for st in QUEUE_STATES:
        p = root / st
        p.mkdir(parents=True, exist_ok=True)
        dirs[st] = p
    return dirs


def _slugify(text: str, max_len: int = 28) -> str:
    s = re.sub(r"[^\w]+", "_", str(text or "AUT")).strip("_")
    return (s[:max_len] or "AUT")


def _yaml_escape(val: object) -> str:
    return json.dumps(val, ensure_ascii=False)


def render_chunk_markdown(chunk: dict, bulletin_nom: str, annee: str,
                          date_parution: Optional[str], source_pdf: str,
                          unit_orig: Optional[dict] = None) -> str:
    """Sérialise un chunk (dossier ou lot unitaire) en fichier Markdown avec frontmatter YAML."""
    u = unit_orig or {}
    lots_inclus = chunk.get("lots_inclus") or ["1"]
    lot_bands = u.get("lot_bands") or []
    couleurs = sorted({b.get("color") for b in lot_bands if isinstance(b, dict) and b.get("color")})

    meta = {
        "bulletin_nom": bulletin_nom,
        "numero": chunk.get("_numero") or u.get("_numero") or "N_INCONNU",
        "annee": str(annee),
        "date_parution": date_parution,
        "source_pdf": str(source_pdf),
        "source_file": chunk.get("_source") or Path(source_pdf).name,
        "emetteur": chunk.get("emetteur") or "Inconnu",
        "macro_section": chunk.get("macro_section") or "MINISTERES",
        "page_debut": chunk.get("page_debut"),
        "page_fin": chunk.get("page_fin"),
        "unit_numero": chunk.get("_numero_unite") or 1,
        "dossier_index": chunk.get("_dossier_index") or 1,
        "lots_inclus": lots_inclus,
        "lots_labels": u.get("lots") or [],
        "lot_bands_couleurs": couleurs,
        "nb_lots_detectes": chunk.get("nb_lots_detectes") or len(lots_inclus),
        "is_lot_split": bool(chunk.get("_is_lot_split")),
        "is_continuation": bool(chunk.get("is_continuation")),
        "chunk_index": chunk.get("index") or 1,
        "chunk_total": chunk.get("total") or 1,
    }

    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {_yaml_escape(v)}")
    lines.append("---\n")

    lots_str = ", ".join(str(x) for x in lots_inclus)
    lines.append(f"# {bulletin_nom} — {meta['emetteur']}")
    lines.append("")
    lines.append(f"- **Année :** {annee}")
    lines.append(f"- **Section :** {meta['macro_section']}")
    lines.append(f"- **Pages :** p.{meta['page_debut']}–p.{meta['page_fin']}")
    lines.append(f"- **Lot(s) inclus :** {lots_str} (morceau {meta['chunk_index']}/{meta['chunk_total']})")
    if couleurs:
        lines.append(f"- **Bandes lot détectées :** {', '.join(couleurs)}")
    lines.append("")
    lines.append("## Texte structuré à extraire")
    lines.append("")
    lines.append("<!-- DEBUT_TEXTE_APLATI -->")
    lines.append((chunk.get("flat_text") or "").strip())
    lines.append("<!-- FIN_TEXTE_APLATI -->")
    lines.append("")
    return "\n".join(lines)


def parse_md_to_unit(md_path: Path) -> dict:
    """Reconstitue le dict `unit` complet depuis un fichier .md généré par `render_chunk_markdown`."""
    content = Path(md_path).read_text(encoding="utf-8")
    meta = {}
    m_fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if m_fm:
        for line in m_fm.group(1).splitlines():
            if ":" not in line:
                continue
            k, raw_v = line.split(":", 1)
            k = k.strip()
            raw_v = raw_v.strip()
            try:
                meta[k] = json.loads(raw_v)
            except Exception:
                meta[k] = raw_v.strip("\"'")

    m_body = re.search(
        r"<!-- DEBUT_TEXTE_APLATI -->\s*\n(.*?)\n<!-- FIN_TEXTE_APLATI -->",
        content,
        re.DOTALL,
    )
    flat_text = m_body.group(1) if m_body else content

    return {
        "emetteur": meta.get("emetteur") or "Inconnu",
        "macro_section": meta.get("macro_section") or "MINISTERES",
        "page_debut": meta.get("page_debut"),
        "page_fin": meta.get("page_fin"),
        "nb_lots_detectes": meta.get("nb_lots_detectes") or 1,
        "lots": meta.get("lots_labels") or [],
        "lots_inclus": meta.get("lots_inclus") or ["1"],
        "is_continuation": bool(meta.get("is_continuation")),
        "_is_lot_split": bool(meta.get("is_lot_split")),
        "_numero": meta.get("unit_numero") or 1,
        "_dossier_index": meta.get("dossier_index") or 1,
        "_source_pdf": meta.get("source_pdf") or "",
        "_source": meta.get("source_file") or Path(md_path).name,
        "_origine": "file_md",
        "_bulletin_nom": meta.get("bulletin_nom") or "",
        "_bulletin_numero": meta.get("numero") or "",
        "_annee": meta.get("annee") or "",
        "_date_parution": meta.get("date_parution"),
        "flat_text": flat_text,
    }


def _detect_resultats_ranges(pdf_p: Path) -> Tuple[List[Tuple[str, Tuple[int, int]]], Optional[str]]:
    """Retourne les plages de pages (0-based inclusif) de la section RÉSULTATS pour un PDF complet,
    ou `[('ALL', None)]` si c'est déjà un sous-PDF de section Résultats."""
    if "resultats_" in pdf_p.stem.lower() or "resultat" in pdf_p.stem.lower():
        return [("SEC", None)], None

    date_parution = None
    ranges: List[Tuple[str, Tuple[int, int]]] = []
    try:
        bornes = detecter_bornes_resultats(str(pdf_p))
        date_parution = bornes.get("date_parution")
        m_rng = bornes.get("mimod")
        r_rng = bornes.get("region")
        if m_rng and r_rng:
            ranges.append(("RES", (min(m_rng[0], r_rng[0]), max(m_rng[1], r_rng[1]))))
        elif m_rng:
            ranges.append(("MIMOD", m_rng))
        elif r_rng:
            ranges.append(("REG", r_rng))
    except Exception:
        pass

    if not ranges:
        try:
            sec = split_sections(str(pdf_p))
            if sec.get("RESULTATS"):
                ranges.append(("RES", sec["RESULTATS"]))
        except Exception:
            pass
    return ranges, date_parution


def split_pdf_to_md(pdf_path: str, bulletin_nom: str, annee: str,
                    date_parution: Optional[str] = None,
                    base_dir: Path = BASE_MD_DIR,
                    max_chars: int = 11000,
                    split_by_lot: bool = True) -> List[Path]:
    """Découpe un PDF de résultats (complet ou section) en fichiers .md unitaires dans `en_attente/`.
    Ignore les fichiers déjà présents dans `en_attente`, `en_cours` ou `termine`."""
    pdf_p = Path(pdf_path)
    if not pdf_p.exists():
        return []

    dirs = ensure_year_dirs(annee, base_dir=base_dir)
    existing_names = set()
    for st in ("en_attente", "en_cours", "termine"):
        for f in dirs[st].glob("*.md"):
            existing_names.add(f.name)

    sub_ranges, detected_date = _detect_resultats_ranges(pdf_p)
    if not sub_ranges:
        return []
    if not date_parution:
        date_parution = detected_date

    m_num = re.search(r"(?:Quotidien\s*N?[°o]?\s*|N)(\d{3,4}(?:\s*\(?bis\)?|-?\d{4})?)", pdf_p.stem, re.I)
    if m_num:
        raw_num = re.sub(r"\s+", "", m_num.group(1)).replace("(", "").replace(")", "")
        num_code = f"N{raw_num}"
    else:
        num_code = _slugify(bulletin_nom, 16)

    created = []
    for default_tag, page_range in sub_ranges:
        try:
            units = segment_resultats(str(pdf_p), page_range=page_range)
        except Exception:
            continue
        if not units:
            continue
        sec_tag = default_tag if default_tag != "SEC" else ("REG" if "region" in pdf_p.stem.lower() else "MIMOD")

        for u_idx, u in enumerate(units, 1):
            if len((u.get("flat_text") or "").strip()) < 80:
                continue
            u["_numero_unite"] = u_idx
            dossiers = split_unit_into_dossiers(u)
            for d_idx, d in enumerate(dossiers, 1):
                d["_numero_unite"] = u_idx
                d["_dossier_index"] = d_idx
                chunks = chunk_unit(d, max_chars=max_chars, split_by_lot=split_by_lot)
                aut_slug = _slugify(d.get("emetteur") or "AUT", 22)
                # Compteur LOCAL par lot : évite que 2 morceaux du même lot géant
                # aient des noms indiscernables qui feraient traiter le même lot 2×.
                lot_chunk_counters: Dict[str, int] = {}
                for ch in chunks:
                    ch["_numero_unite"] = u_idx
                    ch["_dossier_index"] = d_idx
                    lots_tag = "_".join(str(x) for x in (ch.get("lots_inclus") or ["1"]))[:16]
                    # Index local au sein de ce lot (1-based), pas global dans le dossier
                    lot_chunk_counters[lots_tag] = lot_chunk_counters.get(lots_tag, 0) + 1
                    c_idx = lot_chunk_counters[lots_tag]
                    fname = f"{num_code}_{sec_tag}_u{u_idx:03d}_d{d_idx:02d}_lot{lots_tag}_p{c_idx:02d}_{aut_slug}.md"
                    if fname in existing_names:
                        continue
                    md_text = render_chunk_markdown(
                        chunk=ch,
                        bulletin_nom=bulletin_nom,
                        annee=annee,
                        date_parution=date_parution,
                        source_pdf=str(pdf_p),
                        unit_orig=d,
                    )
                    out_file = dirs["en_attente"] / fname
                    out_file.write_text(md_text, encoding="utf-8")
                    existing_names.add(fname)
                    created.append(out_file)
    return created


def _chunk_group_index(name: str) -> Optional[Tuple[str, int]]:
    """Extrait (groupe, index) d'un nom de chunk : `..._lot1_c03_...` → (groupe, 3).

    Le groupe est le nom de fichier tronqué avant `_cNN_` / `_pNN_` (bulletin,
    unité, dossier et lot). Retourne None si le nom n'est pas un chunk."""
    m = re.match(r"^(?P<grp>.+)_(?P<sch>[cp])(?P<idx>\d+)_(?P<aut>.+)$", name)
    if not m:
        return None
    return m.group("grp"), int(m.group("idx"))


def claim_next_md(annee: str, base_dir: Path = BASE_MD_DIR) -> Optional[Path]:
    """Prend atomiquement le prochain fichier .md en attente et le déplace dans `en_cours/`.
    Garantit qu'aucun deux agents ne traitent le même .md.

    Les chunks d'un même lot géant (`_cNN_`/`_pNN_`) sont claimés EN SÉRIE :
    un chunk n'est pris que si aucun chunk de même groupe à index inférieur
    n'est encore en_attente ou en_cours. Évite que2 workers n'extraient le
    même lot en parallèle (pertes/doublons lors des upserts DB)."""
    dirs = ensure_year_dirs(annee, base_dir=base_dir)

    # groupes → index mini encore présent en_attente OU en_cours
    # (un chunk n'est claimable que s'il est le plus petit index restant de son lot)
    pending_min: Dict[str, int] = {}
    for folder in ("en_attente", "en_cours"):
        for f in dirs[folder].glob("*.md"):
            gi = _chunk_group_index(f.name)
            if gi:
                grp, idx = gi
                if grp not in pending_min or idx < pending_min[grp]:
                    pending_min[grp] = idx

    for src in sorted(dirs["en_attente"].glob("*.md")):
        gi = _chunk_group_index(src.name)
        if gi:
            grp, idx = gi
            # Un chunk du même lot à index inférieur est encore en attente/en cours
            # → on laisse ce chunk pour plus tard (l'autre sera claimé avant).
            if idx > pending_min.get(grp, idx):
                continue
        dst = dirs["en_cours"] / src.name
        try:
            os.replace(str(src), str(dst))
            return dst
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return None


def complete_md(claimed_path: Path, annee: str, base_dir: Path = BASE_MD_DIR) -> Path:
    """Déplace un fichier .md terminé de `en_cours/` vers `termine/`."""
    dirs = ensure_year_dirs(annee, base_dir=base_dir)
    dst = dirs["termine"] / claimed_path.name
    os.replace(str(claimed_path), str(dst))
    return dst


def release_md(claimed_path: Path, annee: str, to_error: bool = False,
               base_dir: Path = BASE_MD_DIR) -> Optional[Path]:
    """Replace un .md dans `en_attente/` (ou `erreur/` si échec définitif)."""
    if not claimed_path.exists():
        return None
    dirs = ensure_year_dirs(annee, base_dir=base_dir)
    target_dir = dirs["erreur"] if to_error else dirs["en_attente"]
    dst = target_dir / claimed_path.name
    os.replace(str(claimed_path), str(dst))
    return dst


def split_manifest_to_md(annee: str = "all", manifest_path: Path = Path("manifeste_complet_resultats.json"),
                         skip_db_existing: bool = True) -> dict:
    """Découpe en .md tous les bulletins restants du manifeste pour 2025 et/ou 2026."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    deja_en_base = set()
    if skip_db_existing and DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH, timeout=30)
        for r in conn.execute("SELECT DISTINCT bulletin FROM resultats_marches").fetchall():
            if r[0]:
                deja_en_base.add(r[0].strip().upper())
                m = re.search(r"N\s*(\d{4}(?:bis)?)", r[0], re.I)
                if m:
                    deja_en_base.add(f"N{m.group(1)}".upper())
        conn.close()

    years = ["2025", "2026"] if annee == "all" else [str(annee)]
    stats = {"years": {}, "total_files_created": 0}
    for yr in years:
        queue = manifest.get(f"queue_{yr}", [])
        created_yr = 0
        bulletins_yr = 0
        for q in queue:
            num = q.get("numero", "")
            b_nom = q.get("bulletin_nom") or f"Quotidien {num}"
            if skip_db_existing and (b_nom.upper() in deja_en_base or f"N{num}".upper() in deja_en_base or num.upper() in deja_en_base):
                continue
            bulletins_yr += 1
            for sec_info in (q.get("sections") or {}).values():
                pdf_p = sec_info.get("pdf_path")
                if not pdf_p:
                    continue
                files = split_pdf_to_md(
                    pdf_path=pdf_p,
                    bulletin_nom=b_nom,
                    annee=yr,
                    date_parution=q.get("date_parution"),
                )
                created_yr += len(files)
        stats["years"][yr] = {"bulletins_split": bulletins_yr, "md_files_created": created_yr}
        stats["total_files_created"] += created_yr
    return stats


def _is_pdf_intact(pdf_p: Path) -> bool:
    """Vérifie rapidement qu'un PDF n'est pas tronqué (en-tête %PDF- et %%EOF)."""
    try:
        sz = pdf_p.stat().st_size
        if sz < 5000:
            return False
        with open(pdf_p, "rb") as f:
            head = f.read(16)
            f.seek(max(0, sz - 1024))
            tail = f.read(1024)
        return head.startswith(b"%PDF-") and (b"%%EOF" in tail)
    except Exception:
        return False


def _split_one_pdf_worker(args: Tuple[str, str, str, str]) -> Tuple[str, str, int, str]:
    yr, pdf_str, b_nom, base_str = args
    p = Path(pdf_str)
    if not _is_pdf_intact(p):
        return yr, p.name, 0, "CORRUPTED_EOF"
    try:
        created = split_pdf_to_md(pdf_str, bulletin_nom=b_nom, annee=yr, base_dir=Path(base_str))
        return yr, p.name, len(created), "OK" if created else "NO_RESULTATS"
    except Exception as e:
        return yr, p.name, 0, f"ERR: {str(e)[:80]}"


def split_folders_to_md(
    dirs_by_year: Optional[Dict[str, Path]] = None,
    skip_db_existing: bool = True,
    max_workers: int = 6,
    base_dir: Path = BASE_MD_DIR,
) -> dict:
    """Découpe en .md tous les Quotidiens complets situés dans telechargements_pdf_classes/2025 et 2026."""
    if dirs_by_year is None:
        dirs_by_year = {
            "2025": Path("telechargements_pdf_classes/2025"),
            "2026": Path("telechargements_pdf_classes/2026"),
        }

    deja_en_base = set()
    if skip_db_existing and DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH, timeout=30)
        for r in conn.execute("SELECT DISTINCT bulletin FROM resultats_marches").fetchall():
            if r[0]:
                deja_en_base.add(r[0].strip().upper())
                m = re.search(r"N\s*(\d{4}(?:\s*\(?bis\)?)?)", r[0], re.I)
                if m:
                    deja_en_base.add(f"N{re.sub(r'\\s+', '', m.group(1))}".upper())
        conn.close()

    tasks = []
    skipped_db = {"2025": 0, "2026": 0}
    for yr, root in dirs_by_year.items():
        if not root.exists():
            continue
        ensure_year_dirs(yr, base_dir=base_dir)
        pdfs = sorted([
            p for p in root.rglob("*.pdf")
            if "01_sections" not in str(p)
            and "02_sections" not in str(p)
            and "resultats_scindes" not in str(p).lower()
        ])
        for p in pdfs:
            m = re.search(r"(\d{3,4}(?:\s*\(?bis\)?)?)", p.stem, re.I)
            core = re.sub(r"\s+", "", m.group(1)) if m else p.stem
            b_nom = f"Quotidien N°{core}"
            if skip_db_existing and (b_nom.upper() in deja_en_base or f"N{core}".upper() in deja_en_base):
                skipped_db[yr] = skipped_db.get(yr, 0) + 1
                continue
            tasks.append((yr, str(p), b_nom, str(base_dir)))

    stats = {
        "years": {
            yr: {"ok": 0, "skipped_db": skipped_db.get(yr, 0), "md_created": 0, "corrupted": [], "no_resultats": [], "errors": []}
            for yr in dirs_by_year
        },
        "total_md_created": 0,
    }
    if not tasks:
        return stats

    ex = ProcessPoolExecutor(max_workers=max_workers)
    try:
        for yr, fname, cnt, status in ex.map(_split_one_pdf_worker, tasks):
            y_stat = stats["years"][yr]
            if status == "OK":
                y_stat["ok"] += 1
                y_stat["md_created"] += cnt
                stats["total_md_created"] += cnt
            elif status == "CORRUPTED_EOF":
                y_stat["corrupted"].append(fname)
            elif status == "NO_RESULTATS":
                y_stat["no_resultats"].append(fname)
            else:
                y_stat["errors"].append((fname, status))
        ex.shutdown(wait=True)
    except KeyboardInterrupt:
        print("\n[INTERRUPTION] Arrêt propre des workers de découpage...", flush=True)
        ex.shutdown(wait=False, cancel_futures=True)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Découpe les PDF de résultats en fichiers .md unitaires (1 lot/dossier par .md).")
    parser.add_argument("--pdf", help="Chemin d'un PDF unique à découper en .md")
    parser.add_argument("--source-folders", action="store_true", help="Découper directement depuis telechargements_pdf_classes/2025 et 2026")
    parser.add_argument("--annee", default="all", choices=["2025", "2026", "all"], help="Année à découper")
    parser.add_argument("--bulletin", default=None, help="Nom du bulletin (si --pdf)")
    parser.add_argument("--include-existing", action="store_true", help="Découper même les bulletins déjà en base")
    parser.add_argument("--workers", type=int, default=6, help="Nombre de workers parallèles")
    args = parser.parse_args()

    if args.pdf:
        b_nom = args.bulletin or Path(args.pdf).stem
        yr = "2026" if "2026" in args.pdf else "2025"
        out = split_pdf_to_md(args.pdf, bulletin_nom=b_nom, annee=yr)
        print(f"OK — {len(out)} fichiers .md créés dans resultats_decoupes_md/{yr}/en_attente/")
    elif args.source_folders:
        dirs = {}
        if args.annee in ("2025", "all"):
            dirs["2025"] = Path("telechargements_pdf_classes/2025")
        if args.annee in ("2026", "all"):
            dirs["2026"] = Path("telechargements_pdf_classes/2026")
        res = split_folders_to_md(dirs_by_year=dirs, skip_db_existing=not args.include_existing, max_workers=args.workers)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        res = split_manifest_to_md(annee=args.annee, skip_db_existing=not args.include_existing)
        print(json.dumps(res, indent=2, ensure_ascii=False))
