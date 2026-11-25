import urllib.request
import json

url = 'http://127.0.0.1:3001/v1/chat/completions'
key = 'freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8'

text_court = 'Tableau des résultats: Lot 1: Société Faso Tech montant 15 000 000 FCFA attributaire conforme. Lot 2: infructueux.'
payload = {
    'model': 'qwen3.8-27b',
    'messages': [
        {'role': 'system', 'content': 'Extrais en json'},
        {'role': 'user', 'content': text_court}
    ],
    'response_format': {'type': 'json_object'},
    'max_tokens': 1000
}
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print('qwen3.8-27b court OK:', resp.status)
        print('Resp:', resp.read().decode('utf-8')[:200])
except Exception as e:
    print('qwen3.8-27b court FAIL:', e)
