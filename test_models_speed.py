import urllib.request
import json
import time

url = 'http://127.0.0.1:3001/v1/chat/completions'
key = 'freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8'

models = ['deepseek-v4-flash', 'qwen3.8-27b', 'llama-3.3-70b-instruct', 'mistral-small-24b-fp8', 'glm-4.7-flash']
for m in models:
    t0 = time.time()
    payload = {
        'model': m,
        'messages': [{'role': 'user', 'content': 'Retourne un JSON avec ok: true'}],
        'response_format': {'type': 'json_object'},
        'max_tokens': 100
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f'Model {m} OK en {round(time.time()-t0, 2)}s: {resp.status}')
    except Exception as e:
        print(f'Model {m} FAIL en {round(time.time()-t0, 2)}s: {e}')
