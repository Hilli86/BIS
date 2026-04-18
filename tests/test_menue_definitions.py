"""Tests fuer utils.menue_definitions."""

import sqlite3

import pytest

from utils.menue_definitions import (
    _standard_sichtbar,
    get_alle_menue_definitionen,
    get_menue_sichtbarkeit_fuer_mitarbeiter,
)


# ---------------------------------------------------------------------------
# _standard_sichtbar
# ---------------------------------------------------------------------------


def test_standard_sichtbar_ohne_berechtigung_immer_true():
    # 'dashboard' hat berechtigung: None -> immer sichtbar
    assert _standard_sichtbar("dashboard", []) is True
    assert _standard_sichtbar("dashboard", ["irgendwas"]) is True


def test_standard_sichtbar_admin_menue_nur_fuer_admins():
    assert _standard_sichtbar("admin", []) is False
    assert _standard_sichtbar("admin", ["admin"]) is True


def test_standard_sichtbar_mehrere_berechtigungen():
    # wareneingang hat ['admin', 'artikel_buchen']
    assert _standard_sichtbar("bestellwesen_wareneingang", []) is False
    assert _standard_sichtbar("bestellwesen_wareneingang", ["artikel_buchen"]) is True
    assert _standard_sichtbar("bestellwesen_wareneingang", ["admin"]) is True


def test_standard_sichtbar_unbekannter_schluessel_false():
    assert _standard_sichtbar("nicht_existent", []) is False


def test_get_alle_menue_definitionen_enthaelt_dashboard():
    defs = get_alle_menue_definitionen()
    schluessel = [m["schluessel"] for m in defs]
    assert "dashboard" in schluessel
    assert "admin" in schluessel


# ---------------------------------------------------------------------------
# get_menue_sichtbarkeit_fuer_mitarbeiter (mit In-Memory-DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE Berechtigung (
            ID INTEGER PRIMARY KEY,
            Schluessel TEXT,
            Aktiv INTEGER DEFAULT 1
        );
        CREATE TABLE MitarbeiterBerechtigung (
            MitarbeiterID INTEGER,
            BerechtigungID INTEGER
        );
        CREATE TABLE MitarbeiterMenueSichtbarkeit (
            MitarbeiterID INTEGER,
            MenueSchluessel TEXT,
            Sichtbar INTEGER
        );
        """
    )
    yield c
    c.close()


def test_get_menue_sichtbarkeit_standard_ohne_berechtigungen(conn):
    # Mitarbeiter 1 ohne Berechtigungen: dashboard sichtbar, admin nicht.
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, conn)
    assert result["dashboard"] is True
    assert result["admin"] is False


def test_get_menue_sichtbarkeit_admin_sieht_admin(conn):
    conn.execute("INSERT INTO Berechtigung (ID, Schluessel, Aktiv) VALUES (1, 'admin', 1)")
    conn.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (1, 1)"
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, conn)
    assert result["admin"] is True


def test_get_menue_sichtbarkeit_explizit_0_ueberschreibt_standard(conn):
    # dashboard ist standardmaessig sichtbar; explizite Sperre greift
    conn.execute(
        """INSERT INTO MitarbeiterMenueSichtbarkeit
           (MitarbeiterID, MenueSchluessel, Sichtbar) VALUES (1, 'dashboard', 0)"""
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, conn)
    assert result["dashboard"] is False


def test_get_menue_sichtbarkeit_explizit_1_ueberschreibt_default_false(conn):
    # admin ist standardmaessig unsichtbar; explizites Einblenden greift
    conn.execute(
        """INSERT INTO MitarbeiterMenueSichtbarkeit
           (MitarbeiterID, MenueSchluessel, Sichtbar) VALUES (1, 'admin', 1)"""
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, conn)
    assert result["admin"] is True


def test_get_menue_sichtbarkeit_inaktive_berechtigung_zaehlt_nicht(conn):
    conn.execute(
        "INSERT INTO Berechtigung (ID, Schluessel, Aktiv) VALUES (1, 'admin', 0)"
    )
    conn.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (1, 1)"
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, conn)
    assert result["admin"] is False
