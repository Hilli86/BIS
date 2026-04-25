"""Startseiten-Endpunkt-Strings existieren in der App; Menue-Keys vollstaendig."""

from app import app
from utils.menue_definitions import get_alle_menue_definitionen
from utils.menue_endpunkt_zuordnung import STARTSEITEN_ENDPUNKT_MENUE_SCHLUESSEL


def test_startseiten_endpunkte_sind_in_der_app_registriert():
    with app.app_context():
        for ep in STARTSEITEN_ENDPUNKT_MENUE_SCHLUESSEL:
            if ep in ("search.search", "auth.profil"):
                continue
            assert app.view_functions.get(ep) is not None, f"unbekannter Endpunkt: {ep}"


def test_jeder_menue_schluessel_hat_startseiten_mapping_eintrag():
    schluesel_in_map = {v for v in STARTSEITEN_ENDPUNKT_MENUE_SCHLUESSEL.values() if v is not None}
    for m in get_alle_menue_definitionen():
        assert m["schluessel"] in schluesel_in_map, f"Startseiten-Mapping fehlt: {m['schluessel']}"
