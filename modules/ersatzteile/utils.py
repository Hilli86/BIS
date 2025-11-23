"""
Gemeinsame Hilfsfunktionen für Ersatzteile-Modul
"""

import os
from flask import current_app, session
from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import row_to_dict


def hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
    """Prüft ob Mitarbeiter Zugriff auf Ersatzteil hat"""
    # Admin hat immer Zugriff
    if 'admin' in session.get('user_berechtigungen', []):
        return True
    
    # Prüfe ob Benutzer der Ersteller ist
    ersatzteil_row = conn.execute('SELECT ErstelltVonID FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
    ersatzteil = row_to_dict(ersatzteil_row)
    if ersatzteil and ersatzteil.get('ErstelltVonID') == mitarbeiter_id:
        return True
    
    # Prüfe ob Ersatzteil für Abteilungen des Mitarbeiters freigegeben ist
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    if not sichtbare_abteilungen:
        return False
    
    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
    zugriff_row = conn.execute(f'''
        SELECT COUNT(*) as count FROM ErsatzteilAbteilungZugriff
        WHERE ErsatzteilID = ? AND AbteilungID IN ({placeholders})
    ''', [ersatzteil_id] + sichtbare_abteilungen).fetchone()
    zugriff = row_to_dict(zugriff_row)
    
    return zugriff and zugriff.get('count', 0) > 0


def get_datei_anzahl(ersatzteil_id, typ='bild'):
    """Ermittelt die Anzahl der Dateien für ein Ersatzteil"""
    ersatzteil_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), typ)
    if not os.path.exists(ersatzteil_folder):
        return 0
    try:
        files = os.listdir(ersatzteil_folder)
        return len([f for f in files if os.path.isfile(os.path.join(ersatzteil_folder, f))])
    except:
        return 0


def allowed_file(filename):
    """Prüft ob Dateityp erlaubt ist"""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.doc', '.docx'})
    return '.' in filename and os.path.splitext(filename)[1].lower() in allowed_extensions

