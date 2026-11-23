# -*- coding: utf-8 -*-
import pdfplumber
import sys

def is_creme(col):
    if not col or not isinstance(col, (tuple, list)) or len(col) != 3:
        return False
    r, g, b = col
    # R >= 90%, G >= 88%, B entre 65% et 96%, et R > B de plus de 2%
    return r >= 0.90 and g >= 0.88 and 0.65 <= b <= 0.96 and (r - b) >= 0.02

def check_corruption(txt):
    if not txt or len(txt.strip()) == 0:
        return 0.0
    bad = 0
    total = len(txt)
    for c in txt:
        code = ord(c)
        if code in (10, 13, 9) or (32 <= code <= 126) or (160 <= code <= 255) or code in (8217, 8220, 8221, 8211, 8212, 8364):
            continue
        bad += 1
    return bad / total

for path in [r'C:\Users\DANIEL\Documents\Mes projets\ScrapperBF\Quotidien N°3665.pdf', r'C:\Users\DANIEL\Documents\Mes projets\ScrapperBF\Quotidien n°4505.pdf']:
    print('SCAN:', path, flush=True)
    with pdfplumber.open(path) as pdf:
        for idx, p in enumerate(pdf.pages):
            p_num = idx + 1
            shapes = p.rects + p.curves
            creme_boxes = []
            for s in shapes:
                col = s.get('non_stroking_color')
                if is_creme(col):
                    w = s.get('width', 0)
                    h = s.get('height', 0)
                    if w > 60 and h > 30:
                        creme_boxes.append((round(s.get('x0',0),1), round(s.get('top',0),1), round(w,1), round(h,1), [round(x,3) for x in col]))
            
            txt = p.extract_text() or ''
            ratio = check_corruption(txt)
            
            if creme_boxes:
                snippet = txt[:60].replace(chr(10), ' ')
                print(f'  [CREME] Page {p_num:3d}: {len(creme_boxes)} bloc(s) -> {creme_boxes} | {snippet}', flush=True)
            if ratio > 0.05 and len(txt) > 50:
                snippet = txt[:80].replace(chr(10), ' ')
                print(f'  [CORRUPTION] Page {p_num:3d}: {round(ratio*100, 1)}% bizarre | {snippet}', flush=True)
