import time
from extract_and_load_resultats import call_freellm_api

sample_text = """
RESULTATS PROVISOIRES DE LA DEMANDE DE PRIX N°2025-014/MS/SG/CHU-B/DG/DMP DU 25/11/2025
Objet : Acquisition de matériel médico-technique au profit du CHU de Bogodogo.
Financement : Budget CHU-B gestion 2025.
Lot 1 : Matériel de réanimation.
Soumissionnaires :
1. BIOMEDICAL SARL - Montant Lu : 18 500 000 FCFA TTC - Montant Corrigé : 18 500 000 FCFA TTC - Rang : 1er - Retenu
2. PHARMA PLUS - Montant Lu : 19 200 000 FCFA TTC - Montant Corrigé : 19 200 000 FCFA TTC - Rang : 2ème - Non retenu
3. SOCAPHARM - Non conforme pour absence d'agrément technique.
"""

t0 = time.time()
res = call_freellm_api(sample_text)
print(f"Extraction terminée en {time.time()-t0:.2f}s")
import json
print(json.dumps(res, indent=2, ensure_ascii=False))
