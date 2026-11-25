import urllib.request
import json

url = 'http://127.0.0.1:3001/v1/chat/completions'
key = 'freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8'
payload = {
    'model': 'qwen/qwen3.8-27b',
    'messages': [{'role': 'user', 'content': 'Bonjour, réponds en JSON: {"status": "ok"}'}],
    'response_format': {'type': 'json_object'},
    'max_tokens': 100
}
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print('Status:', resp.status)
        print('Resp:', resp.read().decode('utf-8')[:200])
except Exception as e:
    print('Error:', e)
