import sqlite3

db_path = r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Mettre à jour les limites artificielles bloquantes
c.execute("UPDATE models SET rpd_limit = 1500, rpm_limit = 30 WHERE platform = 'google'")
c.execute("UPDATE models SET tpm_limit = 30000, rpd_limit = 14400 WHERE platform = 'groq'")
c.execute("DELETE FROM rate_limit_cooldowns WHERE platform IN ('google', 'groq')")
conn.commit()

print("Limites mises à jour avec succès!")

c.execute("SELECT platform, model_id, rpm_limit, rpd_limit, tpm_limit FROM models WHERE model_id IN ('gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'qwen/qwen3.8-27b')")
for r in c.fetchall():
    print(r)

conn.close()
