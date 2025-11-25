"""
Benachrichtigungs-Utilities
Funktionen zum Erstellen und Verwalten von Benachrichtigungen
"""

import json
import logging
from utils import get_db_connection

# Logger für Benachrichtigungen
logger = logging.getLogger(__name__)


def get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, abteilung_id=None, conn=None):
    """
    Prüft ob eine Benachrichtigung für einen Mitarbeiter aktiviert ist.
    
    Logik:
    - Wenn abteilung_id gesetzt ist: Prüfe zuerst spezifische Einstellung (mit Abteilung)
      - Wenn gefunden und Aktiv=0: return False
      - Wenn gefunden und Aktiv=1: return True
      - Wenn nicht gefunden: Prüfe allgemeine Einstellung (ohne Abteilung)
    - Wenn abteilung_id None ist: Prüfe nur allgemeine Einstellung
    - Wenn keine Einstellung gefunden: return False (Standard: deaktiviert)
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        modul: Modul (z.B. 'schichtbuch', 'bestellwesen')
        aktion: Aktion (z.B. 'neues_thema', 'neue_bemerkung')
        abteilung_id: AbteilungID (None = alle Abteilungen)
        conn: Datenbankverbindung (optional)
    
    Returns:
        True wenn Benachrichtigung aktiviert ist, False sonst
    """
    if conn is None:
        with get_db_connection() as conn:
            return get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, abteilung_id, conn)
    
    # Wenn abteilung_id gesetzt ist: Prüfe zuerst spezifische Einstellung (mit Abteilung)
    if abteilung_id is not None:
        einstellung = conn.execute('''
            SELECT Aktiv FROM BenachrichtigungEinstellung
            WHERE MitarbeiterID = ? AND Modul = ? AND Aktion = ? AND AbteilungID = ?
        ''', (mitarbeiter_id, modul, aktion, abteilung_id)).fetchone()
        if einstellung:
            aktiv = bool(einstellung['Aktiv'])
            logger.debug(f"Benachrichtigungseinstellung gefunden (spezifisch): MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, AbteilungID={abteilung_id}, Aktiv={aktiv}")
            return aktiv
    
    # Prüfe allgemeine Einstellung (alle Abteilungen)
    einstellung = conn.execute('''
        SELECT Aktiv FROM BenachrichtigungEinstellung
        WHERE MitarbeiterID = ? AND Modul = ? AND Aktion = ? AND AbteilungID IS NULL
    ''', (mitarbeiter_id, modul, aktion)).fetchone()
    if einstellung:
        aktiv = bool(einstellung['Aktiv'])
        logger.debug(f"Benachrichtigungseinstellung gefunden (allgemein): MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, Aktiv={aktiv}")
        return aktiv
    
    # Standard: Benachrichtigung ist deaktiviert (wenn keine Einstellung vorhanden)
    logger.debug(f"Keine Benachrichtigungseinstellung gefunden, verwende Standard (deaktiviert): MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, AbteilungID={abteilung_id}")
    return False


def get_aktive_benachrichtigungskanaele(mitarbeiter_id, conn=None):
    """
    Gibt alle aktiven Benachrichtigungskanäle für einen Mitarbeiter zurück.
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung (optional)
    
    Returns:
        Liste von KanalTypen (z.B. ['app', 'mail'])
    """
    if conn is None:
        with get_db_connection() as conn:
            return get_aktive_benachrichtigungskanaele(mitarbeiter_id, conn)
    
    kanale = conn.execute('''
        SELECT KanalTyp FROM BenachrichtigungKanal
        WHERE MitarbeiterID = ? AND Aktiv = 1
    ''', (mitarbeiter_id,)).fetchall()
    
    return [k['KanalTyp'] for k in kanale] if kanale else []  # Standard: keine Kanäle


