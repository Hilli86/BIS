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


def validate_thema_ersatzteil_buchung(ersatzteil_id, menge, thema_id, mitarbeiter_id, conn):
    """
    Validiert eine Artikel-zu-Thema-Buchung
    
    Args:
        ersatzteil_id: ID des Ersatzteils
        menge: Menge der Buchung
        thema_id: ID des Themas
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        
    Returns:
        Tuple (is_valid: bool, error_message: str, ersatzteil_data: dict, thema_data: dict)
        Bei Fehler: (False, Fehlermeldung, None, None)
        Bei Erfolg: (True, None, ersatzteil_data, thema_data)
    """
    # Grundlegende Validierung
    if not ersatzteil_id:
        return False, 'Ersatzteil-ID ist erforderlich.', None, None
    
    if not menge or menge <= 0:
        return False, 'Menge muss größer als 0 sein.', None, None
    
    if not thema_id:
        return False, 'Thema-ID ist erforderlich.', None, None
    
    # Prüfe ob Thema existiert
    thema = conn.execute('SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0', (thema_id,)).fetchone()
    if not thema:
        return False, 'Thema nicht gefunden oder nicht aktiv.', None, None
    
    # Prüfe ob Ersatzteil existiert
    ersatzteil = conn.execute('''
        SELECT ID, AktuellerBestand, Preis, Waehrung, Bezeichnung, Gelöscht, Aktiv
        FROM Ersatzteil 
        WHERE ID = ? AND Gelöscht = 0
    ''', (ersatzteil_id,)).fetchone()
    
    if not ersatzteil:
        return False, 'Ersatzteil nicht gefunden.', None, None
    
    # Prüfe Berechtigung
    if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
        return False, 'Sie haben keine Berechtigung für dieses Ersatzteil.', None, None
    
    # Prüfe ob Ersatzteil aktiv ist (für neue Themen)
    if not ersatzteil['Aktiv']:
        return False, 'Ersatzteil ist nicht aktiv.', None, None
    
    # Bestand prüfen (wird auch im Service geprüft, aber hier für frühe Validierung)
    aktueller_bestand = ersatzteil['AktuellerBestand'] or 0
    if aktueller_bestand < menge:
        return False, f'Nicht genug Bestand verfügbar! Verfügbar: {aktueller_bestand}, benötigt: {menge}.', None, None
    
    return True, None, dict(ersatzteil), dict(thema)


def prepare_thema_ersatzteil_data(ersatzteil_id, menge, thema_id, bemerkung, kostenstelle_id):
    """
    Bereitet Daten für eine Artikel-zu-Thema-Buchung vor
    
    Args:
        ersatzteil_id: ID des Ersatzteils (kann String oder int sein)
        menge: Menge (kann String oder int sein)
        thema_id: ID des Themas
        bemerkung: Bemerkung (kann None oder String sein)
        kostenstelle_id: Kostenstellen-ID (kann None, String oder int sein)
        
    Returns:
        Tuple (ersatzteil_id: int, menge: int, bemerkung: str|None, kostenstelle_id: int|None, error: str|None)
    """
    try:
        # Normalisiere Ersatzteil-ID
        if isinstance(ersatzteil_id, str):
            ersatzteil_id = int(ersatzteil_id.strip()) if ersatzteil_id.strip() else None
        elif ersatzteil_id is None:
            return None, None, None, None, 'Ersatzteil-ID ist erforderlich.'
        
        # Normalisiere Menge
        if isinstance(menge, str):
            menge = int(menge.strip()) if menge.strip() else None
        elif menge is None:
            return None, None, None, None, 'Menge ist erforderlich.'
        
        if menge <= 0:
            return None, None, None, None, 'Menge muss größer als 0 sein.'
        
        # Normalisiere Bemerkung
        if bemerkung:
            bemerkung = bemerkung.strip() if isinstance(bemerkung, str) else None
        else:
            bemerkung = None
        
        # Normalisiere Kostenstelle
        if kostenstelle_id:
            if isinstance(kostenstelle_id, str):
                kostenstelle_id = int(kostenstelle_id.strip()) if kostenstelle_id.strip() else None
            else:
                kostenstelle_id = int(kostenstelle_id)
        else:
            kostenstelle_id = None
        
        return ersatzteil_id, menge, bemerkung, kostenstelle_id, None
        
    except (ValueError, TypeError) as e:
        return None, None, None, None, f'Ungültige Eingabewerte: {str(e)}'

