import sqlite3

db_path = r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Désactiver TeamoRouter (clé 31, solde insuffisant) et Routeway (clé 8, timeouts systématiques)
c.execute("UPDATE api_keys SET enabled = 0, status = 'disabled' WHERE id IN (31, 8)")
conn.commit()

print(f"Clés mises à jour : {c.rowcount}")

c.execute("SELECT id, platform, label, enabled, status FROM api_keys WHERE id IN (2, 8, 10, 30, 31)")
for r in c.fetchall():
    print(r)

conn.close()
