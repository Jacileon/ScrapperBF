import sqlite3, time

conn = sqlite3.connect(r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db')
c = conn.cursor()
c.execute("SELECT platform, model_id, key_id, expires_at_ms, source FROM rate_limit_cooldowns WHERE platform = 'google'")
for r in c.fetchall():
    exp = r[3]
    rem = (exp - (time.time() * 1000)) / 1000
    print(r[0], r[1], f"Expire dans {rem:.1f}s", r[4])
conn.close()
