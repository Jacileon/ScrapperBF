#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/db.py
=============
Accès partagé à la base. En SaaS/production la base est **Postgres (Supabase)**
via psycopg2 ; une couche de compatibilité expose l'API sqlite3 attendue par les
routers (``conn.execute(sql, params).fetchone()``, lignes façon ``sqlite3.Row``,
placeholders ``?``, ``INSERT OR IGNORE``…), ce qui évite de réécrire chaque requête.

Si ``DATABASE_URL`` est vide, on retombe sur SQLite (dev hors-ligne / pipeline).
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.config import DATABASE_URL, DB_PATH

_USE_PG = bool(DATABASE_URL)
IS_POSTGRES = _USE_PG  # exposé aux routers devant court-circuiter du DDL spécifique SQLite


# ===========================================================================
# Backend Postgres (Supabase) — couche de compatibilité sqlite3
# ===========================================================================
if _USE_PG:
    import psycopg2
    import psycopg2.extensions

    class SqliteRow:
        """Ligne compatible sqlite3.Row : indexation par nom ou position, dict()."""
        __slots__ = ("_keys", "_vals")

        def __init__(self, keys, vals):
            self._keys = keys
            self._vals = vals

        def keys(self):
            return list(self._keys)

        def __getitem__(self, k):
            if isinstance(k, (int, slice)):
                return self._vals[k]
            return self._vals[self._keys.index(k)]

        def get(self, k, default=None):
            try:
                return self[k]
            except (KeyError, ValueError, IndexError):
                return default

        def __iter__(self):
            return iter(self._vals)

        def __len__(self):
            return len(self._vals)

        def __contains__(self, k):
            return k in self._keys

    _RE_IGNORE = re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)

    def _translate(query: str, has_params: bool) -> str:
        q = query
        if "insert or ignore" in q.lower():
            q = _RE_IGNORE.sub("INSERT INTO", q)
            if "on conflict" not in q.lower():
                q = q.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        if has_params:
            # psycopg2 n'interprète les % que si des paramètres sont fournis.
            q = q.replace("%", "%%").replace("?", "%s")
        return q

    class _Cursor(psycopg2.extensions.cursor):
        def execute(self, query, vars=None):
            super().execute(_translate(query, bool(vars)), vars)
            return self

        def _cols(self):
            return [d[0] for d in self.description] if self.description else []

        def fetchone(self):
            row = super().fetchone()
            return SqliteRow(self._cols(), list(row)) if row is not None else None

        def fetchall(self):
            cols = self._cols()
            return [SqliteRow(cols, list(r)) for r in super().fetchall()]

        def fetchmany(self, size=None):
            cols = self._cols()
            rows = super().fetchmany(size) if size is not None else super().fetchmany()
            return [SqliteRow(cols, list(r)) for r in rows]

    class _Conn:
        """Enveloppe psycopg2 offrant l'API sqlite3 utilisée par les routers."""

        def __init__(self, raw):
            self._raw = raw

        def cursor(self):
            return self._raw.cursor()

        def execute(self, query, vars=None):
            cur = self._raw.cursor()
            cur.execute(query, vars)
            return cur

        def executescript(self, script):
            cur = self._raw.cursor()
            cur.execute(script)
            return cur

        def commit(self):
            self._raw.commit()

        def rollback(self):
            self._raw.rollback()

        def close(self):
            try:
                self._raw.close()
            except Exception:
                pass

        @property
        def closed(self):
            return self._raw.closed

        def __getattr__(self, name):
            return getattr(self._raw, name)

    def get_db():
        """Connexion Postgres (Supabase) avec curseurs compatibles sqlite3."""
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=_Cursor)
        return _Conn(conn)


# ===========================================================================
# Backend SQLite (dev hors-ligne / pipeline d'ingestion)
# ===========================================================================
else:
    import sqlite3

    def get_db() -> "sqlite3.Connection":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


@contextmanager
def db_cursor(commit: bool = False) -> Iterator[object]:
    """Context manager : ouvre une connexion, fournit un curseur, ferme proprement."""
    conn = get_db()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


def init_saas_schema(conn=None) -> None:
    """
    Garantit la présence du schéma.
    - Postgres : le schéma est provisionné via backend/schema_postgres.sql (migration
      Supabase). On ne le rejoue au démarrage que si VEILLEBF_INIT_SCHEMA=1
      (évite le coût au démarrage à froid sur Vercel).
    - SQLite : non géré ici (schéma créé par le pipeline / database_schema.py).
    """
    import os

    if not _USE_PG:
        return
    if os.getenv("VEILLEBF_INIT_SCHEMA") != "1":
        return
    sql_path = Path(__file__).resolve().parent / "schema_postgres.sql"
    if not sql_path.exists():
        return
    own = conn is None
    if own:
        conn = get_db()
    try:
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        if own:
            conn.close()
