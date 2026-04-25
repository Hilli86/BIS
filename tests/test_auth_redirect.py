"""Tests fuer utils.auth_redirect (Post-Login-Redirect-Allowlist)."""

from app import app
from utils.auth_redirect import (
    ERLAUBTE_LOGIN_STARTSEITEN,
    normalisiere_startseite_endpunkt,
    resolve_post_login_redirect_url,
)


def test_normalisiere_startseite_erlaubter_endpunkt():
    # dashboard.dashboard steht in der Allowlist
    assert "dashboard.dashboard" in ERLAUBTE_LOGIN_STARTSEITEN
    assert normalisiere_startseite_endpunkt("dashboard.dashboard") == "dashboard.dashboard"


def test_normalisiere_startseite_unbekannt_oder_leer():
    assert normalisiere_startseite_endpunkt("") is None
    assert normalisiere_startseite_endpunkt(None) is None
    assert normalisiere_startseite_endpunkt("   ") is None
    assert normalisiere_startseite_endpunkt("nicht.existent") is None


def test_normalisiere_startseite_whitespace_wird_getrimmt():
    assert (
        normalisiere_startseite_endpunkt("  dashboard.dashboard  ")
        == "dashboard.dashboard"
    )


def test_resolve_post_login_gespeicherter_endpunkt_gewinnt():
    with app.test_request_context("/login", base_url="http://localhost:5000/"):
        from flask import session

        session["user_menue_sichtbarkeit"] = {"dashboard": True}
        url = resolve_post_login_redirect_url("dashboard.dashboard", "/other")
        assert url.rstrip("/").endswith("/dashboard")


def test_resolve_post_login_next_param_wird_uebernommen():
    with app.test_request_context("/login", base_url="http://localhost:5000/"):
        url = resolve_post_login_redirect_url(None, "/schichtbuch")
        assert url == "/schichtbuch"


def test_resolve_post_login_offener_redirect_wird_verworfen():
    with app.test_request_context("/login", base_url="http://localhost:5000/"):
        url = resolve_post_login_redirect_url(None, "http://evil.example/pwn")
        # Fallback auf Dashboard
        assert url.rstrip("/").endswith("/dashboard")


def test_resolve_post_login_kein_next_faellt_auf_dashboard():
    with app.test_request_context("/login", base_url="http://localhost:5000/"):
        url = resolve_post_login_redirect_url(None, None)
        assert url.rstrip("/").endswith("/dashboard")
