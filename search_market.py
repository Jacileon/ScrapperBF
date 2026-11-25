import glob
import pdfplumber

def search():
    print("Searching PDFs...")
    for p in glob.glob("**/*4143*.pdf", recursive=True):
        try:
            with pdfplumber.open(p) as pdf:
                for i, page in enumerate(pdf.pages):
                    txt = page.extract_text() or ''
                    if 'CHUP-CDG' in txt or 'CHARLES DE GAULLE' in txt or 'petits matériels' in txt.lower() or 'petit matériel' in txt.lower():
                        print(f"FOUND IN {p} page {i+1}")
                        print(txt)
                        print("="*60)
        except Exception as e:
            print(f"Error reading {p}: {e}")

if __name__ == "__main__":
    search()
