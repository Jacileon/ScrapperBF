import urllib.request, json, time

KEY = 'freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8'
URL = 'http://127.0.0.1:3001/v1/chat/completions'

candidates = [
    'google/gemma-4-26b-a4b-it:free',
    'google/gemma-4-31b-it:free',
    'nvidia/nemotron-3.5-lightning:free'
]

for model in candidates:
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': 'Reponds avec un JSON valide: {"status": "ok"}'}],
        'response_format': {'type': 'json_object'},
        'max_tokens': 30
    }
    req = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode('utf-8'))
            print(f'[{model}] SUCCES en {time.time()-t0:.2f}s: {res["choices"][0]["message"]["content"]}')
    except Exception as e:
        print(f'[{model}] ERREUR en {time.time()-t0:.2f}s: {e}')