def erstelle_benachrichtigung_mit_filter(modul, aktion, mitarbeiter_id, titel, nachricht, 
                                        thema_id=None, bemerkung_id=None, abteilung_id=None, 
                                        zusatzdaten=None, conn=None):
    """
    Erstellt eine Benachrichtigung mit Filterung basierend auf Einstellungen.
    
    Args:
        modul: Modul (z.B. 'schichtbuch', 'bestellwesen')
        aktion: Aktion (z.B. 'neues_thema', 'neue_bemerkung')
        mitarbeiter_id: ID des Mitarbeiters, der benachrichtigt werden soll
        titel: Titel der Benachrichtigung
        nachricht: Nachricht der Benachrichtigung
        thema_id: ThemaID (optional, für Schichtbuch)
        bemerkung_id: BemerkungID (optional, für Schichtbuch)
        abteilung_id: AbteilungID (optional)
        zusatzdaten: Zusätzliche Daten als Dict (wird als JSON gespeichert)
        conn: Datenbankverbindung (optional)
    
    Returns:
        ID der erstellten Benachrichtigung oder None
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_mit_filter(
                modul, aktion, mitarbeiter_id, titel, nachricht,
                thema_id, bemerkung_id, abteilung_id, zusatzdaten, conn
            )
    
    # Prüfe ob Benachrichtigung aktiviert ist
    if not get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, abteilung_id, conn):
        logger.info(f"Benachrichtigung nicht erstellt: Einstellung deaktiviert - MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, AbteilungID={abteilung_id}")
        return None
    
    # Für Schichtbuch: ThemaID ist erforderlich
    if modul == 'schichtbuch' and thema_id is None:
        logger.warning(f"Benachrichtigung nicht erstellt: ThemaID fehlt für Schichtbuch - MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}")
        return None
    
    # Zusatzdaten als JSON speichern
    zusatzdaten_json = json.dumps(zusatzdaten) if zusatzdaten else None
    
    try:
        # Erstelle Benachrichtigung
        cursor = conn.execute('''
            INSERT INTO Benachrichtigung (
                MitarbeiterID, ThemaID, BemerkungID, Typ, Titel, Nachricht,
                Modul, Aktion, AbteilungID, Zusatzdaten
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            mitarbeiter_id,
            thema_id if thema_id else 0,  # SQLite erfordert NOT NULL, verwende 0 als Platzhalter
            bemerkung_id,
            aktion,  # Typ wird durch Aktion ersetzt
            titel,
            nachricht,
            modul,
            aktion,
            abteilung_id,
            zusatzdaten_json
        ))
        
        benachrichtigung_id = cursor.lastrowid
        logger.info(f"Benachrichtigung erstellt: ID={benachrichtigung_id}, MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, Titel={titel[:50]}")
        
        # Versende Benachrichtigung über aktive Kanäle
        aktive_kanale = get_aktive_benachrichtigungskanaele(mitarbeiter_id, conn)
        for kanal_typ in aktive_kanale:
            if kanal_typ != 'app':  # App-Benachrichtigungen werden direkt angezeigt
                # Erstelle Versand-Eintrag
                conn.execute('''
                    INSERT INTO BenachrichtigungVersand (
                        BenachrichtigungID, KanalTyp, Status
                    )
                    VALUES (?, ?, 'pending')
                ''', (benachrichtigung_id, kanal_typ))
                logger.debug(f"Versand-Eintrag erstellt: BenachrichtigungID={benachrichtigung_id}, KanalTyp={kanal_typ}")
        
        return benachrichtigung_id
    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Benachrichtigung: MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, Fehler={str(e)}", exc_info=True)
        raise


def erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id_erstellt, conn=None):
    """
    Erstellt Benachrichtigungen für alle Mitarbeiter, die bereits eine Bemerkung zu diesem Thema haben
    (außer dem Ersteller der neuen Bemerkung)
    Nutzt jetzt die neue Filterlogik.
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id_erstellt, conn)
    
    logger.info(f"Erstelle Benachrichtigungen für neue Bemerkung: ThemaID={thema_id}, BemerkungID={bemerkung_id}, ErstellerID={mitarbeiter_id_erstellt}")
    
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
    
    logger.debug(f"Gefundene Mitarbeiter mit Bemerkungen zu Thema {thema_id}: {len(mitarbeiter_mit_bemerkungen)}")
    
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
        logger.warning(f"Thema {thema_id} nicht gefunden, keine Benachrichtigungen erstellt")
        return
    
    # Erstellername holen
    ersteller = conn.execute('''
        SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?
    ''', (mitarbeiter_id_erstellt,)).fetchone()
    
    ersteller_name = f"{ersteller['Vorname']} {ersteller['Nachname']}".strip() if ersteller else "Ein Benutzer"
    
    # Benachrichtigungen erstellen mit Filterlogik
    titel = f"Neue Bemerkung zu Thema #{thema_id}"
    nachricht = f"{ersteller_name} hat eine neue Bemerkung zu '{thema_info['Bereich']} / {thema_info['Gewerk']}' hinzugefügt."
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    for mitarbeiter in mitarbeiter_mit_bemerkungen:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='schichtbuch',
            aktion='neue_bemerkung',
            mitarbeiter_id=mitarbeiter['MitarbeiterID'],
            titel=titel,
            nachricht=nachricht,
            thema_id=thema_id,
            bemerkung_id=bemerkung_id,
            abteilung_id=thema_info.get('ErstellerAbteilungID'),
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für neue Bemerkung erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (ThemaID={thema_id})")


