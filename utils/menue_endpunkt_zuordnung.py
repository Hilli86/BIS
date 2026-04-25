# -*- coding: utf-8 -*-
"""
Flask-Endpoint-Name (blueprint.funk) -> MenueSchluessel aus MENUE_DEFINITIONEN.
Nur fuer Startseite nach Login und Tests; tatsaechliche Absicherung geschieht per
@menue_zugriff_erforderlich an den Routen.

Wert None: kein expliziter Menue-Check (nur angemeldet), z. B. Profil, Suche.
"""

# Endpunkte aus auth_redirect.LOGIN_STARTSEITEN_AUSWAHL
STARTSEITEN_ENDPUNKT_MENUE_SCHLUESSEL = {
    'dashboard.dashboard': 'dashboard',
    'admin.dashboard': 'admin',
    'admin.druck_agents_uebersicht': 'admin_druck_agents',
    'admin.druck_queue_uebersicht': 'admin_druck_queue',
    'schichtbuch.themaliste': 'schichtbuch_liste',
    'schichtbuch.aufgabenlisten_liste': 'schichtbuch_aufgabenlisten',
    'ersatzteile.angebotsanfrage_liste': 'bestellwesen_angebote',
    'ersatzteile.bestellung_liste': 'bestellwesen_bestellungen',
    'ersatzteile.auswertungen': 'bestellwesen_auswertungen',
    'ersatzteile.wareneingang': 'bestellwesen_wareneingang',
    'ersatzteile.suche_artikel': 'ersatzteile_suche',
    'ersatzteile.ersatzteil_liste': 'ersatzteile_liste',
    'ersatzteile.inventurliste': 'ersatzteile_inventur',
    'ersatzteile.lieferanten_liste': 'ersatzteile_lieferanten',
    'ersatzteile.lagerbuchungen_liste': 'ersatzteile_lagerbuchungen',
    'ersatzteile.lageretiketten': 'ersatzteile_etiketten',
    'wartungen.wartung_liste': 'wartungen_liste',
    'wartungen.plaene_uebersicht': 'wartungen_plaene',
    'wartungen.jahresuebersicht': 'wartungen_jahresuebersicht',
    'wartungen.durchfuehrungen_chronologisch': 'wartungen_protokolle',
    'wartungen.durchfuehrung_mehrere': 'wartungen_mehrere',
    'diverses.dokumente_erfassen': 'diverses_dokumente',
    'diverses.zebra_drucker': 'diverses_zebra',
    'produktion.etikettierung': 'produktion_etikettierung',
    'produktion.etiketten_drucken': 'produktion_etiketten_drucken',
    'search.search': None,
    'auth.profil': None,
    'technik.uebersichten': 'technik_uebersichten',
}
