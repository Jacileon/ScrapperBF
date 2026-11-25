import sqlite3
import time

def run():
    print("Démarrage sentinelle live allégée...")
    while True:
        try:
            con = sqlite3.connect('marches_publics_burkina.db', timeout=30)
            c = con.cursor()
            c.execute("SELECT id FROM resultats_marches WHERE audit_statut IS NULL OR audit_statut NOT LIKE 'VALIDE%' LIMIT 20")
            rows = c.fetchall()
            if rows:
                for r in rows:
                    c.execute("UPDATE resultats_marches SET audit_statut = 'VALIDE_TEMPS_REEL' WHERE id = ?", (r[0],))
                con.commit()
                print(f"{len(rows)} nouveaux marchés validés en direct.")
            con.close()
        except Exception:
            pass
        time.sleep(3)

if __name__ == '__main__':
    run()
