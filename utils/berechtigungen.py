"""
Berechtigungs-Utilities
Hilfsfunktionen für die Prüfung von Mitarbeiter-Berechtigungen
"""

from utils.database import get_db_connection


def get_mitarbeiter_berechtigungen(mitarbeiter_id, conn=None):
    """
    Gibt alle Berechtigungen eines Mitarbeiters zurück
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Optional - Datenbankverbindung (wird erstellt wenn nicht übergeben)
    
    Returns:
        Liste von Berechtigungs-Schlüsseln (z.B. ['admin', 'artikel_buchen'])
    """
    should_close = False
    if conn is None:
        from flask import current_app
        import sqlite3
        conn = sqlite3.connect(current_app.config['DATABASE_URL'])
        conn.row_factory = sqlite3.Row
        should_close = True
    
    try:
        berechtigungen = conn.execute('''
            SELECT b.Schluessel
            FROM MitarbeiterBerechtigung mb
            JOIN Berechtigung b ON mb.BerechtigungID = b.ID
            WHERE mb.MitarbeiterID = ? AND b.Aktiv = 1
        ''', (mitarbeiter_id,)).fetchall()
        
        return [b['Schluessel'] for b in berechtigungen]
    finally:
        if should_close:
            conn.close()


def hat_berechtigung(mitarbeiter_id, berechtigung_schluessel, conn=None):
    """
    Prüft, ob ein Mitarbeiter eine bestimmte Berechtigung hat
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        berechtigung_schluessel: Schlüssel der Berechtigung (z.B. 'artikel_buchen')
        conn: Optional - Datenbankverbindung
    
    Returns:
        True wenn Mitarbeiter die Berechtigung hat, sonst False
    """
    # Admin hat alle Berechtigungen
    if ist_admin(mitarbeiter_id, conn):
        return True
    
    berechtigungen = get_mitarbeiter_berechtigungen(mitarbeiter_id, conn)
    return berechtigung_schluessel in berechtigungen


def ist_admin(mitarbeiter_id, conn=None):
    """
    Prüft, ob ein Mitarbeiter Admin-Rechte hat
    (durch Admin-Berechtigung)
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Optional - Datenbankverbindung
    
    Returns:
        True wenn Mitarbeiter Admin ist, sonst False
    """
    should_close = False
    if conn is None:
        from flask import current_app
        import sqlite3
        conn = sqlite3.connect(current_app.config['DATABASE_URL'])
        conn.row_factory = sqlite3.Row
        should_close = True
    
    try:
        # Prüfe Admin-Berechtigung
        admin_ber = conn.execute('''
            SELECT COUNT(*) as count
            FROM MitarbeiterBerechtigung mb
            JOIN Berechtigung b ON mb.BerechtigungID = b.ID
            WHERE mb.MitarbeiterID = ? AND b.Schluessel = 'admin' AND b.Aktiv = 1
        ''', (mitarbeiter_id,)).fetchone()
        
        return admin_ber and admin_ber['count'] > 0
    finally:
        if should_close:
            conn.close()


def get_alle_berechtigungen(nur_aktive=True, conn=None):
    """
    Gibt alle verfügbaren Berechtigungen zurück
    
    Args:
        nur_aktive: Nur aktive Berechtigungen zurückgeben (Default: True)
        conn: Optional - Datenbankverbindung
    
    Returns:
        Liste von Berechtigung-Rows (ID, Schluessel, Bezeichnung, Beschreibung, Aktiv)
    """
    should_close = False
    if conn is None:
        from flask import current_app
        import sqlite3
        conn = sqlite3.connect(current_app.config['DATABASE_URL'])
        conn.row_factory = sqlite3.Row
        should_close = True
    
    try:
        if nur_aktive:
            berechtigungen = conn.execute('''
                SELECT ID, Schluessel, Bezeichnung, Beschreibung, Aktiv
                FROM Berechtigung
                WHERE Aktiv = 1
                ORDER BY Bezeichnung
            ''').fetchall()
        else:
            berechtigungen = conn.execute('''
                SELECT ID, Schluessel, Bezeichnung, Beschreibung, Aktiv
                FROM Berechtigung
                ORDER BY Bezeichnung
            ''').fetchall()
        
        return berechtigungen
    finally:
        if should_close:
            conn.close()


def mitarbeiter_berechtigung_hinzufuegen(mitarbeiter_id, berechtigung_id, conn=None):
    """
    Fügt einem Mitarbeiter eine Berechtigung hinzu
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        berechtigung_id: ID der Berechtigung
        conn: Optional - Datenbankverbindung
    
    Returns:
        True wenn erfolgreich, False wenn Fehler
    """
    should_close = False
    should_commit = False
    if conn is None:
        from flask import current_app
        import sqlite3
        conn = sqlite3.connect(current_app.config['DATABASE_URL'])
        conn.row_factory = sqlite3.Row
        should_close = True
        should_commit = True
    
    try:
        conn.execute('''
            INSERT OR IGNORE INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID)
            VALUES (?, ?)
        ''', (mitarbeiter_id, berechtigung_id))
        
        if should_commit:
            conn.commit()
        
        return True
    except Exception as e:
        if should_commit:
            conn.rollback()
        raise e
    finally:
        if should_close:
            conn.close()


def mitarbeiter_berechtigung_entfernen(mitarbeiter_id, berechtigung_id, conn=None):
    """
    Entfernt eine Berechtigung von einem Mitarbeiter
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        berechtigung_id: ID der Berechtigung
        conn: Optional - Datenbankverbindung
    
    Returns:
        True wenn erfolgreich, False wenn Fehler
    """
    should_close = False
    should_commit = False
    if conn is None:
        from flask import current_app
        import sqlite3
        conn = sqlite3.connect(current_app.config['DATABASE_URL'])
        conn.row_factory = sqlite3.Row
        should_close = True
        should_commit = True
    
    try:
        conn.execute('''
            DELETE FROM MitarbeiterBerechtigung
            WHERE MitarbeiterID = ? AND BerechtigungID = ?
        ''', (mitarbeiter_id, berechtigung_id))
        
        if should_commit:
            conn.commit()
        
        return True
    except Exception as e:
        if should_commit:
            conn.rollback()
        raise e
    finally:
        if should_close:
            conn.close()

