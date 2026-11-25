#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database_schema.py
==================
Initialisation de la base de données SQLite pour stocker les annonces de marchés publics
extraites du Quotidien des Marchés Publics (DGCMEF - Burkina Faso).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("marches_publics_burkina.db")

SCHEMA_SQL = """
-- Table principale des annonces d'appels d'offres
CREATE TABLE IF NOT EXISTS annonces_avis (
    id TEXT PRIMARY KEY,                       -- ex: Quotidien_N4532_avis_001
    source_file TEXT,                          -- Chemin du fichier .md
    numero_bulletin TEXT,                      -- ex: Quotidien N°4532
    date_parution TEXT,                        -- ex: Lundi 16 novembre 2026
    pages TEXT,                                -- ex: p. 30 ou p. 32 à 33
    categorie_marche TEXT,                     -- Travaux, Fournitures, Prestations...
    type_procedure TEXT,                       -- Demande de prix, Appel d'offres ouvert...
    reference_dossier TEXT,                    -- Référence administrative officielle
    autorite_contractante TEXT,                -- Autorité émettrice / Contractante
    ministere_tutelle TEXT,                    -- Ministère de tutelle ou Institution
    objet_marche TEXT,                         -- Intitulé exhaustif de la commande
    allotissement_type TEXT,                   -- Lot unique / Lots multiples
    nombre_lots INTEGER,                       -- Décompte des lots
    budget_previsionnel_fcfa INTEGER,          -- Montant en chiffres FCFA
    garantie_soumission_fcfa INTEGER,          -- Caution financière exigée
    cout_acquisition_dossier_fcfa INTEGER,     -- Frais de retrait du DAO
    source_financement TEXT,                   -- Budget État, Budget BYM, Banque Mondiale...
    exercice_budgetaire TEXT,                  -- 2026
    date_limite_depot TEXT,                    -- JJ/MM/AAAA
    heure_limite_depot TEXT,                   -- HH:MM TU
    delai_execution_jours INTEGER,             -- Délai de réalisation (en jours)
    delai_validite_offres_jours INTEGER,       -- Délai d'engagement (en jours)
    lieu_depot_offres TEXT,                    -- Bureau / Secrétariat où déposer
    date_heure_ouverture_plis TEXT,            -- Date & heure d'ouverture publique
    lieu_ouverture_plis TEXT,                  -- Salle / Direction d'ouverture
    marche_reserve TEXT,                       -- Réservé aux PME / moyennes entreprises...
    qualifications_ou_agrement TEXT,           -- Agréments requis ou DPAO
    contacts_renseignements TEXT,              -- BP, Téléphone, Email
    signataire_nom_fonction TEXT,              -- Signataire / Titre (Président CAM...)
    remarque TEXT,                             -- Contrôle qualité / Notes libres
    secteur_activite TEXT,                     -- Secteur d'activité métier (BTP, Santé, Informatique...)
    json_brut TEXT,                            -- Payload JSON brut complet extrait
    date_extraction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table secondaire pour les détails des lots en cas d'allotissement multiple
CREATE TABLE IF NOT EXISTS detail_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annonce_id TEXT,
    numero_lot TEXT,                           -- ex: Lot 1, Lot 2
    titre TEXT,                                -- Titre du lot
    description TEXT,                          -- Détail des prestations
    montant_fcfa INTEGER,                      -- Montant alloué au lot
    caution_fcfa INTEGER,                      -- Caution exigée pour ce lot
    FOREIGN KEY(annonce_id) REFERENCES annonces_avis(id) ON DELETE CASCADE
);

-- ============================================================================
-- NOUVELLES TABLES : SECTION RÉSULTATS PROVISOIRES & SUIVI DES CANDIDATS
-- ============================================================================

-- 1. Table des marchés attribués / résultats provisoires
CREATE TABLE IF NOT EXISTS resultats_marches (
    id TEXT PRIMARY KEY,                       -- ex: Quotidien_N4536_res_001
    bulletin TEXT,                             -- ex: Quotidien N°4536
    date_parution TEXT,                        -- ex: 20/11/2026
    pages TEXT,                                -- ex: p. 5
    autorite_contractante TEXT,                -- Nom canonique de l'émetteur
    reference_dossier TEXT,                    -- Référence du dossier (ex: N°001/2026/PDP/DIS)
    reference_normalisee TEXT,                 -- Référence épurée pour matching automatique
    annonce_avis_id TEXT,                      -- Clé étrangère vers annonces_avis(id) si matché
    objet TEXT,                                -- Objet du marché
    secteur_activite TEXT,                     -- Secteur métier (13 secteurs)
    financement TEXT,                          -- Source de financement
    methode_selection TEXT,                    -- Qualité-Coût, Moindre Coût, Qualifications, etc.
    score_technique_min_requis REAL,           -- Note technique éliminatoire (ex: 70 ou 75 pts)
    decision_arcop_ref TEXT,                   -- Référence de décision ARCOP si contentieux/recours
    est_rectificatif BOOLEAN DEFAULT 0,        -- 1 si synthèse rectificative / erratum
    date_depouillement TEXT,                   -- JJ/MM/AAAA
    date_deliberation TEXT,                    -- JJ/MM/AAAA
    nombre_lots INTEGER DEFAULT 1,             -- Nombre de lots
    budget_previsionnel_min_fcfa INTEGER,      -- Montant prévisionnel Min
    budget_previsionnel_max_fcfa INTEGER,      -- Montant prévisionnel Max
    source_file TEXT,                          -- Fichier d'origine
    json_brut TEXT,                            -- Payload JSON complet
    date_extraction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(annonce_avis_id) REFERENCES annonces_avis(id) ON DELETE SET NULL
);

-- 2. Table des lots et des seuils Min/Max de régulation
CREATE TABLE IF NOT EXISTS resultats_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resultat_id TEXT,
    numero_lot INTEGER,                        -- 1, 2, ...
    intitule_lot TEXT,                         -- Titre du lot
    nombre_plis_recus INTEGER,                 -- Nombre exact de plis reçus
    budget_lot_min_fcfa INTEGER,               -- Budget min du lot
    budget_lot_max_fcfa INTEGER,               -- Budget max du lot
    moyenne_offres_fcfa INTEGER,               -- Moyenne arithmétique M des offres
    borne_inf_basse_fcfa INTEGER,              -- Borne inférieure / anormalement basse
    seuil_tolerance_5pct_fcfa INTEGER,         -- Seuil de tolérance (ex: -5% de borne basse)
    borne_sup_elevee_fcfa INTEGER,             -- Borne supérieure / anormalement élevée
    attributaire_nom TEXT,                     -- Entreprise gagnante
    montant_attribue_min_fcfa INTEGER,         -- Montant minimum retenu (TTC)
    montant_attribue_max_fcfa INTEGER,         -- Montant maximum retenu (TTC)
    delai_execution TEXT,                      -- Délai d'exécution contractualisé
    est_infructueux BOOLEAN DEFAULT 0,         -- 1 si infructueux, 0 sinon
    motif_infructueux TEXT,                    -- Raison officielle de l'échec
    FOREIGN KEY(resultat_id) REFERENCES resultats_marches(id) ON DELETE CASCADE
);

-- 3. Table des soumissionnaires et des offres proposées (Min/Max, Lu/Corrigé)
CREATE TABLE IF NOT EXISTS resultats_soumissionnaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resultat_id TEXT,
    lot_id INTEGER,
    nom_soumissionnaire TEXT,                  -- Nom tel qu'écrit dans le PV
    nom_canonique TEXT,                        -- Nom nettoyé pour agrégat CRM
    ifu TEXT,                                  -- Identifiant Financier Unique
    rccm TEXT,                                 -- Registre du Commerce et du Crédit Mobilier
    telephone TEXT,                            -- Numéros de contact
    email TEXT,                                -- Email de contact
    adresse_bp TEXT,                           -- Boîte postale et ville
    score_technique REAL,                      -- Note technique obtenue sur 100
    est_groupement BOOLEAN DEFAULT 0,          -- 1 si groupement d'entreprises
    membres_groupement TEXT,                   -- Détail des entreprises co-traitantes
    montant_lu_htva_min INTEGER,               -- Offre lue publiquement HTVA Min
    montant_lu_htva_max INTEGER,               -- Offre lue publiquement HTVA Max
    montant_lu_ttc_min INTEGER,                -- Offre lue publiquement TTC Min
    montant_lu_ttc_max INTEGER,                -- Offre lue publiquement TTC Max
    montant_corrige_htva_min INTEGER,          -- Offre corrigée HTVA Min
    montant_corrige_htva_max INTEGER,          -- Offre corrigée HTVA Max
    montant_corrige_ttc_min INTEGER,           -- Offre corrigée TTC Min
    montant_corrige_ttc_max INTEGER,           -- Offre corrigée TTC Max
    conformite TEXT,                           -- Conforme | Non conforme
    classement TEXT,                           -- 1er, 2ème, Non classé
    rang_numerique INTEGER,                    -- 1, 2, ...
    est_attributaire BOOLEAN DEFAULT 0,        -- 1 si retenu, 0 sinon
    categorie_rejet TEXT,                      -- OFFRE_ANORMALEMENT_BASSE | TECHNIQUE | ADMINISTRATIF | FINANCIER
    observations_motifs TEXT,                  -- Motif de rejet ou observation de conformité
    FOREIGN KEY(resultat_id) REFERENCES resultats_marches(id) ON DELETE CASCADE,
    FOREIGN KEY(lot_id) REFERENCES resultats_lots(id) ON DELETE CASCADE
);

-- Index pour accélérer les requêtes métiers
CREATE INDEX IF NOT EXISTS idx_annonces_date_parution ON annonces_avis(date_parution);
CREATE INDEX IF NOT EXISTS idx_annonces_date_limite ON annonces_avis(date_limite_depot);
CREATE INDEX IF NOT EXISTS idx_annonces_autorite ON annonces_avis(autorite_contractante);
CREATE INDEX IF NOT EXISTS idx_annonces_budget ON annonces_avis(budget_previsionnel_fcfa);
CREATE INDEX IF NOT EXISTS idx_annonces_categorie ON annonces_avis(categorie_marche);
CREATE INDEX IF NOT EXISTS idx_annonces_secteur ON annonces_avis(secteur_activite);
CREATE INDEX IF NOT EXISTS idx_detail_lots_annonce ON detail_lots(annonce_id);
CREATE INDEX IF NOT EXISTS idx_res_marches_ref ON resultats_marches(reference_normalisee);
CREATE INDEX IF NOT EXISTS idx_res_marches_aut ON resultats_marches(autorite_contractante);
CREATE INDEX IF NOT EXISTS idx_res_marches_annonce ON resultats_marches(annonce_avis_id);
CREATE INDEX IF NOT EXISTS idx_res_soum_nom ON resultats_soumissionnaires(nom_canonique);
CREATE INDEX IF NOT EXISTS idx_res_soum_attributaire ON resultats_soumissionnaires(est_attributaire);
"""

def init_database(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print(f"[OK] Base de données initialisée avec succès : {db_path.resolve()}")

if __name__ == "__main__":
    init_database()
