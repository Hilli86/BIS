"""
Benachrichtigungs-Utilities
Funktionen zum Erstellen und Verwalten von Benachrichtigungen
"""

from utils import get_db_connection


def erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id_erstellt, conn=None):
    """
    Erstellt Benachrichtigungen für alle Mitarbeiter, die bereits eine Bemerkung zu diesem Thema haben
    (außer dem Ersteller der neuen Bemerkung)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id_erstellt, conn)
    
    # Alle Mitarbeiter finden, die bereits eine Bemerkung zu diesem Thema haben
    mitarbeiter_mit_bemerkungen = conn.execute('''
        SELECT DISTINCT BM.MitarbeiterID, M.Vorname, M.Nachname
        FROM SchichtbuchBemerkungen BM
        JOIN Mitarbeiter M ON BM.MitarbeiterID = M.ID
        WHERE BM.ThemaID = ? 
        AND BM.MitarbeiterID != ?
        AND BM.Gelöscht = 0
        AND M.Aktiv = 1
    ''', (thema_id, mitarbeiter_id_erstellt)).fetchall()
    
    # Thema-Informationen holen
    thema_info = conn.execute('''
        SELECT 
            T.ID,
            G.Bezeichnung AS Gewerk,
            B.Bezeichnung AS Bereich
        FROM SchichtbuchThema T
        JOIN Gewerke G ON T.GewerkID = G.ID
        JOIN Bereich B ON G.BereichID = B.ID
        WHERE T.ID = ?
    ''', (thema_id,)).fetchone()
    
    if not thema_info:
        return
    
    # Erstellername holen
    ersteller = conn.execute('''
        SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?
    ''', (mitarbeiter_id_erstellt,)).fetchone()
    
    ersteller_name = f"{ersteller['Vorname']} {ersteller['Nachname']}".strip() if ersteller else "Ein Benutzer"
    
    # Benachrichtigungen erstellen
    for mitarbeiter in mitarbeiter_mit_bemerkungen:
        titel = f"Neue Bemerkung zu Thema #{thema_id}"
        nachricht = f"{ersteller_name} hat eine neue Bemerkung zu '{thema_info['Bereich']} / {thema_info['Gewerk']}' hinzugefügt."
        
        conn.execute('''
            INSERT INTO Benachrichtigung (MitarbeiterID, ThemaID, BemerkungID, Typ, Titel, Nachricht)
            VALUES (?, ?, ?, 'neue_bemerkung', ?, ?)
        ''', (mitarbeiter['MitarbeiterID'], thema_id, bemerkung_id, titel, nachricht))


def erstelle_benachrichtigung_fuer_neues_thema(thema_id, sichtbare_abteilungen, conn=None):
    """
    Erstellt Benachrichtigungen für alle Mitarbeiter in den sichtbaren Abteilungen
    (außer dem Ersteller)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_neues_thema(thema_id, sichtbare_abteilungen, conn)
    
    if not sichtbare_abteilungen:
        return
    
    # Thema-Informationen holen
    thema_info = conn.execute('''
        SELECT 
            T.ID,
            T.ErstellerAbteilungID,
            G.Bezeichnung AS Gewerk,
            B.Bezeichnung AS Bereich
        FROM SchichtbuchThema T
        JOIN Gewerke G ON T.GewerkID = G.ID
        JOIN Bereich B ON G.BereichID = B.ID
        WHERE T.ID = ?
    ''', (thema_id,)).fetchone()
    
    if not thema_info:
        return
    
    # Ersteller-ID ermitteln (über erste Bemerkung)
    ersteller = conn.execute('''
        SELECT MitarbeiterID FROM SchichtbuchBemerkungen 
        WHERE ThemaID = ? AND Gelöscht = 0 
        ORDER BY Datum ASC LIMIT 1
    ''', (thema_id,)).fetchone()
    
    ersteller_id = ersteller['MitarbeiterID'] if ersteller else None
    
    # Alle Mitarbeiter in den sichtbaren Abteilungen finden
    if not sichtbare_abteilungen:
        return
    
    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
    params = sichtbare_abteilungen + sichtbare_abteilungen + ([ersteller_id] if ersteller_id else [0])
    
    mitarbeiter = conn.execute(f'''
        SELECT DISTINCT M.ID
        FROM Mitarbeiter M
        WHERE M.Aktiv = 1
        AND (
            M.PrimaerAbteilungID IN ({placeholders})
            OR EXISTS (
                SELECT 1 FROM MitarbeiterAbteilung MA
                WHERE MA.MitarbeiterID = M.ID
                AND MA.AbteilungID IN ({placeholders})
            )
        )
        AND M.ID != ?
    ''', params).fetchall()
    
    # Benachrichtigungen erstellen
    titel = f"Neues Thema #{thema_id}"
    nachricht = f"Ein neues Thema '{thema_info['Bereich']} / {thema_info['Gewerk']}' wurde erstellt."
    
    for ma in mitarbeiter:
        conn.execute('''
            INSERT INTO Benachrichtigung (MitarbeiterID, ThemaID, Typ, Titel, Nachricht)
            VALUES (?, ?, 'neues_thema', ?, ?)
        ''', (ma['ID'], thema_id, titel, nachricht))

