"""
Zentrale DB-Ausnahmen - dialekt- und transportunabhaengig.

Die hier exportierten Namen (``IntegrityError``, ``OperationalError``,
``DBAPIError``) sind **Tupel von Exception-Klassen**. Damit greifen sie in
``except``-Bloecken sowohl fuer

- SQLAlchemy-gewrappte Fehler (``sqlalchemy.exc.IntegrityError`` etc.), die
  beim Ausfuehren ueber SA-Core- oder -ORM-Queries entstehen, als auch fuer
- native DBAPI-Fehler (``sqlite3.IntegrityError``, psycopg-Fehler etc.), wie
  sie beim aktuellen ``get_db_connection()`` (``engine.raw_connection()``)
  direkt vom Treiber geworfen werden.

Das macht die schrittweise Migration in Phase 3 robust: ``except
utils.db_errors.IntegrityError`` funktioniert heute (raw DBAPI) und spaeter
unveraendert auch, wenn einzelne Callsites auf SA-Core-Queries umgestellt
werden.

``SQLAlchemyError`` bleibt eine einzelne Klasse, weil sie nur fuer
SA-interne Fehlerzustaende relevant ist.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy.exc import (
    DBAPIError as _SA_DBAPIError,
    IntegrityError as _SA_IntegrityError,
    OperationalError as _SA_OperationalError,
    SQLAlchemyError,
)

__all__ = [
    'DBAPIError',
    'IntegrityError',
    'OperationalError',
    'SQLAlchemyError',
]


_INTEGRITY_CLASSES: list[type[BaseException]] = [_SA_IntegrityError, sqlite3.IntegrityError]
_OPERATIONAL_CLASSES: list[type[BaseException]] = [_SA_OperationalError, sqlite3.OperationalError]
_DBAPI_CLASSES: list[type[BaseException]] = [_SA_DBAPIError, sqlite3.Error]

# psycopg ist optional (erst ab Phase 5 zwingend). Wenn installiert, erweitern
# wir die Tupel, damit die gleichen ``except``-Bloecke ohne Aenderung auch
# Postgres-Fehler fangen.
try:  # pragma: no cover - optionaler Treiber
    import psycopg as _psycopg  # type: ignore[import-not-found]

    _INTEGRITY_CLASSES.append(_psycopg.errors.IntegrityError)
    _OPERATIONAL_CLASSES.append(_psycopg.errors.OperationalError)
    _DBAPI_CLASSES.append(_psycopg.Error)
except Exception:
    pass


IntegrityError = tuple(_INTEGRITY_CLASSES)
OperationalError = tuple(_OPERATIONAL_CLASSES)
DBAPIError = tuple(_DBAPI_CLASSES)
