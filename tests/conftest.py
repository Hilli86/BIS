"""Gemeinsame Test-Fixtures.

Phase 4 der SA-Migration:

- ``engine``: In-Memory-SQLite-Engine mit vollstaendigem Schema (entspricht
  ``alembic upgrade head`` – die Baseline-Migration ruft selbst nur
  ``metadata.create_all`` auf, das wir hier direkt ausfuehren).
- ``connection``: DBAPI-kompatible Verbindung aus der Engine, die sich wie die
  ``get_db_connection()``-Fassade verhaelt (``sqlite3.Row`` als ``row_factory``).
- ``client``: unveraenderter Flask-Test-Client fuer Routen-Tests.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app import app
from utils.db_schema import metadata


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def engine():
    """Frische In-Memory-SQLite-Engine mit vollstaendigem BIS-Schema.

    ``StaticPool`` sorgt dafuer, dass alle Verbindungen auf derselben
    ``:memory:``-DB arbeiten (mehrere ``raw_connection()``-Aufrufe sehen
    dieselben Tabellen/Daten).

    Foreign-Key-Enforcement wird absichtlich **nicht** aktiviert, damit Tests
    Einzeltabellen isoliert befuellen koennen, ohne alle referenzierten Rows
    anzulegen (entspricht dem bisherigen Verhalten vor Phase 4).
    """

    eng = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(eng, 'connect')
    def _on_connect(dbapi_conn, _conn_record):
        if isinstance(dbapi_conn, sqlite3.Connection):
            dbapi_conn.row_factory = sqlite3.Row

    # Entspricht "alembic upgrade head" auf einer frischen DB (Baseline-
    # Migration ruft intern ebenfalls metadata.create_all).
    metadata.create_all(bind=eng, checkfirst=True)

    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def connection(engine):
    """DBAPI-kompatible Verbindung aus der ``engine``-Fixture.

    Verhalten analog zu ``utils.database.get_db_connection()``:
    ``conn.execute(sql, params)``, ``row['Spalte']``, ``cursor()``,
    ``commit()`` und ``rollback()`` funktionieren wie gewohnt.
    """

    conn = engine.raw_connection()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
