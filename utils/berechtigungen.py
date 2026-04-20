"""
Berechtigungs-Utilities
Hilfsfunktionen für die Prüfung von Mitarbeiter-Berechtigungen
"""

from utils.database import get_db_connection
from utils.db_sql import upsert_ignore


def get_mitarbeiter_berechtigungen(mitarbeiter_id, conn=None):
    """
    Gibt alle Berechtigungen eines Mitarbeiters zurück

    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Optional - Datenbankverbindung (wird erstellt wenn nicht übergeben)

    Returns:
        Liste von Berechtigungs-Schlüsseln (z.B. ['admin', 'artikel_buchen'])
    """
    if conn is None:
        with get_db_connection() as conn:
            return get_mitarbeiter_berechtigungen(mitarbeiter_id, conn)

    berechtigungen = conn.execute('''
        SELECT b.Schluessel
        FROM MitarbeiterBerechtigung mb
        JOIN Berechtigung b ON mb.BerechtigungID = b.ID
        WHERE mb.MitarbeiterID = ? AND b.Aktiv = 1
    ''', (mitarbeiter_id,)).fetchall()

    return [b['Schluessel'] for b in berechtigungen]


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
    if conn is None:
        with get_db_connection() as conn:
            return ist_admin(mitarbeiter_id, conn)

    admin_ber = conn.execute('''
        SELECT COUNT(*) as count
        FROM MitarbeiterBerechtigung mb
        JOIN Berechtigung b ON mb.BerechtigungID = b.ID
        WHERE mb.MitarbeiterID = ? AND b.Schluessel = 'admin' AND b.Aktiv = 1
    ''', (mitarbeiter_id,)).fetchone()

    return admin_ber and admin_ber['count'] > 0


def get_alle_berechtigungen(nur_aktive=True, conn=None):
    """
    Gibt alle verfügbaren Berechtigungen zurück

    Args:
        nur_aktive: Nur aktive Berechtigungen zurückgeben (Default: True)
        conn: Optional - Datenbankverbindung

    Returns:
        Liste von Berechtigung-Rows (ID, Schluessel, Bezeichnung, Beschreibung, Aktiv)
    """
    if conn is None:
        with get_db_connection() as conn:
            return get_alle_berechtigungen(nur_aktive=nur_aktive, conn=conn)

    if nur_aktive:
        return conn.execute('''
            SELECT ID, Schluessel, Bezeichnung, Beschreibung, Aktiv
            FROM Berechtigung
            WHERE Aktiv = 1
            ORDER BY Bezeichnung
        ''').fetchall()
    return conn.execute('''
        SELECT ID, Schluessel, Bezeichnung, Beschreibung, Aktiv
        FROM Berechtigung
        ORDER BY Bezeichnung
    ''').fetchall()


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
    if conn is None:
        with get_db_connection() as conn:
            return mitarbeiter_berechtigung_hinzufuegen(mitarbeiter_id, berechtigung_id, conn)

    sql = upsert_ignore(
        'MitarbeiterBerechtigung',
        ('MitarbeiterID', 'BerechtigungID'),
        ('MitarbeiterID', 'BerechtigungID'),
    )
    conn.execute(sql, (mitarbeiter_id, berechtigung_id))
    return True


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
    if conn is None:
        with get_db_connection() as conn:
            return mitarbeiter_berechtigung_entfernen(mitarbeiter_id, berechtigung_id, conn)

    conn.execute('''
        DELETE FROM MitarbeiterBerechtigung
        WHERE MitarbeiterID = ? AND BerechtigungID = ?
    ''', (mitarbeiter_id, berechtigung_id))
    return True
