"""Tests für utils.helpers (reine Funktionen + Row-/DB-Helfer).

Die DB-gestuetzten Tests (``safe_get`` mit ``sqlite3.Row``, ``row_to_dict``)
wurden in Phase 4 auf die ``connection``-Fixture aus ``conftest.py``
umgezogen. Die Fixture stellt eine DBAPI-kompatible Verbindung bereit, die
im SQLite-Fall unter der Haube ``sqlite3.Row`` als ``row_factory`` nutzt.
"""

from utils.helpers import (
    build_ersatzteil_zugriff_filter,
    build_sichtbarkeits_filter_query,
    format_file_size,
    format_schichtbuch_datum,
    row_to_dict,
    safe_get,
)
from utils.database_check_helpers import extract_column_from_index


def test_safe_get_dict():
    assert safe_get({"a": 1}, "a") == 1
    assert safe_get({"a": 1}, "b", "x") == "x"
    assert safe_get(None, "a", 0) == 0


def test_safe_get_sqlite_row(connection):
    connection.execute("CREATE TABLE t (name TEXT, val INTEGER)")
    connection.execute("INSERT INTO t VALUES ('n', 42)")
    row = connection.execute("SELECT * FROM t").fetchone()
    assert safe_get(row, "name") == "n"
    assert safe_get(row, "missing", 0) == 0


def test_row_to_dict(connection):
    assert row_to_dict(None) is None
    connection.execute("CREATE TABLE t (a TEXT)")
    connection.execute("INSERT INTO t VALUES ('z')")
    row = connection.execute("SELECT * FROM t").fetchone()
    assert row_to_dict(row) == {"a": "z"}


def test_format_file_size():
    assert "B" in format_file_size(100)
    assert "KB" in format_file_size(2048)
    assert "MB" in format_file_size(3 * 1024 * 1024)


def test_format_schichtbuch_datum_midnight_is_date_only():
    assert format_schichtbuch_datum("2024-03-15 00:00:00") == "15.03.2024"


def test_format_schichtbuch_datum_with_time():
    out = format_schichtbuch_datum("2024-03-15 14:30:00")
    assert "15.03.2024" in out
    assert "14:30" in out


def test_format_schichtbuch_datum_empty():
    assert format_schichtbuch_datum("") == ""
    assert format_schichtbuch_datum(None) == ""


def test_build_sichtbarkeits_filter_query_without_abteilungen():
    base = "SELECT * FROM T t WHERE 1=1"
    q, params = build_sichtbarkeits_filter_query(base, None, [])
    assert q == base
    assert params == []


def test_build_sichtbarkeits_filter_query_with_abteilungen():
    base = "SELECT * FROM T t WHERE 1=1"
    q, params = build_sichtbarkeits_filter_query(base, [10, 20], [])
    assert "EXISTS" in q
    assert q.count("?") >= 2
    assert params == [10, 20]


def test_build_ersatzteil_zugriff_filter_admin_unchanged():
    base = "SELECT * FROM Ersatzteil e WHERE 1=1"
    q, params = build_ersatzteil_zugriff_filter(base, 99, [1, 2], True, [])
    assert q == base
    assert params == []


def test_build_ersatzteil_zugriff_filter_non_admin_with_abteilungen():
    base = "SELECT * FROM Ersatzteil e WHERE 1=1"
    q, params = build_ersatzteil_zugriff_filter(base, 5, [7, 8], False, [])
    assert "ErsatzteilAbteilungZugriff" in q
    assert params == [5, 7, 8]


def test_build_ersatzteil_zugriff_filter_non_admin_no_abteilungen():
    base = "SELECT * FROM Ersatzteil e WHERE 1=1"
    q, params = build_ersatzteil_zugriff_filter(base, 3, [], False, [])
    assert "ErstelltVonID = ?" in q
    assert params == [3]


def test_extract_column_from_index_simple():
    assert extract_column_from_index("CREATE INDEX idx_x ON Ersatzteil(Bestellnummer)") == "Bestellnummer"


def test_extract_column_from_index_composite_returns_none():
    assert extract_column_from_index("CREATE INDEX idx_x ON T(a, b)") is None
