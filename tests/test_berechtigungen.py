"""Tests fuer utils.berechtigungen (mit In-Memory-DB)."""

import sqlite3

import pytest

from utils.berechtigungen import (
    get_alle_berechtigungen,
    get_mitarbeiter_berechtigungen,
    hat_berechtigung,
    ist_admin,
    mitarbeiter_berechtigung_entfernen,
    mitarbeiter_berechtigung_hinzufuegen,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE Berechtigung (
            ID INTEGER PRIMARY KEY,
            Schluessel TEXT,
            Bezeichnung TEXT,
            Beschreibung TEXT,
            Aktiv INTEGER DEFAULT 1
        );
        CREATE TABLE MitarbeiterBerechtigung (
            MitarbeiterID INTEGER,
            BerechtigungID INTEGER,
            UNIQUE (MitarbeiterID, BerechtigungID)
        );
        """
    )
    c.executemany(
        "INSERT INTO Berechtigung (ID, Schluessel, Bezeichnung, Aktiv) VALUES (?, ?, ?, ?)",
        [
            (1, "admin", "Administrator", 1),
            (2, "artikel_buchen", "Artikel buchen", 1),
            (3, "alt", "Alte Berechtigung", 0),
        ],
    )
    c.commit()
    yield c
    c.close()


# ---------------------------------------------------------------------------
# get_mitarbeiter_berechtigungen
# ---------------------------------------------------------------------------


def test_get_mitarbeiter_berechtigungen_liefert_nur_aktive(conn):
    conn.executemany(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (?, ?)",
        [(10, 2), (10, 3)],
    )
    result = get_mitarbeiter_berechtigungen(10, conn)
    assert result == ["artikel_buchen"]


def test_get_mitarbeiter_berechtigungen_leer_wenn_nichts_zugewiesen(conn):
    assert get_mitarbeiter_berechtigungen(999, conn) == []


# ---------------------------------------------------------------------------
# ist_admin / hat_berechtigung
# ---------------------------------------------------------------------------


def test_ist_admin_true_wenn_admin_berechtigung(conn):
    conn.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (10, 1)"
    )
    assert ist_admin(10, conn) is True


def test_ist_admin_false_ohne_berechtigung(conn):
    assert ist_admin(10, conn) is False


def test_hat_berechtigung_admin_shortcut(conn):
    conn.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (10, 1)"
    )
    # Admin hat alles, auch wenn er die konkrete Berechtigung nicht explizit besitzt
    assert hat_berechtigung(10, "artikel_buchen", conn) is True
    assert hat_berechtigung(10, "irgendwas_neues", conn) is True


def test_hat_berechtigung_normale_pruefung(conn):
    conn.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (10, 2)"
    )
    assert hat_berechtigung(10, "artikel_buchen", conn) is True
    assert hat_berechtigung(10, "admin", conn) is False


def test_hat_berechtigung_fehlschlag_ohne_rechte(conn):
    assert hat_berechtigung(10, "artikel_buchen", conn) is False


# ---------------------------------------------------------------------------
# get_alle_berechtigungen
# ---------------------------------------------------------------------------


def test_get_alle_berechtigungen_nur_aktive(conn):
    rows = get_alle_berechtigungen(nur_aktive=True, conn=conn)
    schluessel = [r["Schluessel"] for r in rows]
    assert "admin" in schluessel
    assert "artikel_buchen" in schluessel
    assert "alt" not in schluessel


def test_get_alle_berechtigungen_mit_inaktiven(conn):
    rows = get_alle_berechtigungen(nur_aktive=False, conn=conn)
    schluessel = [r["Schluessel"] for r in rows]
    assert "alt" in schluessel


# ---------------------------------------------------------------------------
# mitarbeiter_berechtigung_hinzufuegen / _entfernen
# ---------------------------------------------------------------------------


def test_berechtigung_hinzufuegen_und_entfernen(conn):
    assert mitarbeiter_berechtigung_hinzufuegen(10, 2, conn) is True
    assert hat_berechtigung(10, "artikel_buchen", conn) is True

    assert mitarbeiter_berechtigung_entfernen(10, 2, conn) is True
    assert hat_berechtigung(10, "artikel_buchen", conn) is False


def test_berechtigung_hinzufuegen_idempotent(conn):
    mitarbeiter_berechtigung_hinzufuegen(10, 2, conn)
    mitarbeiter_berechtigung_hinzufuegen(10, 2, conn)
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM MitarbeiterBerechtigung WHERE MitarbeiterID = 10"
    ).fetchone()
    # Dank UNIQUE-Constraint und INSERT OR IGNORE: nur ein Eintrag
    assert rows["c"] == 1
