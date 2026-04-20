"""Tests fuer utils.abteilungen (Hierarchie-Helfer).

Seit Phase 4 wird die gemeinsame ``connection``-Fixture aus ``conftest.py``
benutzt: frisch migriertes Schema in einer in-memory-SQLite-DB. Foreign-Keys
sind im Test-Engine bewusst nicht erzwungen, damit die Hierarchie-Helfer mit
minimalen Fixtures (nur der relevanten Abteilungs-/Mitarbeiter-Rows)
getestet werden koennen.
"""

import pytest

from utils.abteilungen import (
    get_direkte_unterabteilungen,
    get_mitarbeiter_abteilungen,
    get_sichtbare_abteilungen_fuer_mitarbeiter,
    get_untergeordnete_abteilungen,
)


def _insert_mitarbeiter(conn, mitarbeiter_id, primaer_abteilung_id):
    """Minimaler Mitarbeiter-Insert fuer die Tests.

    Das Schema erfordert ``Personalnummer``, ``Nachname`` und ``Passwort`` als
    NOT-NULL-Spalten; wir vergeben synthetische Platzhalter.
    """
    conn.execute(
        """
        INSERT INTO Mitarbeiter (ID, Personalnummer, Nachname, Passwort, PrimaerAbteilungID)
        VALUES (?, ?, 'Test', 'x', ?)
        """,
        (mitarbeiter_id, f'P{mitarbeiter_id}', primaer_abteilung_id),
    )


@pytest.fixture
def conn(connection):
    """Befuellt die vorhandene Abteilungs-Hierarchie fuer alle Tests."""
    # Hierarchie:
    #   1 Werk
    #     2 Produktion
    #       4 Linie A
    #       5 Linie B (inaktiv)
    #     3 Verwaltung
    connection.executemany(
        "INSERT INTO Abteilung (ID, Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (1, "Werk", None, 1, 1),
            (2, "Produktion", 1, 1, 1),
            (3, "Verwaltung", 1, 1, 2),
            (4, "Linie A", 2, 1, 1),
            (5, "Linie B", 2, 0, 2),
        ],
    )
    connection.commit()
    return connection


# ---------------------------------------------------------------------------
# get_untergeordnete_abteilungen
# ---------------------------------------------------------------------------


def test_get_untergeordnete_abteilungen_inkl_wurzel(conn):
    ergebnis = get_untergeordnete_abteilungen(1, conn)
    assert 1 in ergebnis
    assert 2 in ergebnis
    assert 3 in ergebnis
    assert 4 in ergebnis
    # Inaktive sollen nicht rekursiv aufgenommen werden
    assert 5 not in ergebnis


def test_get_untergeordnete_abteilungen_blatt(conn):
    # Blatt ohne Kinder liefert sich selbst
    assert get_untergeordnete_abteilungen(4, conn) == [4]


def test_get_untergeordnete_abteilungen_ignoriert_inaktive_kinder(conn):
    result = get_untergeordnete_abteilungen(2, conn)
    assert 2 in result
    assert 4 in result
    assert 5 not in result


# ---------------------------------------------------------------------------
# get_mitarbeiter_abteilungen
# ---------------------------------------------------------------------------


def test_get_mitarbeiter_abteilungen_primaer_und_zusatz(conn):
    _insert_mitarbeiter(conn, 10, 2)
    conn.execute(
        "INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (10, 3)"
    )
    result = get_mitarbeiter_abteilungen(10, conn)
    assert set(result) == {2, 3}


def test_get_mitarbeiter_abteilungen_dedupliziert_primaer(conn):
    _insert_mitarbeiter(conn, 10, 2)
    conn.execute(
        "INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (10, 2)"
    )
    result = get_mitarbeiter_abteilungen(10, conn)
    assert result == [2]


def test_get_mitarbeiter_abteilungen_ohne_primaer(conn):
    _insert_mitarbeiter(conn, 10, None)
    conn.execute(
        "INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (10, 4)"
    )
    result = get_mitarbeiter_abteilungen(10, conn)
    assert result == [4]


# ---------------------------------------------------------------------------
# get_sichtbare_abteilungen_fuer_mitarbeiter
# ---------------------------------------------------------------------------


def test_get_sichtbare_abteilungen_inkl_unterabteilungen(conn):
    _insert_mitarbeiter(conn, 10, 2)
    result = set(get_sichtbare_abteilungen_fuer_mitarbeiter(10, conn))
    assert 2 in result
    assert 4 in result
    assert 5 not in result  # inaktiv


def test_get_sichtbare_abteilungen_werk_sieht_alles(conn):
    _insert_mitarbeiter(conn, 10, 1)
    result = set(get_sichtbare_abteilungen_fuer_mitarbeiter(10, conn))
    assert {1, 2, 3, 4}.issubset(result)
    assert 5 not in result


# ---------------------------------------------------------------------------
# get_direkte_unterabteilungen
# ---------------------------------------------------------------------------


def test_get_direkte_unterabteilungen_nur_aktive(conn):
    rows = get_direkte_unterabteilungen(2, conn)
    ids = [r["ID"] for r in rows]
    assert ids == [4]  # 5 ist inaktiv


def test_get_direkte_unterabteilungen_werk(conn):
    rows = get_direkte_unterabteilungen(1, conn)
    ids = [r["ID"] for r in rows]
    assert set(ids) == {2, 3}


def test_get_direkte_unterabteilungen_ohne_kinder(conn):
    rows = get_direkte_unterabteilungen(4, conn)
    assert list(rows) == []
