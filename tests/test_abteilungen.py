"""Tests fuer utils.abteilungen (Hierarchie-Helfer mit In-Memory-DB)."""

import sqlite3

import pytest

from utils.abteilungen import (
    get_direkte_unterabteilungen,
    get_mitarbeiter_abteilungen,
    get_sichtbare_abteilungen_fuer_mitarbeiter,
    get_untergeordnete_abteilungen,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE Abteilung (
            ID INTEGER PRIMARY KEY,
            Bezeichnung TEXT,
            ParentAbteilungID INTEGER,
            Aktiv INTEGER DEFAULT 1,
            Sortierung INTEGER DEFAULT 0
        );
        CREATE TABLE Mitarbeiter (
            ID INTEGER PRIMARY KEY,
            PrimaerAbteilungID INTEGER
        );
        CREATE TABLE MitarbeiterAbteilung (
            MitarbeiterID INTEGER,
            AbteilungID INTEGER
        );
        """
    )
    # Hierarchie:
    #   1 Werk
    #     2 Produktion
    #       4 Linie A
    #       5 Linie B (inaktiv)
    #     3 Verwaltung
    c.executemany(
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
    c.commit()
    yield c
    c.close()


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
    conn.execute("INSERT INTO Mitarbeiter (ID, PrimaerAbteilungID) VALUES (10, 2)")
    conn.execute(
        "INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (10, 3)"
    )
    result = get_mitarbeiter_abteilungen(10, conn)
    assert set(result) == {2, 3}


def test_get_mitarbeiter_abteilungen_dedupliziert_primaer(conn):
    conn.execute("INSERT INTO Mitarbeiter (ID, PrimaerAbteilungID) VALUES (10, 2)")
    conn.execute(
        "INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (10, 2)"
    )
    result = get_mitarbeiter_abteilungen(10, conn)
    assert result == [2]


def test_get_mitarbeiter_abteilungen_ohne_primaer(conn):
    conn.execute("INSERT INTO Mitarbeiter (ID, PrimaerAbteilungID) VALUES (10, NULL)")
    conn.execute(
        "INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (10, 4)"
    )
    result = get_mitarbeiter_abteilungen(10, conn)
    assert result == [4]


# ---------------------------------------------------------------------------
# get_sichtbare_abteilungen_fuer_mitarbeiter
# ---------------------------------------------------------------------------


def test_get_sichtbare_abteilungen_inkl_unterabteilungen(conn):
    conn.execute("INSERT INTO Mitarbeiter (ID, PrimaerAbteilungID) VALUES (10, 2)")
    result = set(get_sichtbare_abteilungen_fuer_mitarbeiter(10, conn))
    assert 2 in result
    assert 4 in result
    assert 5 not in result  # inaktiv


def test_get_sichtbare_abteilungen_werk_sieht_alles(conn):
    conn.execute("INSERT INTO Mitarbeiter (ID, PrimaerAbteilungID) VALUES (10, 1)")
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
