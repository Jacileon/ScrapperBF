import sqlite3
import extract_and_load_resultats as elr

conn = sqlite3.connect(elr.DB_PATH)
res_id = "Quotidien_N_4306_bis__res_MINISTERE_DE_L_ENSEI_001_01"

lots_data = {
    3275: [  # Lot 24
        ("AMGR MSA", "00282165E", "BF-OUA-01-2025-B13-13487", "70 84 61 59", 1, "Retenu"),
        ("COMPLEXE EBENESER", "00118780N", "BF-BBD-2019-A-0446", "56 57 29 29/70 58 99 59", 1, "Retenu"),
        ("BUREAU AFRICAIN DES SERVICES ET DES ETUDES STRATEGIQUES (BASES)", "00111232U", "BF-OUA-2018-B8248", "25 39 18 29/70 57 19 13/76 68 41 48", 1, "Retenu"),
        ("STRID AGENCE", "00043076B", "BF-KDG2012-A-155", "70 12 39 75/78 11 37 15", 1, "Retenu"),
        ("FREEZIA", "00120569T", "BF-OUA-2019-M6244", "78 62 05 73/56 83 90 30", 1, "Retenu"),
        ("SB", "00155341Z", "BF-OUA-01-2023-M12138", "70 25 44 57/76 24 54 02", 1, "Retenu"),
        ("GOLDEN ASSIST GROUP SARL", "00178973G", "BF-OUA-01-2022-B13-04724", "06 87 87 87/01 87 87 87", 1, "Retenu"),
        ("EKAF BURKINA", "001505552X", "BF OUA2021A0228", "66 30 63 35/70 60 09 97", 1, "Retenu"),
        ("JL-INTERACTIV", "00061051V", "BF OUA 01 2025M08139", "62275350/70284095", 1, "Retenu"),
        ("ZELUS", "00141331F", "BFOUA2020B7126", "63 27 35 93/76 45 02 76", 1, "Retenu"),
        ("SIMUL", "00224248C", "BF OUA 01 2024 B13 01735", "56 61 00 95", 1, "Retenu"),
        ("WECO", "00213012V", "BF-OUA-01-2023-B13-12783", "79 39 60 66", 1, "Retenu"),
        ("IMPRINT", "00177855F", "BFOUA2022B4109", "78 86 73 13", 1, "Retenu"),
        ("IMEDIA", "00105485Y", "BF OUA 2018 B 4145", "78 88 73 13/ 70 27 07 00", 1, "Retenu"),
        ("KADOUM SERVICES SARL", "00229200J", "BF-OUA-01-2024-B13-04299", "70695710/76 11 53 60", 1, "Retenu"),
        ("PAPILLE ET PRESTIGE", "00252442X", "BF-OUA-01-2024-A10-16415", "70 64 33 01/78 19 58 69", 1, "Retenu"),
        ("MINGABA PRESTATION", "00152146E", "BF-OUA-201 B 1381", "74969363/73602678", 1, "Retenu"),
        ("ENTREPRISE SERVICE GENERAL (E.SE.G)", "00048138Z", "BF OUA 2020 M 10592", "78 28 86 98/76 80 29 00", 1, "Retenu"),
        ("SALRAS MULTI SERVICES", "00211324A", "BF OUA 01 2023 B 1211650", "60 19 02 65/77 63 89 89", 1, "Retenu"),
        ("GUESDELA MULTI-SERVICES", "00193000Y", "BF-OUA-01-2022-A10-14638", "76 74 40 57/79 38 20 48", 1, "Retenu"),
        ("SAA YANGUI", "00124228J", "BF OUA 2019 A 6438", "76 61 35 18/58 16 57 62", 1, "Retenu"),
        ("ZEPHYR SARL", "00015204E", "BF OUA 2008 B 390", "78 88 18 18/70 18 0088", 1, "Retenu"),
        ("LANAYA K-SERVICES SARL", "00215712K", "BF-OUA-01-2023-B13-14404", "70 41 90 90 / 55 61 27 62", 1, "Retenu"),
        ("KAMOUF SARL", "00182522X", "BF-OUA-01-2022-B13-7265", "70 00 48 06 /78 84 46 31", 1, "Retenu"),
        ("INITIATIVE & FRANSISE", "00251829H", "BF-BBD-01-2024-A10-02652", "65 65 40 43 / 73 77 11 91", 1, "Retenu"),
    ],
    3276: [  # Lot 25
        ("GROUPE NOUVEL ET SERVICES", "00174254P", "BF OUA 2022B1658", "79087758/78081144", 1, "Retenu"),
        ("UNIVERSAL CHANGE SARL", "000611399D", "BF OUA 2014 B6482", "70221342", 1, "Retenu"),
        ("ZELUS", None, "BFOUA2020B7126", "63 27 35 93/76 45 02 76", 1, "Retenu"),
        ("SIMUL", "00224248C", "BF OUA 01 2024 B13 01735", "56 61 00 95", 1, "Retenu"),
        ("WECO", "00213012V", "BF-OUA-01-2023-B13-12783", "79 39 60 66", 1, "Retenu"),
        ("IMPRINT", "00177855F", "BFOUA2022B4109", "78 86 73 13", 1, "Retenu"),
        ("IMEDIA", "00105485Y", "BF OUA 2018 B 4145", "78 88 73 13/ 70 27 07 00", 1, "Retenu"),
        ("NAKAM SERVICE", "00161502f", "BF-OUA-2021-A7599", "73 85 85 88/78 00 27 78", 1, "Retenu"),
        ("SOG-MANEGRE SERVICE", "00004907N", "BFOUA 2017 M 8442", "76 47 86 31/70 06 40 60", 1, "Retenu"),
        ("KALFALA TRADING", "00241741S", "BF-OUA-01-2024-A10-10630", "70 65 06 58/74 60 14 24", 1, "Retenu"),
        ("SANCFIS", "00003267E", "BF-OUA01-2005-B14-01229", "55 91 91 91/78 91 91 91", 1, "Retenu"),
    ],
    3277: [  # Lot 26
        ("ENTRPRISE ECLAIR", "00081584T", "BF OHG 2016 A 363", "76 02 49 81/ 78 14 25 07", 0, "AGREMENT TECHNIQUE NON FOURNI - Non retenu"),
        ("SIGAZ", "00227756G", "BF OUA 01 2024 B 1303470", "70 20 94 03/68 36 36 56", 0, "AGREMENT TECHNIQUE NON FOURNI - Non retenu"),
        ("ECBA", "00152653H", "BFOUA2021A1742", "70228679/78074883", 1, "AGREMENT TECHNIQUE FOURNI - Retenu"),
        ("MAERI", "00183014T", "BFOUA012022M13655", "70628951/76162695/79647573", 1, "AGREMENT TECHNIQUE FOURNI - Retenu"),
        ("MVI SARL", "00206765K", "BFOUA-01-2023-B13-08752", "70200421", 1, "AGREMENT TECHNIQUE FOURNI - Retenu"),
    ],
    3278: [  # Lot 27
        ("PRODIGIA", "00053410U", "BF OUA 2014 A 0796", "70 22 62 64/ 70 08 00 98", 1, "Retenu"),
        ("PRODITEK", "00203636X", "BF OUA 01 2023 B13 06613", "65 83 22 22/ 78 07 03 08", 1, "Retenu"),
        ("ART TECHNOLOGY SARL", "00073064R", "BF-OUA2016-B1595", "70 21 62 45/25 30 24 85", 1, "Retenu"),
        ("PROTECH SARL", "00100781K", "BF-OUA-01-2018-B13-00942", "70 20 91 92/69 07 68 68", 1, "Retenu"),
        ("FAAB SERVICES", "00283179T", "BF-OUA-01-2025-B13-13949", "70 25 20 88/02 47 47 47", 1, "Retenu"),
        ("AGENCE PRO NET", "00179643M", "BF-OUA-01-2022-B12-5224", "70 25 34 47/77 00 17 15", 1, "Retenu"),
        ("D.COM", "00041688D", "BF OUA 2012 B 4038", "78 87 19 45/ 25 40 93 74", 1, "Retenu"),
        ("BRICK'S SARL", "00212536R", "BF-OUA-01-2023-B13-12-473", "70 11 63 74/78 14 21 81", 1, "Retenu"),
        ("ARNAULD BUREAUTIQUE INFORMATIQUE", "0023565M", "BF-OUA-2009-A4242", "70 24 14 84/78 82 22 12", 1, "Retenu"),
        ("AS EQUIPEMENTS ET TRAVAUX SARL", "00173234C", "BF OUA 01-2022-B12-00918", "66 11 11 80/78 40 91 76", 1, "Retenu"),
        ("LEADER DE COMMERCE DU BURKINA (LCB)", "00115638X", "BF OUA 2019 A 0879", "70 02 26 38/ 78 81 62 01", 1, "Retenu"),
        ("TIPOKO SERVICE DOMA", "00196668K", "BF OUA 2023-M-02995", "78 02 35 95", 1, "Retenu"),
        ("E.G.I.F", "00053126F", "BF OUA 2014 A 0599", "72 30 99 73/78 06 23 46", 1, "Retenu"),
        ("ARIELLE SERVICE ET FRERES", "00130727K", "BF OUA 2020 A 0056", "70 00 56 29/ 78 01 93 55", 1, "Retenu"),
        ("SOCODY SERVICE INTERNATIONAL", "0015128R", "BF OUA 2021 A 0734", "76 39 59 34", 1, "Retenu"),
    ],
}

for lot_id, items in lots_data.items():
    conn.execute("DELETE FROM resultats_soumissionnaires WHERE lot_id = ?", (lot_id,))
    retenus = []
    for nom, ifu, rccm, tel, est_attr, obs in items:
        conn.execute(
            """INSERT INTO resultats_soumissionnaires
            (resultat_id, lot_id, nom_soumissionnaire, ifu, rccm, telephone, est_attributaire, observations_motifs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (res_id, lot_id, nom, ifu, rccm, tel, est_attr, obs),
        )
        if est_attr:
            retenus.append(nom)
    conn.execute("UPDATE resultats_lots SET attributaire_nom = ? WHERE id = ?", (" ; ".join(retenus), lot_id))

conn.commit()
print("Lots 24-27 mis a jour avec succes.")
