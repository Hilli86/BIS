"""
Database Utilities
Verbindung zur Datenbank und Context Manager
"""
import sqlite3
from contextlib import contextmanager
from flask import current_app


def sql_trace(statement):
    """SQL-Tracing für Debugging – schreibt in den Flask-Logger (DEBUG)."""
    try:
        current_app.logger.debug('SQL: %s', statement)
    except RuntimeError:
        # Kein App-Kontext (sehr früher Bootstrap): still verwerfen.
        pass


@contextmanager
def get_db_connection():
    """Context Manager für Datenbankverbindungen"""
    conn = sqlite3.connect(current_app.config['DATABASE_URL'])
    if current_app.config.get('SQL_TRACING', False):
        conn.set_trace_callback(sql_trace)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        # Automatisches Commit wenn keine Exception aufgetreten ist
        # SQLite committet standardmäßig nur DDL-Anweisungen automatisch
        # DML-Anweisungen (INSERT, UPDATE, DELETE) benötigen explizites Commit
        conn.commit()
    except Exception as e:
        # Bei Fehler: Rollback
        conn.rollback()
        raise e
    finally:
        conn.close()

