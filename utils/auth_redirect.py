# -*- coding: utf-8 -*-
"""
Post-login redirect: optional per-employee start page (allowlist).
Order: fixed start page > next query param > dashboard.

Nur bekannte Flask-Endpunkte sind erlaubt (kein freies URL-Feld), damit gespeicherte
Werte nicht zu beliebigen Zielen führen. Die Auswahl entspricht den Hauptseiten
aus Sidebar/Menü (siehe utils.menue_definitions).
"""

from flask import url_for

from utils.decorators import is_safe_url
from utils.menue_definitions import ist_menue_zugriff_erlaubt
from utils.menue_endpunkt_zuordnung import STARTSEITEN_ENDPUNKT_MENUE_SCHLUESSEL

# Admin-Dropdown: (endpoint, Anzeigename) — Reihenfolge wie im Menü
LOGIN_STARTSEITEN_AUSWAHL = [
    ('dashboard.dashboard', 'Dashboard'),
    ('admin.dashboard', 'Adminbereich'),
    ('admin.druck_agents_uebersicht', 'Admin: Druck-Agents'),
    ('admin.mqtt_konfiguration', 'Admin: MQTT'),
    ('admin.druck_queue_uebersicht', 'Admin: Druck-Queue'),
    ('schichtbuch.themaliste', 'Schichtbuch: Themenliste'),
    ('schichtbuch.aufgabenlisten_liste', 'Schichtbuch: Aufgabenlisten'),
    ('ersatzteile.angebotsanfrage_liste', 'Bestellwesen: Angebotsanfragen'),
    ('ersatzteile.bestellung_liste', 'Bestellwesen: Bestellungen'),
    ('ersatzteile.auswertungen', 'Bestellwesen: Auswertungen'),
    ('ersatzteile.wareneingang', 'Bestellwesen: Wareneingang buchen'),
    ('ersatzteile.suche_artikel', 'Ersatzteile: Suche Artikel'),
    ('ersatzteile.ersatzteil_liste', 'Ersatzteile: Artikelliste'),
    ('ersatzteile.inventurliste', 'Ersatzteile: Inventurliste'),
    ('ersatzteile.lieferanten_liste', 'Ersatzteile: Lieferanten'),
    ('ersatzteile.lagerbuchungen_liste', 'Ersatzteile: Lagerbuchungen'),
    ('ersatzteile.lageretiketten', 'Ersatzteile: Etiketten drucken'),
    ('wartungen.wartung_liste', 'Wartungen: Wartungen'),
    ('wartungen.plaene_uebersicht', 'Wartungen: Wartungspläne'),
    ('wartungen.jahresuebersicht', 'Wartungen: Jahresübersicht'),
    ('wartungen.durchfuehrungen_chronologisch', 'Wartungen: Protokolle'),
    ('wartungen.durchfuehrung_mehrere', 'Wartungen: Mehrere protokollieren'),
    ('diverses.dokumente_erfassen', 'Dashboard: Dokumente erfassen'),
    ('diverses.zebra_drucker', 'Diverses: Zebra-Drucker (Weiterleitung)'),
    ('produktion.etikettierung', 'Produktion: Etikettierung'),
    ('produktion.etiketten_drucken', 'Produktion: Verpackung'),
    ('technik.uebersichten', 'Technik: Übersichten'),
    ('search.search', 'Globale Suche'),
    ('auth.profil', 'Mein Profil'),
]

ERLAUBTE_LOGIN_STARTSEITEN = frozenset(ep for ep, _ in LOGIN_STARTSEITEN_AUSWAHL)

# Frühere Endpunktnamen → gültiges Ziel (z. B. nach Umzug einer Seite)
_STARTSEITE_ENDPUNKT_ALIAS = {
    'diverses.zebra_drucker': 'produktion.etikettierung',
}


def normalisiere_startseite_endpunkt(wert):
    """Return a valid endpoint string or None (no DB override)."""
    if not wert:
        return None
    s = (wert or '').strip()
    s = _STARTSEITE_ENDPUNKT_ALIAS.get(s, s)
    if not s or s not in ERLAUBTE_LOGIN_STARTSEITEN:
        return None
    return s


def resolve_post_login_redirect_url(startseite_endpunkt_gespeichert, next_param):
    """
    Target URL for redirect() after successful login.
    startseite_endpunkt_gespeichert: Mitarbeiter.StartseiteNachLoginEndpunkt or None.
    next_param: request.args.get('next') or from WebAuthn JSON.
    session muss user_menue_sichtbarkeit ggf. bereits enthalten (normal nach Session-Befüllung beim Login).
    """
    from flask import flash

    ep = normalisiere_startseite_endpunkt(startseite_endpunkt_gespeichert)
    if ep:
        mkey = STARTSEITEN_ENDPUNKT_MENUE_SCHLUESSEL.get(ep)
        if mkey and not ist_menue_zugriff_erlaubt(mkey):
            flash(
                'Die gespeicherte Startseite steht Ihnen derzeit nicht zur Verfügung. Es wurde das Dashboard geöffnet.',
                'warning',
            )
            return url_for('dashboard.dashboard')
        return url_for(ep)

    if next_param and is_safe_url(next_param):
        return next_param

    return url_for('dashboard.dashboard')
