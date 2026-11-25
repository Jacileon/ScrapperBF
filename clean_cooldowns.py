import sqlite3

db_path = r'C:\Users\DANIEL\Documents\freellmapi\server\data\freeapi.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Désactiver la clé 4 openrouter (sans auth)
c.execute("UPDATE api_keys SET enabled = 0, status = 'invalid' WHERE id = 4")
# Effacer tous les cooldowns google
c.execute("DELETE FROM rate_limit_cooldowns WHERE platform = 'google'")
conn.commit()

print("Clé 4 désactivée et cooldowns Google effacés!")
conn.close()
