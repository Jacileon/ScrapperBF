import urllib.request
import json

url = 'http://127.0.0.1:3001/v1/chat/completions'
key = 'freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8'

candidates = ['mistral-small-24b-fp8', 'glm-4.7-flash', 'minimax-m3', 'gemma-4-31b-it', 'llama-3.3-70b-fp8-fast', 'qwen2.5-72b-instruct']
text_court = 'Tableau des résultats: Lot 1: Société Faso Tech montant 15 000 000 FCFA attributaire conforme. Lot 2: infructueux.'

for m in candidates:
    payload = {
        'model': m,
        'messages': [
            {'role': 'system', 'content': 'Extrais en json'},
            {'role': 'user', 'content': text_court}
        ],
        'response_format': {'type': 'json_object'},
        'max_tokens': 500
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            print(f'Model {m} OK: {resp.status}')
    except Exception as e:
        print(f'Model {m} FAIL: {e}')
