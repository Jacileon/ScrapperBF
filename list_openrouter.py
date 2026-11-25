import sqlite3

conn = sqlite3.connect(r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db')
c = conn.cursor()
c.execute("SELECT id, model_id, display_name, context_window FROM models WHERE platform = 'openrouter'")
for r in c.fetchall():
    print(r)
