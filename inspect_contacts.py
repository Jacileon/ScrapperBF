import sqlite3
import re

con = sqlite3.connect('marches_publics_burkina.db')
c = con.cursor()
c.execute("SELECT id, nom_soumissionnaire, telephone, adresse_bp, observations_motifs FROM resultats_soumissionnaires WHERE telephone IS NOT NULL AND length(telephone) > 0")
rows = c.fetchall()
print(f"Total avec telephone: {len(rows)}")

abm_rows = [r for r in rows if "ABM" in r[1].upper()]
print("ABM rows:", abm_rows)

polluted = []
for r in rows:
    tel = r[2]
    if any(k in tel.lower() for k in ["confirmation", "lettre", "bp", "ouaga", "saaba", "bobo", "lot", "offre"]):
        polluted.append(r)
print(f"Polluted count: {len(polluted)}")
for p in polluted[:10]:
    print(f"ID={p[0]} | NOM={p[1]} | TEL={p[2]} | BP={p[3]}")
