"""Tests fuer IP-Helfer in utils.helpers (_ip_matches_trusted, get_client_ip)."""

from app import app
from utils.helpers import _ip_matches_trusted, get_client_ip


class _FakeRequest:
    """Minimaler Request-Stub fuer get_client_ip-Tests."""

    def __init__(self, remote_addr="", headers=None):
        self.remote_addr = remote_addr
        self.headers = headers or {}


# ---------------------------------------------------------------------------
# _ip_matches_trusted
# ---------------------------------------------------------------------------


def test_ip_matches_trusted_exakte_ip():
    assert _ip_matches_trusted("127.0.0.1", ["127.0.0.1"]) is True
    assert _ip_matches_trusted("10.0.0.5", ["127.0.0.1"]) is False


def test_ip_matches_trusted_cidr():
    assert _ip_matches_trusted("10.0.0.5", ["10.0.0.0/8"]) is True
    assert _ip_matches_trusted("192.168.1.1", ["10.0.0.0/8"]) is False


def test_ip_matches_trusted_leere_liste_und_leere_ip():
    assert _ip_matches_trusted("", ["127.0.0.1"]) is False
    assert _ip_matches_trusted("127.0.0.1", []) is False
    assert _ip_matches_trusted("127.0.0.1", None) is False


def test_ip_matches_trusted_ignoriert_ungueltige_eintraege():
    assert _ip_matches_trusted("127.0.0.1", ["bogus", "127.0.0.1"]) is True
    assert _ip_matches_trusted("127.0.0.1", ["  "]) is False


def test_ip_matches_trusted_bei_ungueltiger_adresse_false():
    assert _ip_matches_trusted("nicht-ip", ["127.0.0.1"]) is False
    assert _ip_matches_trusted(None, ["127.0.0.1"]) is False


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------


def test_get_client_ip_ohne_trust_ignoriert_xff():
    req = _FakeRequest(
        remote_addr="203.0.113.5",
        headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"},
    )
    with app.test_request_context("/"):
        app.config["TRUSTED_PROXIES"] = ()
        assert get_client_ip(req) == "203.0.113.5"


def test_get_client_ip_mit_trust_nimmt_erste_xff_adresse():
    req = _FakeRequest(
        remote_addr="127.0.0.1",
        headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"},
    )
    with app.test_request_context("/"):
        app.config["TRUSTED_PROXIES"] = ("127.0.0.1",)
        assert get_client_ip(req) == "1.2.3.4"


def test_get_client_ip_mit_trust_faellt_auf_xri_zurueck():
    req = _FakeRequest(
        remote_addr="127.0.0.1",
        headers={"X-Real-IP": "8.8.8.8"},
    )
    with app.test_request_context("/"):
        app.config["TRUSTED_PROXIES"] = ("127.0.0.1",)
        assert get_client_ip(req) == "8.8.8.8"


def test_get_client_ip_mit_trust_aber_ohne_header_liefert_remote():
    req = _FakeRequest(remote_addr="127.0.0.1", headers={})
    with app.test_request_context("/"):
        app.config["TRUSTED_PROXIES"] = ("127.0.0.1",)
        assert get_client_ip(req) == "127.0.0.1"


def test_get_client_ip_trust_via_cidr():
    req = _FakeRequest(
        remote_addr="10.0.0.55",
        headers={"X-Forwarded-For": "77.77.77.77"},
    )
    with app.test_request_context("/"):
        app.config["TRUSTED_PROXIES"] = ("10.0.0.0/8",)
        assert get_client_ip(req) == "77.77.77.77"


def test_get_client_ip_trusted_proxies_als_string():
    req = _FakeRequest(
        remote_addr="127.0.0.1",
        headers={"X-Forwarded-For": "4.4.4.4"},
    )
    with app.test_request_context("/"):
        app.config["TRUSTED_PROXIES"] = "127.0.0.1, 10.0.0.0/8"
        assert get_client_ip(req) == "4.4.4.4"
