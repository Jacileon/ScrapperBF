#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/pdfgen.py
=================
Générateur PDF minimal en bibliothèque standard (aucune dépendance).
Produit un document texte simple (A4, Helvetica / Helvetica-Bold, WinAnsi)
— suffisant pour une fiche de soumission / récapitulatif de dossier.
"""

from __future__ import annotations

from typing import List, Optional

PAGE_W, PAGE_H = 595, 842
MARGIN = 54
LINE_H = 15


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, size: int) -> List[str]:
    # Largeur approx. d'un caractère Helvetica ≈ 0.5 * taille.
    max_chars = max(10, int((PAGE_W - 2 * MARGIN) / (size * 0.5)))
    out, line = [], ""
    for word in (text or "").split():
        if len(line) + len(word) + 1 <= max_chars:
            line = (line + " " + word).strip()
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out or [""]


def build_pdf(lines: List[dict]) -> bytes:
    """
    lines : liste de dicts { 'text', 'size'(11), 'bold'(False), 'gap'(0) }.
    Retourne les octets d'un PDF une-ou-plusieurs pages (saut auto).
    """
    pages_content: List[str] = []
    ops = ["BT"]
    y = PAGE_H - MARGIN

    def new_page():
        nonlocal ops, y
        ops.append("ET")
        pages_content.append("\n".join(ops))
        ops = ["BT"]
        y = PAGE_H - MARGIN

    for item in lines:
        text = item.get("text", "")
        size = int(item.get("size", 11))
        bold = bool(item.get("bold"))
        gap = int(item.get("gap", 0))
        y -= gap
        font = "/F2" if bold else "/F1"
        for sub in _wrap(text, size):
            if y < MARGIN:
                new_page()
            ops.append(f"{font} {size} Tf")
            ops.append(f"1 0 0 1 {MARGIN} {y} Tm")
            ops.append(f"({_esc(sub)}) Tj")
            y -= LINE_H
    ops.append("ET")
    pages_content.append("\n".join(ops))

    # --- Assemblage des objets PDF ---
    objects: List[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)  # numéro d'objet (1-based)

    font1 = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    font2 = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"

    # On réserve : 1 Catalog, 2 Pages, puis pour chaque page un Page + Contents, puis fonts.
    n_pages = len(pages_content)
    # Numérotation : 1=Catalog, 2=Pages, 3..=(page,contents)*, puis fonts
    page_obj_ids, content_obj_ids = [], []
    base = 3
    for i in range(n_pages):
        page_obj_ids.append(base + i * 2)
        content_obj_ids.append(base + i * 2 + 1)
    font1_id = base + n_pages * 2
    font2_id = font1_id + 1

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages = (f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} "
             f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] >>").encode("latin-1")

    serial = {1: catalog, 2: pages}
    for i in range(n_pages):
        pid, cid = page_obj_ids[i], content_obj_ids[i]
        page = (f"<< /Type /Page /Parent 2 0 R /Resources << /Font << "
                f"/F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> /Contents {cid} 0 R >>").encode("latin-1")
        stream = pages_content[i].encode("latin-1", "replace")
        content = (f"<< /Length {len(stream)} >>\nstream\n").encode("latin-1") + stream + b"\nendstream"
        serial[pid] = page
        serial[cid] = content
    serial[font1_id] = font1
    serial[font2_id] = font2

    total = font2_id
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in range(1, total + 1):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode("latin-1") + serial[num] + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {total + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for num in range(1, total + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {total + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode("latin-1")
    return bytes(out)
