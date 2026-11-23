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

-- Index pour accélérer les requêtes métiers
CREATE INDEX IF NOT EXISTS idx_annonces_date_parution ON annonces_avis(date_parution);
CREATE INDEX IF NOT EXISTS idx_annonces_date_limite ON annonces_avis(date_limite_depot);
CREATE INDEX IF NOT EXISTS idx_annonces_autorite ON annonces_avis(autorite_contractante);
CREATE INDEX IF NOT EXISTS idx_annonces_budget ON annonces_avis(budget_previsionnel_fcfa);
CREATE INDEX IF NOT EXISTS idx_annonces_categorie ON annonces_avis(categorie_marche);
CREATE INDEX IF NOT EXISTS idx_annonces_secteur ON annonces_avis(secteur_activite);
CREATE INDEX IF NOT EXISTS idx_detail_lots_annonce ON detail_lots(annonce_id);
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
