"""
Database Utilities – SQLAlchemy-Core-Fassade (Phase 0).

Die oeffentliche API (``get_db_connection()`` als Context Manager) bleibt
rueckwaertskompatibel: Callsites koennen weiterhin ``conn.execute``,
``conn.executemany``, ``conn.executescript``, ``conn.cursor()``,
``conn.commit()`` und ``conn.rollback()`` wie gewohnt aufrufen und erhalten
``sqlite3.Row``-artige Ergebnisse (``row['Spalte']`` und ``row[0]``).

Intern wird eine DBAPI-Verbindung aus dem SQLAlchemy-Connection-Pool bezogen
(``engine.raw_connection()``). Damit sind bestehende Aufrufstile identisch
erhalten, und spaetere Phasen koennen schrittweise auf SQLAlchemy-Core-Syntax
umstellen, ohne den App-Start zu brechen.

Phase 0 ist SQLite-zentriert; die Fassade ist aber so gebaut, dass ab Phase 1
(Alembic + ``utils.db_schema``) und Phase 5 (Postgres) dieselbe Engine-Instanz
genutzt werden kann.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from threading import Lock

from flask import current_app
from sqlalchemy import create_engine, event

__all__ = [
    'get_db_connection',
    'get_engine',
    'normalize_db_url',
    'sql_trace',
]


# Prozessweiter Cache: eine Engine pro (App-Identitaet, normalisierte URL).
# Flask erzeugt im Regelfall genau eine App pro Prozess; Tests koennen mehrere
# Apps (mit unterschiedlichen DBs) aufsetzen -> App-Identitaet mitnehmen, damit
# ``get_engine()`` deterministisch die richtige Engine zurueckgibt.
_ENGINE_CACHE: dict = {}
_ENGINE_LOCK = Lock()


def normalize_db_url(value) -> str:
    """Normalisiert einen DATABASE_URL-Wert zu einer SQLAlchemy-URL.

    Erlaubte Eingaben:

    - vollstaendige SA-URL, z. B. ``sqlite:///C:/pfad/bis.db`` oder
      ``postgresql+psycopg://user:pw@host/db``
    - reiner Dateipfad zu einer SQLite-Datei (rueckwaertskompatibel zum
      bisherigen Default ``database_main.db``)
    """
    if value is None:
        raise RuntimeError('DATABASE_URL ist nicht gesetzt.')
    s = str(value).strip()
    if not s:
        raise RuntimeError('DATABASE_URL ist leer.')
    if '://' in s:
        return s
    return 'sqlite:///' + os.path.abspath(s)


def sql_trace(statement):
    """Rueckwaertskompatibler Trace-Hook.

    Wird von der SA-Fassade selbst nicht mehr direkt aufgerufen (Tracing laeuft
    ueber Engine-Event-Listener), bleibt aber exportiert, falls externe
    Werkzeuge ihn importieren.
    """
    try:
        current_app.logger.debug('SQL: %s', statement)
    except RuntimeError:
        # Kein App-Kontext (sehr frueher Bootstrap): still verwerfen.
        pass


def _install_engine_listeners(engine, app):
    """Event-Listener fuer Tracing und dialect-spezifische Setup-Schritte."""
    logger = app.logger

    @event.listens_for(engine, 'connect')
    def _on_connect(dbapi_conn, connection_record):
        # SQLite-spezifisch: row_factory fuer Dict-Zugriff auf Rows, Foreign
        # Keys erzwingen und optional SQL-Tracing am DBAPI-Connection setzen.
        if isinstance(dbapi_conn, sqlite3.Connection):
            dbapi_conn.row_factory = sqlite3.Row
            try:
                dbapi_conn.execute('PRAGMA foreign_keys = ON')
            except Exception:
                pass
            if app.config.get('SQL_TRACING', False):
                def _tracer(stmt, _logger=logger):
                    try:
                        _logger.debug('SQL: %s', stmt)
                    except Exception:
                        pass
                try:
                    dbapi_conn.set_trace_callback(_tracer)
                except Exception:
                    pass

    @event.listens_for(engine, 'before_cursor_execute')
    def _before_cursor(conn, cursor, statement, parameters, context, executemany):
        # SA-seitiges Tracing (greift spaeter fuer SA-Core-Queries). Bei Phase 0
        # laufen die meisten Queries direkt ueber den DBAPI-Cursor; dort wirkt
        # der sqlite3-Trace-Callback von oben.
        if app.config.get('SQL_TRACING', False):
            try:
                logger.debug('SQL: %s | params=%r', statement, parameters)
            except Exception:
                pass


def _get_engine_for_app(app):
    url = normalize_db_url(app.config['DATABASE_URL'])
    key = (id(app), url)
    engine = _ENGINE_CACHE.get(key)
    if engine is None:
        with _ENGINE_LOCK:
            engine = _ENGINE_CACHE.get(key)
            if engine is None:
                engine = create_engine(url, future=True, pool_pre_ping=True)
                _install_engine_listeners(engine, app)
                _ENGINE_CACHE[key] = engine
    return engine


def get_engine():
    """Gibt die SA-Engine fuer die aktuelle Flask-App zurueck (gecached)."""
    app = current_app._get_current_object()
    return _get_engine_for_app(app)


@contextmanager
def get_db_connection():
    """Context Manager fuer Datenbankverbindungen.

    Liefert eine DBAPI-kompatible Verbindung aus dem SQLAlchemy-Pool. Die
    Verbindung verhaelt sich wie die bisherige ``sqlite3.Connection``
    (inklusive ``row_factory = sqlite3.Row``), wird aber ueber den Pool verwaltet.

    Commit bei erfolgreichem Blockaustritt, Rollback bei Ausnahme, danach
    Rueckgabe der Verbindung in den Pool.
    """
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        # Gibt die Verbindung an den Pool zurueck (schliesst nicht die
        # unterliegende sqlite3.Connection).
        conn.close()
