# -*- coding: utf-8 -*-
import pdfplumber
import sys

def is_creme(color):
    if not color:
        return False
    if len(color) == 3:
        r, g, b = color
        # R >= 90%, G >= 85%, B entre 65% et 96%, et R > B de plus de 3%
        return r >= 0.90 and g >= 0.85 and 0.65 <= b <= 0.96 and (r - b) >= 0.03
    return False

def text_corruption_ratio(text):
    if not text or len(text.strip()) == 0:
        return 0.0
    total = len(text)
    corrupt = 0
    for c in text:
        code = ord(c)
        if code in (10, 13, 9):
            continue
        if 32 <= code <= 126:
            continue
        if 160 <= code <= 255:
            continue
        if code in (8217, 8220, 8221, 8211, 8212, 8364):
            continue
        corrupt += 1
    return corrupt / total

def scan_pdf(pdf_path):
    print('==========================================')
    print('ANALYSE :', pdf_path)
    print('==========================================')
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print('Total pages :', total_pages)
        
        creme_zones = []
        corrupted_pages = []
        
        for idx, page in enumerate(pdf.pages):
            p_num = idx + 1
            shapes = page.rects + page.curves
            page_creme = []
            for s in shapes:
                col = s.get('fill_color') or s.get('non_stroke_color')
                if is_creme(col):
                    w = s.get('width', 0)
                    h = s.get('height', 0)
                    if w > 100 and h > 40:
                        page_creme.append({
                            'x0': round(s.get('x0', 0), 1),
                            'top': round(s.get('top', 0), 1),
                            'width': round(w, 1),
                            'height': round(h, 1),
                            'rgb': [round(c, 3) for c in col]
                        })
            if page_creme:
                creme_zones.append((p_num, page_creme))
                
            txt = page.extract_text() or ''
            ratio = text_corruption_ratio(txt)
            if ratio > 0.08 and len(txt) > 50:
                corrupted_pages.append((p_num, round(ratio * 100, 1), txt[:100].replace(chr(10), ' ')))
                
        print(f'--- ZONES CREME DETECTEES ({len(creme_zones)} pages) ---')
        for p_num, shapes in creme_zones:
            print(f'  Page {p_num}: {len(shapes)} bloc(s) creme : {shapes}')
            
        print(f'--- PAGES AVEC CORRUPTION POLICE/TABLEAU ({len(corrupted_pages)} pages) ---')
        for p_num, ratio, sample in corrupted_pages:
            print(f'  Page {p_num}: Taux anomalie {ratio}% | Debut: {sample}')

if __name__ == '__main__':
    scan_pdf(r'C:\Users\DANIEL\Documents\Mes projets\ScrapperBF\Quotidien N°3665.pdf')
    scan_pdf(r'C:\Users\DANIEL\Documents\Mes projets\ScrapperBF\Quotidien n°4505.pdf')