def erstelle_benachrichtigung_fuer_neues_thema(thema_id, sichtbare_abteilungen, conn=None):
    """
    Erstellt Benachrichtigungen für alle Mitarbeiter in den sichtbaren Abteilungen
    (außer dem Ersteller)
    Nutzt jetzt die neue Filterlogik.
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_neues_thema(thema_id, sichtbare_abteilungen, conn)
    
    if not sichtbare_abteilungen:
        logger.warning(f"Keine sichtbaren Abteilungen für Thema {thema_id}, keine Benachrichtigungen erstellt")
        return
    
    logger.info(f"Erstelle Benachrichtigungen für neues Thema: ThemaID={thema_id}, SichtbareAbteilungen={sichtbare_abteilungen}")
    
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
        logger.warning(f"Thema {thema_id} nicht gefunden, keine Benachrichtigungen erstellt")
        return
    
    # Ersteller-ID ermitteln (über erste Bemerkung)
    ersteller = conn.execute('''
        SELECT MitarbeiterID FROM SchichtbuchBemerkungen 
        WHERE ThemaID = ? AND Gelöscht = 0 
        ORDER BY Datum ASC LIMIT 1
    ''', (thema_id,)).fetchone()
    
    ersteller_id = ersteller['MitarbeiterID'] if ersteller else None
    
    # Alle Mitarbeiter in den sichtbaren Abteilungen finden
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
    
    logger.debug(f"Gefundene Mitarbeiter in sichtbaren Abteilungen: {len(mitarbeiter)}")
    
    # Benachrichtigungen erstellen mit Filterlogik
    titel = f"Neues Thema #{thema_id}"
    nachricht = f"Ein neues Thema '{thema_info['Bereich']} / {thema_info['Gewerk']}' wurde erstellt."
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='schichtbuch',
            aktion='neues_thema',
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            thema_id=thema_id,
            abteilung_id=thema_info.get('ErstellerAbteilungID'),
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für neues Thema erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (ThemaID={thema_id})")


# ========== Bestellwesen-Benachrichtigungen ==========

def erstelle_benachrichtigung_fuer_angebotsanfrage(angebotsanfrage_id, aktion, conn=None):
    """
    Erstellt Benachrichtigungen für Angebotsanfragen.
    
    Args:
        angebotsanfrage_id: ID der Angebotsanfrage
        aktion: Aktion ('neue_angebotsanfrage', 'angebotsanfrage_bearbeitet', etc.)
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_angebotsanfrage(angebotsanfrage_id, aktion, conn)
    
    # Angebotsanfrage-Informationen holen
    anfrage = conn.execute('''
        SELECT 
            AA.ID,
            AA.ErstellerAbteilungID,
            AA.Status,
            L.Name AS LieferantName,
            M.Vorname || ' ' || M.Nachname AS ErstellerName
        FROM Angebotsanfrage AA
        JOIN Lieferant L ON AA.LieferantID = L.ID
        JOIN Mitarbeiter M ON AA.ErstelltVonID = M.ID
        WHERE AA.ID = ?
    ''', (angebotsanfrage_id,)).fetchone()
    
    if not anfrage:
        return
    
    # Titel und Nachricht je nach Aktion
    aktionen = {
        'neue_angebotsanfrage': ('Neue Angebotsanfrage', f"Eine neue Angebotsanfrage #{angebotsanfrage_id} wurde erstellt."),
        'angebotsanfrage_bearbeitet': ('Angebotsanfrage bearbeitet', f"Die Angebotsanfrage #{angebotsanfrage_id} wurde bearbeitet."),
        'angebotsanfrage_preise_eingegeben': ('Preise eingegeben', f"Preise für Angebotsanfrage #{angebotsanfrage_id} wurden eingegeben."),
    }
    
    titel, nachricht = aktionen.get(aktion, (f"Angebotsanfrage #{angebotsanfrage_id}", f"Aktion bei Angebotsanfrage #{angebotsanfrage_id}"))
    
    logger.info(f"Erstelle Benachrichtigungen für Angebotsanfrage: AngebotsanfrageID={angebotsanfrage_id}, Aktion={aktion}")
    
    # Alle Mitarbeiter in der Abteilung finden (außer Ersteller)
    mitarbeiter = conn.execute('''
        SELECT DISTINCT M.ID
        FROM Mitarbeiter M
        WHERE M.Aktiv = 1
        AND (
            M.PrimaerAbteilungID = ?
            OR EXISTS (
                SELECT 1 FROM MitarbeiterAbteilung MA
                WHERE MA.MitarbeiterID = M.ID
                AND MA.AbteilungID = ?
            )
        )
        AND M.ID != (SELECT ErstelltVonID FROM Angebotsanfrage WHERE ID = ?)
    ''', (anfrage['ErstellerAbteilungID'], anfrage['ErstellerAbteilungID'], angebotsanfrage_id)).fetchall()
    
    logger.debug(f"Gefundene Mitarbeiter für Angebotsanfrage {angebotsanfrage_id}: {len(mitarbeiter)}")
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    # Benachrichtigungen erstellen
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='bestellwesen',
            aktion=aktion,
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            abteilung_id=anfrage['ErstellerAbteilungID'],
            zusatzdaten={'angebotsanfrage_id': angebotsanfrage_id, 'lieferant': anfrage['LieferantName']},
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für Angebotsanfrage erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (AngebotsanfrageID={angebotsanfrage_id})")


