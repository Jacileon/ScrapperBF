import sqlite3

conn = sqlite3.connect(r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db')
c = conn.cursor()
c.execute("SELECT id, platform, label, status, enabled, base_url FROM api_keys WHERE enabled = 1")
for r in c.fetchall():
    print(r)
conn.close()
