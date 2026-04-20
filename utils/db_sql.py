"""
Dialekt-neutrale SQL-Helfer fuer BIS (Phase 2).

Wir bleiben bewusst nah an Roh-SQL, weil die bestehenden Callsites weiterhin
``conn.execute('SELECT ... WHERE x = ?', (val,))``-Stil verwenden. Dieses
Modul stellt kleine Bausteine bereit, um SQL-Strings dialektgerecht zu
rendern (SQLite jetzt, PostgreSQL ab Phase 5), ohne dass Callsites mit
``if dialect == ...``-Verzweigungen hantieren muessen.

Standardverhalten:

- Ohne Argument erkennt jeder Helfer den Dialekt automatisch aus der
  aktuellen Flask-Engine (``utils.database.get_engine``). Wird das Modul
  ausserhalb eines App-Kontextes importiert (z. B. in Unit-Tests),
  greift ``sqlite`` als Fallback.
- Alle Funktionen akzeptieren optional ein ``dialect='sqlite'|'postgresql'``
  zum expliziten Ueberschreiben; das erleichtert Tests.

Die Helfer ersetzen bewusst keine komplette Query-DSL. Sie decken nur
Stellen ab, an denen die Dialekte semantisch abweichen (Placeholder,
Upsert-Syntax, Aggregat-/Datumsfunktionen, JSON-Extraktion).
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Sequence

__all__ = [
    'ph',
    'upsert_ignore',
    'upsert_replace',
    'string_agg',
    'now_sql',
    'today_sql',
    'json_get',
    'month_expr',
    'year_expr',
    'year_month_expr',
    'local_now_str',
    'resolve_dialect',
]


# ---------------------------------------------------------------------------
# Dialekt-Aufloesung
# ---------------------------------------------------------------------------

_SUPPORTED_DIALECTS = ('sqlite', 'postgresql')


def resolve_dialect(dialect: Optional[str] = None) -> str:
    """Ermittelt den aktiven Dialekt (``'sqlite'`` oder ``'postgresql'``).

    Reihenfolge:

    1. explizit uebergebener ``dialect`` (case-insensitive)
    2. aktiv registrierte Flask-App: ``get_engine().dialect.name``
    3. Fallback ``'sqlite'``
    """
    if dialect:
        d = dialect.lower()
        if d in _SUPPORTED_DIALECTS:
            return d
        raise ValueError(
            f"Unbekannter Dialekt {dialect!r}; erwartet: {_SUPPORTED_DIALECTS}"
        )

    try:
        # Lokaler Import, damit reine Unit-Tests ohne Flask-Kontext funktionieren.
        from .database import get_engine

        name = get_engine().dialect.name
    except Exception:
        return 'sqlite'

    if name == 'postgresql':
        return 'postgresql'
    return 'sqlite'


# ---------------------------------------------------------------------------
# Placeholder
# ---------------------------------------------------------------------------

def ph(n: int = 1, *, dialect: Optional[str] = None) -> str:
    """Gibt ``n`` Parameter-Platzhalter als Komma-getrennten String zurueck.

    - SQLite (qmark): ``ph(3)`` -> ``'?, ?, ?'``
    - PostgreSQL (pyformat/format): ``ph(3)`` -> ``'%s, %s, %s'``

    Typischer Einsatz: dynamische ``IN (...)``-Klauseln.

        conn.execute(f'SELECT ... WHERE id IN ({ph(len(ids))})', ids)
    """
    if n <= 0:
        raise ValueError(f"ph(n) erwartet n >= 1, nicht {n}")
    token = '?' if resolve_dialect(dialect) == 'sqlite' else '%s'
    return ', '.join([token] * n)


def _ph_token(dialect: str) -> str:
    return '?' if dialect == 'sqlite' else '%s'


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------

def _normalize_cols(columns: Iterable[str]) -> Sequence[str]:
    cols = list(columns)
    if not cols:
        raise ValueError('columns darf nicht leer sein.')
    return cols


def upsert_ignore(
    table: str,
    columns: Iterable[str],
    conflict_cols: Iterable[str],
    *,
    dialect: Optional[str] = None,
) -> str:
    """Erzeugt ein ``INSERT ... ON CONFLICT DO NOTHING`` fuer ``table``.

    Sowohl SQLite (>= 3.24) als auch PostgreSQL unterstuetzen diese Syntax
    identisch; die Funktion liefert daher dialektunabhaengig denselben
    Rumpf und variiert nur den Placeholder-Token.
    """
    d = resolve_dialect(dialect)
    cols = _normalize_cols(columns)
    confl = _normalize_cols(conflict_cols)
    tok = _ph_token(d)

    col_list = ', '.join(cols)
    val_list = ', '.join([tok] * len(cols))
    confl_list = ', '.join(confl)
    return (
        f'INSERT INTO {table} ({col_list}) VALUES ({val_list}) '
        f'ON CONFLICT ({confl_list}) DO NOTHING'
    )


def upsert_replace(
    table: str,
    columns: Iterable[str],
    conflict_cols: Iterable[str],
    update_cols: Optional[Iterable[str]] = None,
    *,
    dialect: Optional[str] = None,
) -> str:
    """Erzeugt ein ``INSERT ... ON CONFLICT DO UPDATE``-Statement.

    ``update_cols`` bestimmt, welche Spalten beim Konflikt ueberschrieben
    werden. Wird nichts angegeben, werden alle Nicht-Konflikt-Spalten
    aktualisiert (haeufigster Fall bei Stammdaten-Upserts).
    """
    d = resolve_dialect(dialect)
    cols = _normalize_cols(columns)
    confl = _normalize_cols(conflict_cols)
    confl_set = set(confl)

    if update_cols is None:
        upd = [c for c in cols if c not in confl_set]
    else:
        upd = _normalize_cols(update_cols)
    if not upd:
        raise ValueError(
            'upsert_replace: keine Spalten fuer DO UPDATE uebrig; '
            'benutze stattdessen upsert_ignore().'
        )

    tok = _ph_token(d)
    col_list = ', '.join(cols)
    val_list = ', '.join([tok] * len(cols))
    confl_list = ', '.join(confl)
    set_clause = ', '.join(f'{c} = excluded.{c}' for c in upd)
    return (
        f'INSERT INTO {table} ({col_list}) VALUES ({val_list}) '
        f'ON CONFLICT ({confl_list}) DO UPDATE SET {set_clause}'
    )


# ---------------------------------------------------------------------------
# String-Aggregation
# ---------------------------------------------------------------------------

def string_agg(
    expr: str,
    separator: str = ', ',
    *,
    dialect: Optional[str] = None,
) -> str:
    """Liefert die passende Aggregat-Funktion fuer verkettete Strings.

    - SQLite: ``GROUP_CONCAT(expr, '<sep>')``
    - PostgreSQL: ``STRING_AGG(expr::text, '<sep>')``

    Der Separator wird literal in den SQL-String eingebettet. Einfache
    Anfuehrungszeichen werden verdoppelt (SQL-Standard-Escape).
    """
    d = resolve_dialect(dialect)
    sep_literal = "'" + separator.replace("'", "''") + "'"
    if d == 'postgresql':
        return f'STRING_AGG(({expr})::text, {sep_literal})'
    return f'GROUP_CONCAT({expr}, {sep_literal})'


# ---------------------------------------------------------------------------
# Datums-/Zeit-Ausdruecke
# ---------------------------------------------------------------------------

def now_sql(*, dialect: Optional[str] = None) -> str:
    """Dialekt-neutraler 'aktueller Zeitstempel'-Ausdruck.

    - SQLite: ``CURRENT_TIMESTAMP`` (UTC, wie bisher in Schema-Defaults)
    - PostgreSQL: ``NOW()``
    """
    return 'NOW()' if resolve_dialect(dialect) == 'postgresql' else 'CURRENT_TIMESTAMP'


def today_sql(*, dialect: Optional[str] = None) -> str:
    """Dialekt-neutraler 'heutiges Datum'-Ausdruck (ohne Uhrzeit)."""
    return 'CURRENT_DATE' if resolve_dialect(dialect) == 'postgresql' else "DATE('now')"


# ---------------------------------------------------------------------------
# JSON-Extraktion
# ---------------------------------------------------------------------------

def json_get(
    expr: str,
    key: str,
    *,
    dialect: Optional[str] = None,
) -> str:
    """Liefert den SQL-Ausdruck fuer den Zugriff auf ein JSON-Feld.

    - SQLite: ``json_extract(expr, '$.<key>')``
    - PostgreSQL: ``(expr)->>'<key>'``  (liefert TEXT)

    ``key`` wird escaped (einfache Anfuehrungszeichen werden verdoppelt).
    """
    if not key:
        raise ValueError('json_get: key darf nicht leer sein.')
    d = resolve_dialect(dialect)
    key_lit = key.replace("'", "''")
    if d == 'postgresql':
        return f"({expr})->>'{key_lit}'"
    return f"json_extract({expr}, '$.{key_lit}')"


# ---------------------------------------------------------------------------
# Datumsteile (Year/Month) aus Datums-/Zeitspalten
# ---------------------------------------------------------------------------

def month_expr(col: str, *, dialect: Optional[str] = None) -> str:
    """Dialekt-neutraler Monats-Ausdruck (1..12) als Integer.

    - SQLite: ``CAST(strftime('%m', col) AS INTEGER)``
    - PostgreSQL: ``CAST(EXTRACT(MONTH FROM col) AS INTEGER)``
    """
    if resolve_dialect(dialect) == 'postgresql':
        return f'CAST(EXTRACT(MONTH FROM {col}) AS INTEGER)'
    return f"CAST(strftime('%m', {col}) AS INTEGER)"


def year_expr(col: str, *, dialect: Optional[str] = None) -> str:
    """Dialekt-neutraler Jahres-Ausdruck (z. B. 2026) als Integer.

    - SQLite: ``CAST(strftime('%Y', col) AS INTEGER)``
    - PostgreSQL: ``CAST(EXTRACT(YEAR FROM col) AS INTEGER)``
    """
    if resolve_dialect(dialect) == 'postgresql':
        return f'CAST(EXTRACT(YEAR FROM {col}) AS INTEGER)'
    return f"CAST(strftime('%Y', {col}) AS INTEGER)"


def year_month_expr(col: str, *, dialect: Optional[str] = None) -> str:
    """Dialekt-neutraler Ausdruck, der einen Zeitstempel als ``'YYYY-MM'``-Text liefert.

    - SQLite: ``strftime('%Y-%m', col)``
    - PostgreSQL: ``TO_CHAR(col, 'YYYY-MM')``
    """
    if resolve_dialect(dialect) == 'postgresql':
        return f"TO_CHAR({col}, 'YYYY-MM')"
    return f"strftime('%Y-%m', {col})"


# ---------------------------------------------------------------------------
# Server-lokaler Zeitstempel als Python-Parameter
# ---------------------------------------------------------------------------

def local_now_str(fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """Server-lokaler Zeitstempel als String.

    Dient als Python-seitiger Ersatz fuer SQLite-spezifisches
    ``datetime('now', 'localtime')`` in ``INSERT``/``UPDATE``-Statements.
    Wird als ``?``-Parameter uebergeben, damit dasselbe SQL unter SQLite und
    PostgreSQL funktioniert.
    """
    return datetime.now().strftime(fmt)
