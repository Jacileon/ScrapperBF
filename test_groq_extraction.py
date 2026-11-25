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

# Test direct avec qwen/qwen3.8-27b
import urllib.request, json
KEY = 'freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8'
URL = 'http://127.0.0.1:3001/v1/chat/completions'
from extract_and_load_resultats import RESULTATS_SYSTEM_PROMPT

payload = {
    'model': 'qwen/qwen3.8-27b',
    'messages': [
        {'role': 'system', 'content': RESULTATS_SYSTEM_PROMPT},
        {'role': 'user', 'content': sample_text}
    ],
    'response_format': {'type': 'json_object'},
    'temperature': 0.1
}

req = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode('utf-8'))
        print(f"Extraction GROQ en {time.time()-t0:.2f}s:")
        content = json.loads(res['choices'][0]['message']['content'])
        print(json.dumps(content, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Erreur Groq: {e}")
