import os
import json
import pdfplumber
from pathlib import Path
from pdf_resultats_extract import segment_resultats

def dump_units_to_text(pdf_path: str, out_dir: str):
    p = Path(pdf_path)
    out_path = Path(out_dir) / p.stem
    out_path.mkdir(parents=True, exist_ok=True)
    
    units = segment_resultats(str(p))
    print(f"[{p.name}] Total unités segmentées: {len(units)}")
    
    summary = []
    for i, u in enumerate(units):
        fn = f"dossier_{i+1:02d}.txt"
        file_path = out_path / fn
        text_content = u.get("flat_text", "")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"EMETTEUR: {u.get('emetteur')}\n")
            f.write(f"SECTION: {u.get('macro_section')}\n")
            f.write(f"PAGES: {u.get('page_debut')} à {u.get('page_fin')}\n")
            f.write(f"NB_LOTS_DETECTES: {u.get('nb_lots_detectes')}\n")
            f.write(f"LOTS_LIBELLES: {json.dumps(u.get('lots', []), ensure_ascii=False)}\n")
            f.write("="*70 + "\n\n")
            f.write(text_content)
            
        summary.append({
            "index": i + 1,
            "emetteur": u.get("emetteur"),
            "section": u.get("macro_section"),
            "pages": f"{u.get('page_debut')}-{u.get('page_fin')}",
            "file": str(file_path).replace("\\", "/"),
            "chars": len(text_content)
        })
        
    with open(out_path / "sommaire.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        
    print(f"Unités exportées dans {out_path}")
    return summary

if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else "sections_resultats_pretes/2025/05/N4131_Resultats_MIMOD_p3_p12.pdf"
    dump_units_to_text(pdf, "dossiers_texte_2025")
