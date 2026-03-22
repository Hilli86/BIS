"""Tests für zentrale Hilfsfunktionen (ohne DB)."""

from flask import Flask

from utils.decorators import is_safe_url


def test_is_safe_url_internal_path():
    app = Flask(__name__)
    with app.test_request_context("/", base_url="http://localhost:5000/"):
        assert is_safe_url("/dashboard") is True


def test_is_safe_url_rejects_foreign_host():
    app = Flask(__name__)
    with app.test_request_context("/", base_url="http://localhost:5000/"):
        assert is_safe_url("http://evil.example/phishing") is False


def test_is_safe_url_same_host_absolute_path():
    app = Flask(__name__)
    with app.test_request_context("/", base_url="http://localhost:5000/"):
        assert is_safe_url("http://localhost:5000/dashboard") is True


def test_login_page_renders(client):
    """Smoke: Login-Seite ist per GET erreichbar."""
    rv = client.get("/login")
    assert rv.status_code == 200
    text = rv.get_data(as_text=True).lower()
    assert "anmeldung" in text or "anmelden" in text


def test_app_root_redirects(client):
    """Smoke: Startseite antwortet (Redirect zu Login o. ä.)."""
    rv = client.get("/", follow_redirects=False)
    assert rv.status_code in (302, 301)
