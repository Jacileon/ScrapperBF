import sys
from pdf_resultats_extract import segment_resultats

pdf_path = sys.argv[1] if len(sys.argv) > 1 else 'sections_resultats_pretes/2025/05/N4135_Resultats_MIMOD_p3_p16.pdf'
units = segment_resultats(pdf_path)
print(f"[{pdf_path}] Unités trouvées : {len(units)}")
for i, u in enumerate(units):
    print(f"  Unité {i+1}: {u.get('emetteur', '')[:50]} | pages {u.get('page_debut')}-{u.get('page_fin')} | {len(u.get('flat_text', ''))} chars")
