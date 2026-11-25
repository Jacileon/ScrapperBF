import sqlite3

conn = sqlite3.connect(r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db')
c = conn.cursor()
c.execute("SELECT id, platform, label, enabled, length(encrypted_key) FROM api_keys WHERE platform = 'openrouter'")
for r in c.fetchall():
    print(r)
