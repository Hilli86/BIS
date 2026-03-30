"""
Menü-Definitionen und Sichtbarkeitslogik
Zentrale Definition aller Sidebar-Menüpunkte und Berechnung der Sichtbarkeit pro Mitarbeiter.
"""

from utils.database import get_db_connection


# Alle Menüpunkte mit Schluessel, Bezeichnung, Gruppe
# BerechtigungErforderlich: Liste von Berechtigungs-Schlüsseln; wenn einer davon, ist Menü sichtbar (Standard)
# Bei leerer Liste: immer sichtbar für eingeloggte Benutzer (nicht Gast)
MENUE_DEFINITIONEN = [
    {'schluessel': 'dashboard', 'bezeichnung': 'Dashboard', 'gruppe': None, 'berechtigung': None},
    {'schluessel': 'admin', 'bezeichnung': 'Adminbereich', 'gruppe': None, 'berechtigung': ['admin']},
    {'schluessel': 'schichtbuch_suche', 'bezeichnung': 'Suche Thema', 'gruppe': 'Schichtbuch', 'berechtigung': None},
    {'schluessel': 'schichtbuch_liste', 'bezeichnung': 'Themenliste', 'gruppe': 'Schichtbuch', 'berechtigung': None},
    {'schluessel': 'bestellwesen_angebote', 'bezeichnung': 'Angebotsanfragen', 'gruppe': 'Bestellwesen', 'berechtigung': None},
    {'schluessel': 'bestellwesen_bestellungen', 'bezeichnung': 'Bestellungen', 'gruppe': 'Bestellwesen', 'berechtigung': None},
    {'schluessel': 'bestellwesen_auswertungen', 'bezeichnung': 'Auswertungen', 'gruppe': 'Bestellwesen', 'berechtigung': None},
    {'schluessel': 'bestellwesen_wareneingang', 'bezeichnung': 'Wareneingang buchen', 'gruppe': 'Bestellwesen', 'berechtigung': ['admin', 'artikel_buchen']},
    {'schluessel': 'ersatzteile_suche', 'bezeichnung': 'Suche Artikel', 'gruppe': 'Ersatzteile', 'berechtigung': None},
    {'schluessel': 'ersatzteile_liste', 'bezeichnung': 'Artikelliste', 'gruppe': 'Ersatzteile', 'berechtigung': None},
    {'schluessel': 'ersatzteile_inventur', 'bezeichnung': 'Inventurliste', 'gruppe': 'Ersatzteile', 'berechtigung': None},
    {'schluessel': 'ersatzteile_lieferanten', 'bezeichnung': 'Lieferanten', 'gruppe': 'Ersatzteile', 'berechtigung': None},
    {'schluessel': 'ersatzteile_lagerbuchungen', 'bezeichnung': 'Lagerbuchungen', 'gruppe': 'Ersatzteile', 'berechtigung': None},
    {'schluessel': 'ersatzteile_etiketten', 'bezeichnung': 'Etiketten drucken', 'gruppe': 'Ersatzteile', 'berechtigung': None},
    {'schluessel': 'wartungen_liste', 'bezeichnung': 'Wartungen', 'gruppe': 'Wartungen', 'berechtigung': ['admin', 'wartung_erstellen', 'wartung_nur_Plan_erstellen']},
    {'schluessel': 'wartungen_plaene', 'bezeichnung': 'Wartungspläne', 'gruppe': 'Wartungen', 'berechtigung': ['admin', 'wartung_erstellen', 'wartung_nur_Plan_erstellen']},
    {'schluessel': 'wartungen_mehrere', 'bezeichnung': 'Mehrere protokollieren', 'gruppe': 'Wartungen', 'berechtigung': ['admin', 'wartung_erstellen', 'wartung_nur_Plan_erstellen']},
    {'schluessel': 'diverses_zebra', 'bezeichnung': 'Zebra-Drucker', 'gruppe': 'Diverses', 'berechtigung': ['zebra_drucker_produktion']},
    {'schluessel': 'diverses_dokumente', 'bezeichnung': 'Dokumente erfassen', 'gruppe': 'Diverses', 'berechtigung': None},
    {'schluessel': 'produktion_etikettierung', 'bezeichnung': 'Etikettierung', 'gruppe': 'Produktion', 'berechtigung': None},
]


def _standard_sichtbar(menue_schluessel, berechtigungen):
    """
    Prüft die Standard-Sichtbarkeit eines Menüpunkts basierend auf Berechtigungen.
    berechtigungen: Liste von Berechtigungs-Schlüsseln des Mitarbeiters
    """
    for m in MENUE_DEFINITIONEN:
        if m['schluessel'] == menue_schluessel:
            if m['berechtigung'] is None:
                return True  # Keine spezielle Berechtigung nötig
            for ber in m['berechtigung']:
                if ber in berechtigungen:
                    return True
            return False
    return False


def get_menue_sichtbarkeit_fuer_mitarbeiter(mitarbeiter_id, conn=None):
    """
    Gibt ein Dict mit der Sichtbarkeit jedes Menüpunkts für einen Mitarbeiter zurück.
    
    Logik:
    - Zuerst MitarbeiterMenueSichtbarkeit prüfen
    - Wenn Eintrag mit Sichtbar=0: ausblenden
    - Wenn Eintrag mit Sichtbar=1: einblenden
    - Kein Eintrag: Standardlogik (Berechtigungen) anwenden
    
    Returns:
        dict: {menue_schluessel: bool}
    """
    should_close = False
    if conn is None:
        from flask import current_app
        import sqlite3
        conn = sqlite3.connect(current_app.config['DATABASE_URL'])
        conn.row_factory = sqlite3.Row
        should_close = True
    
    try:
        # Berechtigungen des Mitarbeiters laden
        berechtigungen_rows = conn.execute('''
            SELECT b.Schluessel
            FROM MitarbeiterBerechtigung mb
            JOIN Berechtigung b ON mb.BerechtigungID = b.ID
            WHERE mb.MitarbeiterID = ? AND b.Aktiv = 1
        ''', (mitarbeiter_id,)).fetchall()
        berechtigungen = [r['Schluessel'] for r in berechtigungen_rows]
        
        # Explizite Menü-Sichtbarkeit laden
        sichtbarkeit_rows = conn.execute('''
            SELECT MenueSchluessel, Sichtbar
            FROM MitarbeiterMenueSichtbarkeit
            WHERE MitarbeiterID = ?
        ''', (mitarbeiter_id,)).fetchall()
        explizit = {r['MenueSchluessel']: bool(r['Sichtbar']) for r in sichtbarkeit_rows}
        
        # Ergebnis für jeden Menüpunkt berechnen
        result = {}
        for m in MENUE_DEFINITIONEN:
            schluessel = m['schluessel']
            if schluessel in explizit:
                result[schluessel] = explizit[schluessel]
            else:
                result[schluessel] = _standard_sichtbar(schluessel, berechtigungen)
        
        return result
    finally:
        if should_close:
            conn.close()


def get_alle_menue_definitionen():
    """Gibt alle Menü-Definitionen zurück (für Admin-UI)."""
    return MENUE_DEFINITIONEN