def erstelle_benachrichtigung_fuer_bestellung(bestellung_id, aktion, conn=None):
    """
    Erstellt Benachrichtigungen für Bestellungen.
    
    Args:
        bestellung_id: ID der Bestellung
        aktion: Aktion ('neue_bestellung', 'bestellung_zur_freigabe', 'bestellung_freigegeben', 'bestellung_bestellt', etc.)
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_bestellung(bestellung_id, aktion, conn)
    
    # Bestellungs-Informationen holen
    bestellung = conn.execute('''
        SELECT 
            B.ID,
            B.ErstellerAbteilungID,
            B.Status,
            L.Name AS LieferantName,
            M.Vorname || ' ' || M.Nachname AS ErstellerName
        FROM Bestellung B
        JOIN Lieferant L ON B.LieferantID = L.ID
        JOIN Mitarbeiter M ON B.ErstelltVonID = M.ID
        WHERE B.ID = ?
    ''', (bestellung_id,)).fetchone()
    
    if not bestellung:
        return
    
    # Titel und Nachricht je nach Aktion
    aktionen = {
        'neue_bestellung': ('Neue Bestellung', f"Eine neue Bestellung #{bestellung_id} wurde erstellt."),
        'bestellung_zur_freigabe': ('Bestellung zur Freigabe', f"Bestellung #{bestellung_id} wartet auf Freigabe."),
        'bestellung_freigegeben': ('Bestellung freigegeben', f"Bestellung #{bestellung_id} wurde freigegeben."),
        'bestellung_bestellt': ('Bestellung aufgegeben', f"Bestellung #{bestellung_id} wurde beim Lieferanten aufgegeben."),
    }
    
    titel, nachricht = aktionen.get(aktion, (f"Bestellung #{bestellung_id}", f"Aktion bei Bestellung #{bestellung_id}"))
    
    logger.info(f"Erstelle Benachrichtigungen für Bestellung: BestellungID={bestellung_id}, Aktion={aktion}")
    
    # Für Freigabe: Benachrichtige alle mit Freigabeberechtigung
    if aktion == 'bestellung_zur_freigabe':
        mitarbeiter = conn.execute('''
            SELECT DISTINCT M.ID
            FROM Mitarbeiter M
            JOIN MitarbeiterBerechtigung MB ON M.ID = MB.MitarbeiterID
            JOIN Berechtigung B ON MB.BerechtigungID = B.ID
            WHERE M.Aktiv = 1
            AND B.Schluessel = 'bestellungen_freigeben'
            AND B.Aktiv = 1
        ''').fetchall()
        logger.debug(f"Gefundene Mitarbeiter mit Freigabeberechtigung: {len(mitarbeiter)}")
    else:
        # Alle Mitarbeiter in der Abteilung finden (außer Ersteller)
        mitarbeiter = conn.execute('''
            SELECT DISTINCT M.ID
            FROM Mitarbeiter M
            WHERE M.Aktiv = 1
            AND (
                M.PrimaerAbteilungID = ?
                OR EXISTS (
                    SELECT 1 FROM MitarbeiterAbteilung MA
                    WHERE MA.MitarbeiterID = M.ID
                    AND MA.AbteilungID = ?
                )
            )
            AND M.ID != (SELECT ErstelltVonID FROM Bestellung WHERE ID = ?)
        ''', (bestellung['ErstellerAbteilungID'], bestellung['ErstellerAbteilungID'], bestellung_id)).fetchall()
        logger.debug(f"Gefundene Mitarbeiter in Abteilung für Bestellung {bestellung_id}: {len(mitarbeiter)}")
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    # Benachrichtigungen erstellen
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='bestellwesen',
            aktion=aktion,
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            abteilung_id=bestellung['ErstellerAbteilungID'],
            zusatzdaten={'bestellung_id': bestellung_id, 'lieferant': bestellung['LieferantName']},
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für Bestellung erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (BestellungID={bestellung_id})")


def erstelle_benachrichtigung_fuer_wareneingang(bestellung_id, conn=None):
    """
    Erstellt Benachrichtigungen für Wareneingang.
    
    Args:
        bestellung_id: ID der Bestellung
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_wareneingang(bestellung_id, conn)
    
    # Bestellungs-Informationen holen
    bestellung = conn.execute('''
        SELECT 
            B.ID,
            B.ErstellerAbteilungID,
            L.Name AS LieferantName
        FROM Bestellung B
        JOIN Lieferant L ON B.LieferantID = L.ID
        WHERE B.ID = ?
    ''', (bestellung_id,)).fetchone()
    
    if not bestellung:
        return
    
    logger.info(f"Erstelle Benachrichtigungen für Wareneingang: BestellungID={bestellung_id}")
    
    titel = f"Wareneingang für Bestellung #{bestellung_id}"
    nachricht = f"Wareneingang für Bestellung #{bestellung_id} wurde gebucht."
    
    # Alle Mitarbeiter in der Abteilung finden
    mitarbeiter = conn.execute('''
        SELECT DISTINCT M.ID
        FROM Mitarbeiter M
        WHERE M.Aktiv = 1
        AND (
            M.PrimaerAbteilungID = ?
            OR EXISTS (
                SELECT 1 FROM MitarbeiterAbteilung MA
                WHERE MA.MitarbeiterID = M.ID
                AND MA.AbteilungID = ?
            )
        )
    ''', (bestellung['ErstellerAbteilungID'], bestellung['ErstellerAbteilungID'])).fetchall()
    
    logger.debug(f"Gefundene Mitarbeiter für Wareneingang Bestellung {bestellung_id}: {len(mitarbeiter)}")
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    # Benachrichtigungen erstellen
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='bestellwesen',
            aktion='wareneingang',
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            abteilung_id=bestellung['ErstellerAbteilungID'],
            zusatzdaten={'bestellung_id': bestellung_id, 'lieferant': bestellung['LieferantName']},
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für Wareneingang erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (BestellungID={bestellung_id})")


