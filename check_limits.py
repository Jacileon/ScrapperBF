import sqlite3

conn = sqlite3.connect(r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db')
c = conn.cursor()
c.execute("SELECT platform, model_id, rpm_limit, rpd_limit, tpm_limit, tpd_limit FROM models WHERE platform IN ('google', 'groq')")
for r in c.fetchall():
    print(r)
