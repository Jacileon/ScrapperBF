#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/db.py
=============
Accès partagé à la base SQLite. Réutilise la base métier existante
(marches_publics_burkina.db) et y ajoute les tables SaaS.
"""

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from backend.config import DB_PATH


def get_db() -> sqlite3.Connection:
    """Connexion SQLite avec Row factory et clés étrangères activées."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor(commit: bool = False) -> Iterator[sqlite3.Cursor]:
    """Context manager : ouvre une connexion, fournit un curseur, ferme proprement."""
    conn = get_db()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schéma des tables SaaS (idempotent)
# ---------------------------------------------------------------------------
SAAS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,                 -- gratuit | pro | entreprise
    nom TEXT NOT NULL,
    sous_titre TEXT,
    prix_mensuel_fcfa INTEGER NOT NULL DEFAULT 0,
    prix_annuel_fcfa INTEGER NOT NULL DEFAULT 0,
    features_json TEXT NOT NULL DEFAULT '{}',
    ordre INTEGER NOT NULL DEFAULT 0,
    actif INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nom TEXT,
    organisation TEXT,
    telephone TEXT,
    plan_id TEXT NOT NULL DEFAULT 'gratuit',
    role TEXT NOT NULL DEFAULT 'user',   -- user | admin
    email_verifie INTEGER NOT NULL DEFAULT 0,
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(plan_id) REFERENCES plans(id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'active',  -- active | pending | expiree | annulee
    cycle TEXT NOT NULL DEFAULT 'mensuel',  -- mensuel | annuel
    debut TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fin TIMESTAMP,
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(plan_id) REFERENCES plans(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subscription_id INTEGER,
    plan_id TEXT,
    cycle TEXT,
    montant_fcfa INTEGER NOT NULL DEFAULT 0,
    provider TEXT,                          -- sandbox | manual | cinetpay | ...
    operateur TEXT,                         -- orange | moov | carte
    telephone TEXT,
    reference_interne TEXT UNIQUE,          -- notre identifiant de transaction
    reference_externe TEXT,                 -- identifiant renvoyé par l'agrégateur
    statut TEXT NOT NULL DEFAULT 'pending', -- pending | paye | echec | annule
    payload_json TEXT,
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    maj_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(subscription_id) REFERENCES subscriptions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS usage_counters (
    user_id INTEGER NOT NULL,
    periode TEXT NOT NULL,                  -- AAAA-MM-JJ (quotas journaliers) ou AAAA-MM
    compteur_recherches INTEGER NOT NULL DEFAULT 0,
    compteur_fiches INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, periode),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    cle_hash TEXT NOT NULL UNIQUE,
    prefixe TEXT NOT NULL,                  -- début lisible de la clé (ex: vbf_live_ab12)
    label TEXT,
    actif INTEGER NOT NULL DEFAULT 1,
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    derniere_utilisation TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    member_user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'membre',    -- membre | admin
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_user_id, member_user_id),
    FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(member_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Favoris : marchés suivis par un utilisateur (socle de l'alerte résultat).
CREATE TABLE IF NOT EXISTS suivis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    avis_id TEXT NOT NULL,                   -- référence annonces_avis(id)
    statut TEXT NOT NULL DEFAULT 'suivi',    -- suivi | je_soumissionne | abandonne
    note TEXT,
    scoring_snapshot_json TEXT,              -- réservé (débrief vs estimation future)
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, avis_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Notifications (alerte « boucle fermée » : marché suivi attribué, etc.).
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,                      -- resultat | ...
    avis_id TEXT,
    resultat_id TEXT,
    titre TEXT,
    message TEXT,
    payload_json TEXT,
    lu INTEGER NOT NULL DEFAULT 0,
    cree_le TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_ref ON payments(reference_interne);
CREATE INDEX IF NOT EXISTS idx_apikeys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_suivis_user ON suivis(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, lu);
CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_unique ON notifications(user_id, type, resultat_id);
"""


def init_saas_schema(conn: sqlite3.Connection | None = None) -> None:
    """Crée les tables SaaS si absentes (idempotent)."""
    own = conn is None
    if own:
        conn = get_db()
    try:
        conn.executescript(SAAS_SCHEMA_SQL)
        conn.commit()
    finally:
        if own:
            conn.close()