# ========== Versand-Funktionen ==========

def versende_benachrichtigung(benachrichtigung_id, kanal_typ, conn=None):
    """
    Versendet eine Benachrichtigung über einen spezifischen Kanal.
    Diese Funktion wird von den spezifischen Kanal-Implementierungen aufgerufen.
    
    Args:
        benachrichtigung_id: ID der Benachrichtigung
        kanal_typ: Kanal-Typ ('mail', 'push', etc.)
        conn: Datenbankverbindung (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_benachrichtigung(benachrichtigung_id, kanal_typ, conn)
    
    # Importiere spezifische Versand-Module
    try:
        if kanal_typ == 'mail':
            from utils.benachrichtigungen_mail import versende_mail_benachrichtigung
            erfolg = versende_mail_benachrichtigung(benachrichtigung_id, conn)
        elif kanal_typ == 'push':
            from utils.benachrichtigungen_push import versende_push_benachrichtigung
            erfolg = versende_push_benachrichtigung(benachrichtigung_id, conn)
        else:
            # Unbekannter Kanal
            erfolg = False
    except ImportError:
        # Modul nicht verfügbar
        erfolg = False
    except Exception as e:
        logger.error(f"Fehler beim Versenden der Benachrichtigung {benachrichtigung_id} über {kanal_typ}: {e}", exc_info=True)
        erfolg = False
    
    # Aktualisiere Versand-Status
    if erfolg:
        conn.execute('''
            UPDATE BenachrichtigungVersand
            SET Status = 'sent', VersandAm = datetime('now')
            WHERE BenachrichtigungID = ? AND KanalTyp = ?
        ''', (benachrichtigung_id, kanal_typ))
    else:
        conn.execute('''
            UPDATE BenachrichtigungVersand
            SET Status = 'failed', VersandAm = datetime('now'), Fehlermeldung = ?
            WHERE BenachrichtigungID = ? AND KanalTyp = ?
        ''', (f"Fehler beim Versenden über {kanal_typ}", benachrichtigung_id, kanal_typ))
    
    return erfolg


def versende_alle_benachrichtigungen(conn=None):
    """
    Versendet alle ausstehenden Benachrichtigungen.
    Sollte regelmäßig (z.B. per Cron-Job) aufgerufen werden.
    
    Args:
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_alle_benachrichtigungen(conn)
    
    # Hole alle ausstehenden Versand-Einträge
    versand_eintraege = conn.execute('''
        SELECT BV.BenachrichtigungID, BV.KanalTyp
        FROM BenachrichtigungVersand BV
        WHERE BV.Status = 'pending'
        ORDER BY BV.ID ASC
        LIMIT 100
    ''').fetchall()
    
    erfolg_count = 0
    fehler_count = 0
    
    for eintrag in versand_eintraege:
        if versende_benachrichtigung(eintrag['BenachrichtigungID'], eintrag['KanalTyp'], conn):
            erfolg_count += 1
        else:
            fehler_count += 1
    
    return {'erfolg': erfolg_count, 'fehler': fehler_count}

