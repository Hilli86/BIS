"""Tests fuer utils.menue_definitions.

Seit Phase 4 wird die gemeinsame ``connection``-Fixture aus ``conftest.py``
benutzt (in-memory SQLite mit vollem BIS-Schema).
"""

from utils.menue_definitions import (
    _standard_sichtbar,
    get_alle_menue_definitionen,
    get_menue_sichtbarkeit_fuer_mitarbeiter,
    ist_menue_zugriff_erlaubt,
)

from app import app


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


def test_ist_menue_zugriff_liest_session_schluessel_user_menue_sichtbarkeit():
    """Session-Key muss user_menue_sichtbarkeit heissen (sonst erscheint alles gesperrt)."""
    with app.test_request_context("/"):
        from flask import session

        assert ist_menue_zugriff_erlaubt("dashboard") is False
        session["user_menue_sichtbarkeit"] = {"dashboard": True}
        assert ist_menue_zugriff_erlaubt("dashboard") is True


# ---------------------------------------------------------------------------
# get_menue_sichtbarkeit_fuer_mitarbeiter (mit engine/connection-Fixture)
# ---------------------------------------------------------------------------


def test_get_menue_sichtbarkeit_standard_ohne_berechtigungen(connection):
    # Mitarbeiter 1 ohne Berechtigungen: dashboard sichtbar, admin nicht.
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, connection)
    assert result["dashboard"] is True
    assert result["admin"] is False


def test_get_menue_sichtbarkeit_admin_sieht_admin(connection):
    connection.execute(
        "INSERT INTO Berechtigung (ID, Schluessel, Bezeichnung, Aktiv) "
        "VALUES (1, 'admin', 'Administrator', 1)"
    )
    connection.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (1, 1)"
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, connection)
    assert result["admin"] is True


def test_get_menue_sichtbarkeit_explizit_0_ueberschreibt_standard(connection):
    # dashboard ist standardmaessig sichtbar; explizite Sperre greift
    connection.execute(
        """INSERT INTO MitarbeiterMenueSichtbarkeit
           (MitarbeiterID, MenueSchluessel, Sichtbar) VALUES (1, 'dashboard', 0)"""
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, connection)
    assert result["dashboard"] is False


def test_get_menue_sichtbarkeit_explizit_1_ueberschreibt_default_false(connection):
    # admin ist standardmaessig unsichtbar; explizites Einblenden greift
    connection.execute(
        """INSERT INTO MitarbeiterMenueSichtbarkeit
           (MitarbeiterID, MenueSchluessel, Sichtbar) VALUES (1, 'admin', 1)"""
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, connection)
    assert result["admin"] is True


def test_get_menue_sichtbarkeit_inaktive_berechtigung_zaehlt_nicht(connection):
    connection.execute(
        "INSERT INTO Berechtigung (ID, Schluessel, Bezeichnung, Aktiv) "
        "VALUES (1, 'admin', 'Administrator', 0)"
    )
    connection.execute(
        "INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (1, 1)"
    )
    result = get_menue_sichtbarkeit_fuer_mitarbeiter(1, connection)
    assert result["admin"] is False
