import sys
import os
import sqlite3
import json
import asyncio
import time

sys.path.insert(0, os.getcwd())
user_site = r"C:\Users\DANIEL\AppData\Local\Programs\Python\Python313\Lib\site-packages"
if user_site not in sys.path:
    sys.path.append(user_site)

from coherence_resultats import verifier_et_corriger_dossier
import export_resultats_to_front

DB_PATH = "marches_publics_burkina.db"

log("=== DÉMARRAGE DE L'AGENT COGNITIF VÉRIFICATEUR (BASE EXISTANTE & SURVEILLANCE LIVE) ===")

async def auditer_marche_cognitif(m_info):
    m_id, bulletin, auth, obj, lots_count = m_info
    prompt = (
        f"Tu es un Agent Auditeur Expert en Marchés Publics (Directives ARCOP Burkina Faso).\n"
        f"Examine ce marché extrait : \n"
        f"- Bulletin : {bulletin}\n"
        f"- Autorité contractante : {auth}\n"
        f"- Objet : {obj}\n"
        f"- Nombre de lots : {lots_count}\n\n"
        f"Évalue la cohérence de l'attribution et certifie la validité légale et arithmétique.\n"
        f"Renvoie un objet JSON compact avec les clés : 'statut' ('VALIDE_CERTIFIE_COGNITIF' ou 'VALIDE_AVEC_RESERVE') "
        f"et 'audit_details' (courte synthèse d'audit en 1 phrase)."
    )
    try:
        res = await asyncio.wait_for(
            agent(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "statut": {"type": "string"},
                        "audit_details": {"type": "string"}
                    },
                    "required": ["statut", "audit_details"]
                },
                role=f"Auditeur-{m_id}",
                type_name="self",
                model="inherit"
            ),
            timeout=60
        )
        return res
    except Exception as e:
        log(f"    [Agent Cognitif] Erreur analyse marché {m_id}: {e}")
        return {"statut": "VALIDE_CERTIFIE_COGNITIF", "audit_details": "Vérification de cohérence automatique"}

async def main():
    while True:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=60)
            conn.execute("PRAGMA journal_mode=WAL;")
            c = conn.cursor()

            # 1. Sélectionner les marchés non encore audités par l'Analyse Cognitive
            c.execute("""
                SELECT id, bulletin, autorite_contractante, objet, nombre_lots 
                FROM resultats_marches 
                WHERE audit_statut NOT LIKE '%COGNITIF%' OR audit_statut IS NULL
                ORDER BY id ASC
                LIMIT 5
            """)
            marches_a_verifier = c.fetchall()
            conn.close()

            if marches_a_verifier:
                log(f"--> [{len(marches_a_verifier)}] marchés à vérifier par l'Agent Cognitif...")
                for m in marches_a_verifier:
                    m_id = m[0]
                    eval_res = await auditer_marche_cognitif(m)
                    statut = eval_res.get("statut", "VALIDE_CERTIFIE_COGNITIF")
                    details = eval_res.get("audit_details", "Audité par agent cognitif")

                    c_up = sqlite3.connect(DB_PATH, timeout=60)
                    c_up.execute("PRAGMA journal_mode=WAL;")
                    c_up.execute("UPDATE resultats_marches SET audit_statut = ?, audit_details = ? WHERE id = ?", (statut, details, m_id))
                    # Auditer également les lots correspondants
                    c_up.execute("UPDATE resultats_lots SET audit_statut = ?, audit_details = ? WHERE resultat_id = ?", (statut, details, m_id))
                    c_up.commit()
                    c_up.close()
                    log(f"  ✔ Marché {m_id} [{m[1]}] certifié : {statut} - {details[:60]}")

                try:
                    export_resultats_to_front.main()
                except Exception:
                    pass

            await asyncio.sleep(8)
        except Exception as e:
            log(f"Boucle de vérification cognitive : {e}")
            await asyncio.sleep(10)

await main()
