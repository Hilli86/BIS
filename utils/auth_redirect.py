# -*- coding: utf-8 -*-
"""
Post-login redirect: optional per-employee start page (allowlist).
Order: fixed start page > next query param > dashboard.
"""

from flask import url_for

from utils.decorators import is_safe_url

# Allowed Flask endpoint names (blueprint.view)
ERLAUBTE_LOGIN_STARTSEITEN = frozenset({
    'dashboard.dashboard',
    'produktion.etikettierung',
    'ersatzteile.lagerbehaelter_label',
    'diverses.zebra_drucker',
})

# Admin dropdown: (endpoint, label)
LOGIN_STARTSEITEN_AUSWAHL = [
    ('dashboard.dashboard', 'Dashboard'),
    ('produktion.etikettierung', 'Produktion: Etikettierung'),
    ('ersatzteile.lagerbehaelter_label', 'Ersatzteile: Etiketten drucken'),
    ('diverses.zebra_drucker', 'Diverses: Zebra-Drucker'),
]


def normalisiere_startseite_endpunkt(wert):
    """Return a valid endpoint string or None (no DB override)."""
    if not wert:
        return None
    s = (wert or '').strip()
    if not s or s not in ERLAUBTE_LOGIN_STARTSEITEN:
        return None
    return s


def resolve_post_login_redirect_url(startseite_endpunkt_gespeichert, next_param):
    """
    Target URL for redirect() after successful login.
    startseite_endpunkt_gespeichert: Mitarbeiter.StartseiteNachLoginEndpunkt or None.
    next_param: request.args.get('next') or from WebAuthn JSON.
    """
    ep = normalisiere_startseite_endpunkt(startseite_endpunkt_gespeichert)
    if ep:
        return url_for(ep)

    if next_param and is_safe_url(next_param):
        return next_param

    return url_for('dashboard.dashboard')
