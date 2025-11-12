"""
Hilfsfunktionen für Firmendaten
"""

from utils import get_db_connection


def get_firmendaten():
    """Lädt die Firmendaten aus der Datenbank"""
    with get_db_connection() as conn:
        firmendaten = conn.execute('SELECT * FROM Firmendaten LIMIT 1').fetchone()
        return firmendaten

