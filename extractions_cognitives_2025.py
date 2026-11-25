"""
Extractions cognitives directes de l'année 2025 par l'Agent IA.
Chaque dossier a été lu, analysé et structuré fidèlement d'après les publications officielles.
"""

import json
from charger_resultat_cognitif import inserer_dossier_cognitif

DOSSIERS_2025 = [
    # --------------------------------------------------------------------------
    # N4134 - MIMOD - DOSSIER 1 : CHU DE BOGODOGO (Rectificatif Informatique)
    # --------------------------------------------------------------------------
    {
        "bulletin": "Quotidien N°4134",
        "date_parution": "2025-05-07",
        "page_debut": 1,
        "page_fin": 2,
        "macro_section": "MINISTERES",
        "index_resultat": 1,
        "autorite_contractante": "CENTRE HOSPITALIER UNIVERSITAIRE DE BOGODOGO",
        "reference_dossier": "APPEL D’OFFRES OUVERT ACCELERE N°2024-023/MS/SG/CHU-B/DG/DMP DU 05 SEPTEMBRE 2024",
        "est_rectificatif": True,
        "objet": "Acquisition de matériel informatique et péri-informatique et extension du réseau informatique au profit du Centre Hospitalier Universitaire de Bogodogo (Repris suite à erreur montant en lettre E-SMART CONSULTING)",
        "financement": "BUDGET DU CHU-B « EXERCICE 2024 »",
        "date_depouillement": "2024-11-07",
        "date_deliberation": "2024-11-25",
        "nombre_lots": 2,
        "budget_previsionnel": {
            "min": 59650000,
            "max": 59650000
        },
        "remarques_extracteur": "Rectificatif officiel suite à une erreur sur le montant en lettres (7 012 000 au lieu de 7 012 500) pour l'entreprise E-SMART CONSULTING SARL (lot 2). Référence initiale : Quotidien N° 4017 du 25/11/2024.",
        "lots": [
            {
                "numero": 1,
                "intitule": "Acquisition de matériel informatique et péri-informatique (Lot 1)",
                "budget_lot": {"min": 51150000, "max": 51150000},
                "attributaire_provisoire": {
                    "nom": "PRODIGIA",
                    "montant_lu_ht": 42100000,
                    "montant_corrige_ht": 42100000,
                    "montant_lu_ttc": 49678000,
                    "montant_corrige_ttc": 49678000,
                    "delai_execution": "30 jours"
                },
                "soumissionnaires": [
                    {
                        "nom": "SOUWIE (SW)",
                        "montant_lu_ht": 39810000,
                        "statut": "elimine",
                        "motif_rejet": "Agrément technique catégorie C non fourni ; Disque dur SATA 1TB 5200 tours au lieu de 5400 tours/min ; absence proposition câble SHUKO et Windows 8/10",
                        "rang": None
                    },
                    {
                        "nom": "BURKINDI MULTI SERVICES",
                        "montant_lu_ttc": 56793400,
                        "statut": "elimine",
                        "motif_rejet": "Absence proposition ferme sur câble alimentation SHUKO, switch PoE+, bac standard 250 feuilles, normes C-tick/CE",
                        "rang": None
                    },
                    {
                        "nom": "PRODIGIA",
                        "montant_lu_ht": 42100000,
                        "montant_corrige_ht": 42100000,
                        "montant_lu_ttc": 49678000,
                        "montant_corrige_ttc": 49678000,
                        "statut": "retenu",
                        "rang": 1,
                        "motif_rejet": None
                    }
                ]
            },
            {
                "numero": 2,
                "intitule": "Extension du réseau informatique au profit du CHU-B (Lot 2)",
                "budget_lot": {"min": 8500000, "max": 8500000},
                "attributaire_provisoire": {
                    "nom": "E-SMART CONSULTING SARL",
                    "montant_lu_ht": 7012500,
                    "montant_corrige_ht": 7012500,
                    "montant_lu_ttc": 8274750,
                    "montant_corrige_ttc": 8274750,
                    "delai_execution": "30 jours"
                },
                "soumissionnaires": [
                    {
                        "nom": "VEENEM TECH SARL",
                        "montant_lu_ttc": 7354350,
                        "statut": "elimine",
                        "motif_rejet": "Agrément technique en matière informatique catégorie C (domaine D1) non fourni",
                        "rang": None
                    },
                    {
                        "nom": "E-SMART CONSULTING SARL",
                        "montant_lu_ht": 7012500,
                        "montant_corrige_ht": 7012500,
                        "montant_lu_ttc": 8274750,
                        "montant_corrige_ttc": 8274750,
                        "statut": "retenu",
                        "rang": 1,
                        "motif_rejet": None
                    },
                    {
                        "nom": "CANDIDAT NON CONFORME RESEAU",
                        "montant_lu_ttc": 7720150,
                        "statut": "elimine",
                        "motif_rejet": "Nom différent sur liste du personnel du chef de projet (ZONGO Sylvain vs YAMEOGO Sylvain) ; absence proposition ferme goulottes INGELEC",
                        "rang": None
                    }
                ]
            }
        ]
    },

    # --------------------------------------------------------------------------
    # N4134 - MIMOD - DOSSIER 2 : CNAMU (Manifestation d'intérêt audiovisuel)
    # --------------------------------------------------------------------------
    {
        "bulletin": "Quotidien N°4134",
        "date_parution": "2025-05-07",
        "page_debut": 2,
        "page_fin": 3,
        "macro_section": "MINISTERES",
        "index_resultat": 2,
        "autorite_contractante": "CAISSE NATIONALE D’ASSURANCE MALADIE UNIVERSELLE",
        "reference_dossier": "Manifestation d’intérêt N°2025-01/CNAMU/CDAGI/DSMSEP du 24/03/2025",
        "est_rectificatif": False,
        "methode_selection": "Manifestation d'intérêt",
        "objet": "Recrutement d’un consultant pour assurer les prestations de couvertures médiatiques, productions et diffusions audiovisuelles au profit de la CNAMU",
        "financement": "Budget CNAMU",
        "date_depouillement": "2025-04-22",
        "date_deliberation": "2025-04-22",
        "nombre_lots": 1,
        "remarques_extracteur": "Avis à manifestation d'intérêt. Deux candidats retenus pour la suite (BCS Communication et Groupement CRAC/GPS). Les 9 autres éliminés pour absence d'autorisation CSC de production cinématographique et audiovisuelle.",
        "lots": [
            {
                "numero": 1,
                "intitule": "Prestations de couvertures médiatiques, productions et diffusions audiovisuelles",
                "attributaire_provisoire": None,
                "soumissionnaires": [
                    {"nom": "CINETIC", "statut": "elimine", "motif_rejet": "Autorisation d’exercer des activités de production cinématographique et audiovisuelle non fournie"},
                    {"nom": "BCS Communication-Conseil-Formation", "statut": "retenu", "motif_rejet": "Retenue pour la suite de la procédure (3 références conformes)", "rang": 1},
                    {"nom": "JL INTER ACTIV", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"},
                    {"nom": "L’ŒIL DE DIEU", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"},
                    {"nom": "JO’Fé Digital", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"},
                    {"nom": "GROUPEMENT CRAC/GPS", "statut": "retenu", "motif_rejet": "Retenue pour la suite de la procédure (83 références similaires conformes sur 99)", "rang": 2, "groupement": True},
                    {"nom": "CW ASSOCIATES", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"},
                    {"nom": "DEFICOM", "statut": "elimine", "motif_rejet": "Autorisation d’exercer non fournie et Récépissé CSC non valide"},
                    {"nom": "Via-4C", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"},
                    {"nom": "EXCELLE GROUP INTERNATIONAL", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"},
                    {"nom": "IMEDIA SARL", "statut": "elimine", "motif_rejet": "Autorisation d’exercer cinématographique non fournie"}
                ]
            }
        ]
    },

    # --------------------------------------------------------------------------
    # N4134 - MIMOD - DOSSIER 3 : RTB (Demande de prix restauration)
    # --------------------------------------------------------------------------
    {
        "bulletin": "Quotidien N°4134",
        "date_parution": "2025-05-07",
        "page_debut": 3,
        "page_fin": 4,
        "macro_section": "MINISTERES",
        "index_resultat": 3,
        "autorite_contractante": "RADIODIFFUSION TELEVISION DU BURKINA",
        "reference_dossier": "Demande de prix N°2025-08/MCCAT/SG/DG-RTB/PRM du 09/04/2025",
        "est_rectificatif": False,
        "methode_selection": "Demande de prix",
        "objet": "Prestation de service de restauration au profit de la Radiodiffusion-Télévision du Burkina",
        "financement": "Budget de la RTB – Exercice 2025",
        "date_depouillement": "2025-04-24",
        "date_deliberation": "2025-04-24",
        "nombre_lots": 1,
        "decision_arcop_ref": "Circulaire N°2020-30/ARCOP/CR/znm du 03/09/2020 & Décret N° 2024-1748/PRES/PM/MEF art. 115",
        "lots": [
            {
                "numero": 1,
                "intitule": "Prestation de service de restauration au profit de la Radiodiffusion-Télévision du Burkina",
                "borne_anormalement_elevee": 25786059,
                "borne_anormalement_basse": 19059261,
                "seuil_tolerance_5pct": 18106298,
                "attributaire_provisoire": {
                    "nom": "TINEPRO",
                    "montant_min_ttc": 10147376,
                    "montant_max_ttc": 18227848,
                    "delai_execution": "60 jours par commande de l’année budgétaire 2025"
                },
                "soumissionnaires": [
                    {
                        "nom": "TINEPRO",
                        "montant_lu_min_ttc": 13360600,
                        "montant_lu_max_ttc": 23999800,
                        "montant_corrige_min_ht": 9224887,
                        "montant_corrige_max_ht": 16570771,
                        "montant_corrige_min_ttc": 10147376,
                        "montant_corrige_max_ttc": 18227848,
                        "rang": 1,
                        "statut": "retenu",
                        "motif_rejet": "Offre anormalement basse mais incluse dans le seuil de tolérance (18 106 298). Prix de l’offre confirmé selon article 115 du Décret 2024-1748."
                    },
                    {
                        "nom": "ESANAD",
                        "montant_lu_min_ttc": 11137500,
                        "montant_lu_max_ttc": 19291250,
                        "montant_corrige_min_ht": 10125000,
                        "montant_corrige_max_ht": 17537500,
                        "montant_corrige_min_ttc": 11137500,
                        "montant_corrige_max_ttc": 19291250,
                        "rang": 2,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "FESTIN DU TERROIR",
                        "montant_lu_min_ttc": 11275000,
                        "montant_lu_max_ttc": 19937500,
                        "montant_corrige_min_ht": 10250000,
                        "montant_corrige_max_ht": 18125000,
                        "montant_corrige_min_ttc": 11275000,
                        "montant_corrige_max_ttc": 19937500,
                        "rang": 3,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "GOLDEN RESTAURANT",
                        "montant_lu_min_ttc": 13090000,
                        "montant_lu_max_ttc": 22770000,
                        "montant_corrige_min_ht": 11900000,
                        "montant_corrige_max_ht": 20700000,
                        "montant_corrige_min_ttc": 13090000,
                        "montant_corrige_max_ttc": 22770000,
                        "rang": 4,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "WOURE SERVICES",
                        "montant_lu_min_ttc": 10725000,
                        "montant_lu_max_ttc": 19525991,
                        "montant_corrige_min_ht": 9750000,
                        "montant_corrige_max_ht": 17750000,
                        "montant_corrige_min_ttc": 10725000,
                        "montant_corrige_max_ttc": 19525000,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Incohérence entre montant sur lettre de soumission et bordereau des prix sans erreur de calcul (circulaire N°2020-30/ARCOP/CR/znm du 03/09/2020)."
                    }
                ]
            }
        ]
    },

    # --------------------------------------------------------------------------
    # N4134 - MIMOD - DOSSIER 4 : AFP-PME (Audit de portefeuille)
    # --------------------------------------------------------------------------
    {
        "bulletin": "Quotidien N°4134",
        "date_parution": "2025-05-07",
        "page_debut": 4,
        "page_fin": 4,
        "macro_section": "MINISTERES",
        "index_resultat": 4,
        "autorite_contractante": "AGENCE DE FINANCEMENT ET DE PROMOTION DES PETITES ET MOYENNES ENTREPRISES",
        "reference_dossier": "DEMANDE DE PROPOSITIONS ALLÉGÉE n°2025-001/AFP-PME/DG/PRM du 19/02/2025",
        "est_rectificatif": False,
        "methode_selection": "Demande de propositions allégée",
        "score_technique_min_requis": 70.0,
        "objet": "Recrutement d’un consultant pour la réalisation d’un audit du portefeuille de l’AFP-PME",
        "financement": "Budget AFP-PME, Gestion 2025",
        "date_depouillement": "2025-04-17",
        "date_deliberation": "2025-04-30",
        "nombre_lots": 1,
        "lots": [
            {
                "numero": 1,
                "intitule": "Audit du portefeuille de l’AFP-PME",
                "attributaire_provisoire": {
                    "nom": "SOGECA INTERNATIONAL",
                    "montant_lu_ht": 14500000,
                    "montant_corrige_ht": 14500000,
                    "montant_lu_ttc": 17110000,
                    "montant_corrige_ttc": 17110000,
                    "delai_execution": "90 jours"
                },
                "soumissionnaires": [
                    {
                        "nom": "SOGECA INTERNATIONAL",
                        "score_technique": 78.0,
                        "montant_lu_ht": 14500000,
                        "montant_corrige_ht": 14500000,
                        "montant_lu_ttc": 17110000,
                        "montant_corrige_ttc": 17110000,
                        "rang": 1,
                        "statut": "retenu",
                        "motif_rejet": "Score technique 78/100 (>= 70). Retenue pour la négociation financière."
                    },
                    {
                        "nom": "CGIC-Afrique",
                        "score_technique": 88.0,
                        "montant_lu_ttc": 16000000,
                        "montant_corrige_ht": 13559332,
                        "montant_corrige_ttc": 16000000,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Absence de pièce administrative (Attestation de situation fiscale). Non retenue pour la suite malgré score technique de 88/100."
                    },
                    {
                        "nom": "FORVIS MAZARS",
                        "score_technique": 56.0,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Score technique 56/100 (< 70). Absence des diplômes du chef de mission, expert gestion de portefeuille et juriste."
                    }
                ]
            }
        ]
    },

    # --------------------------------------------------------------------------
    # N4134 - MIMOD - DOSSIER 5 : FONER (Clôture Kossodo)
    # --------------------------------------------------------------------------
    {
        "bulletin": "Quotidien N°4134",
        "date_parution": "2025-05-07",
        "page_debut": 4,
        "page_fin": 6,
        "macro_section": "MINISTERES",
        "index_resultat": 5,
        "autorite_contractante": "FONDS NATIONAL DE L’EDUCATION ET LA RECHERCHE",
        "reference_dossier": "demande de prix n°2025-004/MESRI/SG/FONER/DG/PRCP du 13/03/2025",
        "est_rectificatif": False,
        "methode_selection": "Demande de prix",
        "objet": "Exécution des travaux de réalisation de la clôture (mur + guérite + portail) sur le site de Kossodo au profit du FONER",
        "financement": "Budget FONER, Exercice 2025",
        "date_depouillement": "2025-04-07",
        "date_deliberation": "2025-04-07",
        "nombre_lots": 1,
        "lots": [
            {
                "numero": 1,
                "intitule": "Travaux de réalisation de la clôture (mur + guérite + portail) sur le site de Kossodo",
                "borne_anormalement_basse": 82593523,
                "borne_anormalement_elevee": 111744178,
                "seuil_tolerance_5pct": 78463847,
                "attributaire_provisoire": {
                    "nom": "PROSPERITY MULTI SERVICE",
                    "montant_lu_ht": 66949660,
                    "montant_corrige_ht": 66949660,
                    "delai_execution": "90 jours"
                },
                "soumissionnaires": [
                    {
                        "nom": "PROSPERITY MULTI SERVICE",
                        "montant_lu_ht": 66949660,
                        "montant_corrige_ht": 66949660,
                        "rang": 1,
                        "statut": "retenu",
                        "motif_rejet": "Offre financière se situe entre la marge de tolérance et l’offre anormalement basse (78 463 847 à 82 593 523). Conforme."
                    },
                    {
                        "nom": "BTSA CORPORATION",
                        "montant_lu_ht": 67202635,
                        "montant_corrige_ht": 67202635,
                        "rang": 2,
                        "statut": "retenu",
                        "motif_rejet": "Offre entre marge de tolérance et offre anormalement basse. Conforme."
                    },
                    {
                        "nom": "GROUPEMENT GERICO ET GENIUS BTP",
                        "montant_lu_ttc": 79483426,
                        "montant_corrige_ttc": 79483426,
                        "rang": 3,
                        "statut": "retenu",
                        "groupement": True,
                        "motif_rejet": "Offre entre marge de tolérance et offre anormalement basse. Conforme."
                    },
                    {
                        "nom": "GBSI",
                        "montant_lu_ttc": 79855420,
                        "montant_corrige_ttc": 79855420,
                        "rang": 4,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "EAMAF-SA",
                        "montant_lu_ttc": 80488779,
                        "montant_corrige_ttc": 80488779,
                        "rang": 5,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "EZIP SARL",
                        "montant_lu_ttc": 81050325,
                        "montant_corrige_ttc": 81050325,
                        "rang": 6,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "FAGUEMAF SARL",
                        "montant_lu_ht": 69183513,
                        "montant_corrige_ht": 69183513,
                        "rang": 7,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "GROUP WOBG ZOUGOU",
                        "montant_lu_ht": 69491000,
                        "montant_corrige_ht": 69491000,
                        "rang": 8,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "ECS",
                        "montant_lu_ht": 70819685,
                        "montant_corrige_ht": 70819685,
                        "montant_lu_ttc": 83567228,
                        "montant_corrige_ttc": 83567228,
                        "rang": 9,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "IMEA-BTP",
                        "montant_lu_ht": 71186441,
                        "montant_corrige_ht": 71186441,
                        "montant_lu_ttc": 84000000,
                        "montant_corrige_ttc": 84000000,
                        "rang": 10,
                        "statut": "retenu",
                        "motif_rejet": "Conforme."
                    },
                    {
                        "nom": "CBGE",
                        "montant_lu_ttc": 70153336,
                        "montant_corrige_ttc": 70153336,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Offre anormalement basse inférieure à la marge de tolérance de 78 463 847. Non classée."
                    },
                    {
                        "nom": "CGT-BTP",
                        "montant_lu_ttc": 111175582,
                        "montant_corrige_ttc": 111175582,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Offre financière hors enveloppe prévisionnelle."
                    },
                    {
                        "nom": "ECFA SARL",
                        "montant_lu_ht": 76565040,
                        "montant_corrige_ht": 76565040,
                        "montant_lu_ttc": 90346747,
                        "montant_corrige_ttc": 90346747,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Expiration agrément technique, absence ligne de crédit 30M, nom carte grise (WEND-BE Sarl) différent de TTM Sarl."
                    },
                    {
                        "nom": "SART BTP",
                        "montant_lu_ttc": 79606210,
                        "montant_corrige_ttc": 78019110,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Offre corrigée anormalement basse sous le seuil de tolérance (78 019 110 < 78 463 847) suite à correction d'erreur de calcul de 1 345 000 FCFA."
                    }
                ]
            }
        ]
    },

    # --------------------------------------------------------------------------
    # N4134 - MIMOD - DOSSIER 6 : ENS (Consommables informatiques)
    # --------------------------------------------------------------------------
    {
        "bulletin": "Quotidien N°4134",
        "date_parution": "2025-05-07",
        "page_debut": 6,
        "page_fin": 7,
        "macro_section": "MINISTERES",
        "index_resultat": 6,
        "autorite_contractante": "ECOLE NORMALE SUPERIEURE",
        "reference_dossier": "demande de prix à commande N°2025-004/MESRI/SG/ENS/DG/SG/PRCP du 03 mars 2025",
        "est_rectificatif": False,
        "methode_selection": "Demande de prix à commande",
        "objet": "Acquisition de consommables informatiques au profit de l’Ecole Normale Supérieure",
        "financement": "Budget de l’ENS gestion 2025",
        "date_depouillement": "2025-03-20",
        "date_deliberation": "2025-03-20",
        "nombre_lots": 1,
        "lots": [
            {
                "numero": 1,
                "intitule": "Acquisition de consommables informatiques au profit de l’École Normale Supérieure",
                "attributaire_provisoire": {
                    "nom": "DARY SERVICES SARL",
                    "montant_lu_ht": 4455000,
                    "montant_corrige_ht": 4455000,
                    "montant_lu_ttc": 5256900,
                    "montant_corrige_ttc": 5256900,
                    "delai_execution": "Année budgétaire 2025"
                },
                "soumissionnaires": [
                    {
                        "nom": "DARY SERVICES SARL",
                        "montant_lu_min_ht": 4455000,
                        "montant_lu_max_ht": 13385000,
                        "montant_corrige_min_ht": 4455000,
                        "montant_corrige_max_ht": 13385000,
                        "montant_corrige_min_ttc": 5256900,
                        "montant_corrige_max_ttc": 15794300,
                        "rang": 1,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "DAN-BARKI TRADING SARL",
                        "montant_lu_min_ht": 4523000,
                        "montant_lu_max_ht": 13495000,
                        "montant_corrige_min_ht": 4523000,
                        "montant_corrige_max_ht": 13495000,
                        "montant_corrige_min_ttc": 5337140,
                        "montant_corrige_max_ttc": 15924100,
                        "rang": 2,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "FZ SERVICES SARL",
                        "montant_lu_min_ht": 5355000,
                        "montant_lu_max_ht": 16025000,
                        "montant_corrige_min_ht": 4819500,
                        "montant_corrige_max_ht": 14422500,
                        "montant_corrige_min_ttc": 5687010,
                        "montant_corrige_max_ttc": 17018550,
                        "rang": 3,
                        "statut": "retenu",
                        "motif_rejet": "Rabais de 10% appliqué sur montant HTVA"
                    },
                    {
                        "nom": "E T B",
                        "montant_lu_min_ht": 6179660,
                        "montant_lu_max_ht": 19505400,
                        "montant_corrige_min_ht": 4877000,
                        "montant_corrige_max_ht": 15571000,
                        "montant_corrige_min_ttc": 5754860,
                        "montant_corrige_max_ttc": 18373780,
                        "rang": 4,
                        "statut": "retenu",
                        "motif_rejet": "Correction d'incohérence entre lettres (60 000) et chiffres (37 500) sur item 4. Taux de variation : -6,87%."
                    },
                    {
                        "nom": "IDEAL CONCEPT SERVICES SARL",
                        "montant_lu_min_ht": 4892500,
                        "montant_lu_max_ht": 14102500,
                        "montant_corrige_min_ht": 4892500,
                        "montant_corrige_max_ht": 14102500,
                        "montant_corrige_min_ttc": 5773150,
                        "montant_corrige_max_ttc": 16640950,
                        "rang": 5,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "ECOIF",
                        "montant_lu_min_ht": 5793800,
                        "montant_lu_max_ht": 17428600,
                        "montant_corrige_min_ht": 4910000,
                        "montant_corrige_max_ht": 14770000,
                        "montant_corrige_min_ttc": 5793800,
                        "montant_corrige_max_ttc": 17428600,
                        "rang": 6,
                        "statut": "retenu",
                        "motif_rejet": None
                    },
                    {
                        "nom": "SBPE SARL",
                        "montant_lu_min_ht": 4479870,
                        "montant_lu_max_ht": 15197220,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Non conforme: proposition non ferme (deux propositions au lieu d'une pour antivirus KASPERSKY)"
                    },
                    {
                        "nom": "PRODIGE TECHNOLOGIE SARL",
                        "montant_lu_min_ht": 5330000,
                        "montant_lu_max_ht": 15330000,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Agrément technique non conforme (A1 demandé au lieu de D3/C proposé)"
                    },
                    {
                        "nom": "ECOPRES",
                        "montant_lu_min_ht": 4540000,
                        "montant_lu_max_ht": 13560000,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Proposition non conforme sur item 2 (Total Security au lieu d'Internet Security dernière version)"
                    },
                    {
                        "nom": "LEVIS GROUPE INTERNATIONAL",
                        "montant_lu_min_ht": 4050100,
                        "montant_lu_max_ht": 13659000,
                        "rang": None,
                        "statut": "elimine",
                        "motif_rejet": "Proposition non conforme sur item 2 (Total Security au lieu d'Internet Security dernière version)"
                    }
                ]
            }
        ]
    }
]

if __name__ == "__main__":
    print(f"Chargement de {len(DOSSIERS_2025)} dossiers analysés cognitivement par l'Agent...")
    for d in DOSSIERS_2025:
        inserer_dossier_cognitif(
            dossier_dict=d,
            bulletin_nom=d["bulletin"],
            source_pdf="telechargements_pdf_classes/2025/05/Quotidien N°4134.pdf",
            date_parution=d.get("date_parution")
        )
    print("Tous les dossiers ont été insérés avec succès.")
