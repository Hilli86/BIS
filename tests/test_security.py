"""Tests fuer utils.security (Farb-/Pfad-/Passwort-Helfer, Redirect-Safety)."""

import os

import pytest
from flask import Flask

from utils.security import (
    PathTraversalError,
    generiere_zufalls_passwort,
    is_safe_url,
    resolve_under_base,
    safe_redirect_target,
    validate_css_color,
    validate_passwort_policy,
)


# ---------------------------------------------------------------------------
# validate_css_color
# ---------------------------------------------------------------------------


def test_validate_css_color_hex_varianten():
    assert validate_css_color("#abc") == "#abc"
    assert validate_css_color("#abcd") == "#abcd"
    assert validate_css_color("#aabbcc") == "#aabbcc"
    assert validate_css_color("#aabbccdd") == "#aabbccdd"


def test_validate_css_color_keywords_erlaubt():
    assert validate_css_color("inherit") == "inherit"
    assert validate_css_color("transparent") == "transparent"
    assert validate_css_color("currentColor") == "currentColor"


def test_validate_css_color_faellt_auf_fallback_zurueck():
    assert validate_css_color("") == "inherit"
    assert validate_css_color(None) == "inherit"
    assert validate_css_color("url(javascript:alert(1))") == "inherit"
    assert validate_css_color("red") == "inherit"
    assert validate_css_color("#zzz") == "inherit"
    assert validate_css_color("#12", fallback="transparent") == "transparent"


# ---------------------------------------------------------------------------
# validate_passwort_policy
# ---------------------------------------------------------------------------


def test_validate_passwort_policy_akzeptiert_starkes_passwort():
    assert validate_passwort_policy("Abcdef12!x") is None


def test_validate_passwort_policy_leer_und_none():
    assert validate_passwort_policy(None) is not None
    assert "mindestens" in validate_passwort_policy("")


def test_validate_passwort_policy_zu_kurz():
    msg = validate_passwort_policy("Ab1!xyz")
    assert msg is not None
    assert "mindestens" in msg


def test_validate_passwort_policy_zu_wenig_zeichenklassen():
    msg = validate_passwort_policy("abcdefghij")
    assert msg is not None
    assert "Zeichenklassen" in msg


def test_validate_passwort_policy_reine_wiederholung():
    # Starkes Passwort mit drei Klassen akzeptiert
    assert validate_passwort_policy("Ab1!Ab1!Ab") is None
    # Nur ein Zeichen oft wiederholt: scheitert
    assert validate_passwort_policy("aaaaaaaaaaaa") is not None


# ---------------------------------------------------------------------------
# resolve_under_base
# ---------------------------------------------------------------------------


def test_resolve_under_base_gueltiger_unterpfad(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    file = sub / "f.txt"
    file.write_text("hi", encoding="utf-8")
    resolved = resolve_under_base(str(tmp_path), "sub/f.txt")
    assert os.path.normcase(resolved) == os.path.normcase(str(file))


def test_resolve_under_base_traversal_wird_abgelehnt(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_under_base(str(tmp_path), "../outside.txt")


def test_resolve_under_base_null_byte(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_under_base(str(tmp_path), "sub/\x00bad")


def test_resolve_under_base_leerer_pfad(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_under_base(str(tmp_path), "")
    with pytest.raises(PathTraversalError):
        resolve_under_base(str(tmp_path), None)


def test_resolve_under_base_backslash_wird_normalisiert(tmp_path):
    sub = tmp_path / "a"
    sub.mkdir()
    file = sub / "b.txt"
    file.write_text("x", encoding="utf-8")
    resolved = resolve_under_base(str(tmp_path), "a\\b.txt")
    assert os.path.normcase(resolved) == os.path.normcase(str(file))


# ---------------------------------------------------------------------------
# is_safe_url / safe_redirect_target
# ---------------------------------------------------------------------------


def _request_ctx():
    app = Flask(__name__)
    return app.test_request_context("/", base_url="http://localhost:5000/")


def test_security_is_safe_url_intern_ok():
    with _request_ctx():
        assert is_safe_url("/dashboard") is True


def test_security_is_safe_url_fremder_host_abgelehnt():
    with _request_ctx():
        assert is_safe_url("http://evil.example/phishing") is False


def test_security_is_safe_url_leer_und_none():
    with _request_ctx():
        assert is_safe_url("") is False
        assert is_safe_url(None) is False


def test_safe_redirect_target_nutzt_fallback_bei_offenem_redirect():
    with _request_ctx():
        assert safe_redirect_target("http://evil.example/x", "/dashboard") == "/dashboard"
        assert safe_redirect_target("/ok", "/dashboard") == "/ok"


# ---------------------------------------------------------------------------
# generiere_zufalls_passwort
# ---------------------------------------------------------------------------


def test_generiere_zufalls_passwort_laenge_und_einzigartigkeit():
    a = generiere_zufalls_passwort()
    b = generiere_zufalls_passwort()
    assert isinstance(a, str)
    assert len(a) >= 16
    assert a != b
