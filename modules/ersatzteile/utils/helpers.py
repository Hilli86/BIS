"""
Helper Utilities für Ersatzteile-Modul
"""

from flask import session
from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import safe_get


def hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
    """Prüft ob Mitarbeiter Zugriff auf Ersatzteil hat"""
    # Admin hat immer Zugriff
    if 'admin' in session.get('user_berechtigungen', []):
        return True
    
    # Prüfe ob Benutzer der Ersteller ist
    ersatzteil = conn.execute('SELECT ErstelltVonID FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
    if ersatzteil and ersatzteil['ErstelltVonID'] == mitarbeiter_id:
        return True
    
    # Prüfe ob Ersatzteil für Abteilungen des Mitarbeiters freigegeben ist
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    if not sichtbare_abteilungen:
        return False
    
    from utils.helpers import build_sichtbarkeits_filter_query
    query, params = build_sichtbarkeits_filter_query(
        'SELECT COUNT(*) as count FROM ErsatzteilAbteilungZugriff WHERE ErsatzteilID = ?',
        sichtbare_abteilungen,
        [ersatzteil_id],
        table_alias='',
        sichtbarkeit_table='ErsatzteilAbteilungZugriff',
        sichtbarkeit_id_column='ErsatzteilID'
    )
    
    # Vereinfachte Version für Ersatzteile
    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
    zugriff = conn.execute(f'''
        SELECT COUNT(*) as count FROM ErsatzteilAbteilungZugriff
        WHERE ErsatzteilID = ? AND AbteilungID IN ({placeholders})
    ''', [ersatzteil_id] + sichtbare_abteilungen).fetchone()
    
    return zugriff['count'] > 0

