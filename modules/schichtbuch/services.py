"""
Schichtbuch Services
Business-Logik für Schichtbuch-Funktionen
"""

from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_sichtbarkeits_filter_query


def build_themen_query(sichtbare_abteilungen, bereich_filter=None, gewerk_filter=None, 
                       status_filter_list=None, q_filter=None, limit=None, offset=None, mitarbeiter_id=None):
    """
    Baut die SQL-Query für Themenliste auf
    
    Args:
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        bereich_filter: Optionaler Bereichs-Filter
        gewerk_filter: Optionaler Gewerks-Filter
        status_filter_list: Optionaler Status-Filter (Liste)
        q_filter: Optionaler Such-Filter
        limit: Optionales Limit
        offset: Optionales Offset
        mitarbeiter_id: Optional: ID des Mitarbeiters (für Anzeige selbst erstellter Themen)
        
    Returns:
        Tuple (query, params)
    """
    query = '''
        SELECT 
            t.ID,
            b.Bezeichnung AS Bereich,
            g.Bezeichnung AS Gewerk,
            s.Bezeichnung AS Status,
            s.Farbe AS Farbe,
            abt.Bezeichnung AS Abteilung,
            COALESCE(MAX(bm.Datum), '1900-01-01') AS LetzteBemerkungDatum,
            COALESCE(MAX(bm.MitarbeiterID), 0) AS LetzteMitarbeiterID,
            COALESCE(MAX(m.Vorname), '') AS LetzteMitarbeiterVorname,
            COALESCE(MAX(m.Nachname), '') AS LetzteMitarbeiterNachname,
            COALESCE(MAX(ta.Bezeichnung), '') AS LetzteTatigkeit
        FROM SchichtbuchThema t
        JOIN Gewerke g ON t.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Status s ON t.StatusID = s.ID
        LEFT JOIN Abteilung abt ON t.ErstellerAbteilungID = abt.ID
        LEFT JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID AND bm.Gelöscht = 0
        LEFT JOIN Mitarbeiter m ON bm.MitarbeiterID = m.ID
        LEFT JOIN Taetigkeit ta ON bm.TaetigkeitID = ta.ID
        WHERE t.Gelöscht = 0
    '''
    params = []
    
    # Sichtbarkeitsfilter: Themen aus sichtbaren Abteilungen ODER selbst erstellte Themen
    if mitarbeiter_id and sichtbare_abteilungen:
        # Prüfe, ob Thema in sichtbaren Abteilungen ist ODER vom Benutzer erstellt wurde
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        query += f''' AND (
            EXISTS (
                SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                WHERE sv.ThemaID = t.ID 
                AND sv.AbteilungID IN ({placeholders})
            )
            OR EXISTS (
                SELECT 1 FROM SchichtbuchBemerkungen b_first
                WHERE b_first.ThemaID = t.ID 
                AND b_first.Gelöscht = 0
                AND b_first.MitarbeiterID = ?
                AND b_first.Datum = (
                    SELECT MIN(b2.Datum) 
                    FROM SchichtbuchBemerkungen b2 
                    WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0
                )
            )
        )'''
        params.extend(sichtbare_abteilungen)
        params.append(mitarbeiter_id)
    elif mitarbeiter_id:
        # Keine sichtbaren Abteilungen, aber selbst erstellte Themen anzeigen
        query += ''' AND EXISTS (
            SELECT 1 FROM SchichtbuchBemerkungen b_first
            WHERE b_first.ThemaID = t.ID 
            AND b_first.Gelöscht = 0
            AND b_first.MitarbeiterID = ?
            AND b_first.Datum = (
                SELECT MIN(b2.Datum) 
                FROM SchichtbuchBemerkungen b2 
                WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0
            )
        )'''
        params.append(mitarbeiter_id)
    else:
        # Standard-Sichtbarkeitsfilter (ohne selbst erstellte Themen)
        query, params = build_sichtbarkeits_filter_query(
            query,
            sichtbare_abteilungen,
            params,
            table_alias='t'
        )
    
    # Filter anwenden
    if bereich_filter:
        query += ' AND b.Bezeichnung = ?'
        params.append(bereich_filter)
    
    if gewerk_filter:
        query += ' AND g.Bezeichnung = ?'
        params.append(gewerk_filter)
    
    if status_filter_list:
        placeholders = ','.join(['?'] * len(status_filter_list))
        query += f' AND s.Bezeichnung IN ({placeholders})'
        params.extend(status_filter_list)
    
    if q_filter:
        query += ' AND EXISTS (SELECT 1 FROM SchichtbuchBemerkungen b2 WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0 AND b2.Bemerkung LIKE ? )'
        params.append(f'%{q_filter}%')
    
    query += ' GROUP BY t.ID'
    
    # ORDER BY
    query += ''' ORDER BY 
                    LetzteBemerkungDatum DESC,
                    LetzteMitarbeiterNachname ASC,
                    LetzteMitarbeiterVorname ASC,
                    Bereich ASC,
                    Gewerk ASC,
                    LetzteTatigkeit ASC,
                    Status ASC'''
    
    # LIMIT und OFFSET
    if limit is not None:
        query += ' LIMIT ?'
        params.append(limit)
        if offset is not None:
            query += ' OFFSET ?'
            params.append(offset)
    
    return query, params


def get_bemerkungen_fuer_themen(thema_ids, conn):
    """
    Lädt Bemerkungen für mehrere Themen in einer Query
    
    Args:
        thema_ids: Liste von Thema-IDs
        conn: Datenbankverbindung
        
    Returns:
        Dictionary mit ThemaID als Key und Liste von Bemerkungen als Value
    """
    if not thema_ids:
        return {}
    
    placeholders = ','.join(['?'] * len(thema_ids))
    bemerkungen = conn.execute(f'''
        SELECT 
            b.ThemaID,
            b.Datum,
            b.Bemerkung,
            m.Vorname,
            m.Nachname,
            t.Bezeichnung AS Taetigkeit
        FROM SchichtbuchBemerkungen b
        JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
        LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
        WHERE b.Gelöscht = 0 AND b.ThemaID IN ({placeholders})
        ORDER BY b.ThemaID DESC, b.Datum DESC
    ''', thema_ids).fetchall()
    
    # Nach Thema gruppieren
    bemerk_dict = {}
    for b in bemerkungen:
        bemerk_dict.setdefault(b['ThemaID'], []).append(b)
    
    return bemerk_dict


def check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
    """
    Prüft ob ein Mitarbeiter Berechtigung hat, ein Thema zu sehen
    
    Args:
        thema_id: ID des Themas
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        
    Returns:
        True wenn berechtigt, False sonst
    """
    # Prüfe zuerst, ob der Benutzer der Ersteller des Themas ist
    ersteller_check = conn.execute('''
        SELECT COUNT(*) as count FROM SchichtbuchBemerkungen
        WHERE ThemaID = ? 
        AND Gelöscht = 0
        AND MitarbeiterID = ?
        AND Datum = (
            SELECT MIN(Datum) 
            FROM SchichtbuchBemerkungen 
            WHERE ThemaID = ? AND Gelöscht = 0
        )
    ''', (thema_id, mitarbeiter_id, thema_id)).fetchone()
    
    if ersteller_check['count'] > 0:
        # Benutzer ist Ersteller - immer berechtigt
        return True
    
    # Prüfe Sichtbarkeit über Abteilungen
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    if not sichtbare_abteilungen:
        return False
    
    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
    berechtigt = conn.execute(f'''
        SELECT COUNT(*) as count FROM SchichtbuchThemaSichtbarkeit
        WHERE ThemaID = ? AND AbteilungID IN ({placeholders})
    ''', [thema_id] + sichtbare_abteilungen).fetchone()
    
    return berechtigt['count'] > 0


def get_thema_detail_data(thema_id, mitarbeiter_id, conn, is_admin=False):
    """
    Lädt alle Daten für die Thema-Detail-Seite
    
    Args:
        thema_id: ID des Themas
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob der Mitarbeiter Admin ist
        
    Returns:
        Dictionary mit allen benötigten Daten:
        - thema: Thema-Informationen
        - sichtbarkeiten: Sichtbare Abteilungen
        - status_liste: Alle Status-Werte
        - taetigkeiten: Alle Tätigkeiten
        - bemerkungen: Bemerkungen zum Thema
        - mitarbeiter: Alle Mitarbeiter
        - thema_lagerbuchungen: Lagerbuchungen für das Thema
        - verfuegbare_ersatzteile: Verfügbare Ersatzteile für den Benutzer
        - kostenstellen: Alle Kostenstellen
    """
    # Thema-Infos
    thema = conn.execute('''
        SELECT 
            t.ID, 
            g.Bezeichnung AS Gewerk,
            b.Bezeichnung AS Bereich,
            s.Bezeichnung AS Status, 
            s.ID AS StatusID,
            s.Farbe AS StatusFarbe,
            a.Bezeichnung AS Abteilung
        FROM SchichtbuchThema t
        JOIN Gewerke g ON t.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Status s ON t.StatusID = s.ID
        LEFT JOIN Abteilung a ON t.ErstellerAbteilungID = a.ID
        WHERE t.ID = ?
    ''', (thema_id,)).fetchone()
    
    # Sichtbare Abteilungen für dieses Thema
    sichtbarkeiten = conn.execute('''
        SELECT a.Bezeichnung, a.ParentAbteilungID
        FROM SchichtbuchThemaSichtbarkeit sv
        JOIN Abteilung a ON sv.AbteilungID = a.ID
        WHERE sv.ThemaID = ?
        ORDER BY a.Sortierung, a.Bezeichnung
    ''', (thema_id,)).fetchall()
    
    # Alle Status-Werte für Dropdown
    status_liste = conn.execute('SELECT * FROM Status ORDER BY Sortierung ASC').fetchall()
    taetigkeiten = conn.execute('SELECT * FROM Taetigkeit ORDER BY Sortierung ASC').fetchall()
    
    # Bemerkungen zu diesem Thema
    bemerkungen = conn.execute('''
        SELECT 
            b.ID AS BemerkungID,
            b.Datum,
            b.MitarbeiterID,
            m.Vorname,
            m.Nachname,
            b.Bemerkung,
            b.TaetigkeitID,
            t.Bezeichnung AS Taetigkeit
        FROM SchichtbuchBemerkungen b
        JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
        LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
        WHERE b.ThemaID = ? AND b.Gelöscht = 0
        ORDER BY b.Datum DESC
    ''', (thema_id,)).fetchall()
    
    # Alle Mitarbeiter
    mitarbeiter = conn.execute('SELECT * FROM Mitarbeiter').fetchall()
    
    # Alle Lagerbuchungen für dieses Thema laden
    thema_lagerbuchungen = conn.execute('''
        SELECT 
            l.ID AS BuchungsID,
            l.ErsatzteilID,
            l.Typ,
            l.Menge,
            l.Grund,
            l.Buchungsdatum,
            l.Bemerkung,
            l.Preis,
            l.Waehrung,
            e.Bestellnummer,
            e.Bezeichnung AS ErsatzteilBezeichnung,
            m.Vorname || ' ' || m.Nachname AS VerwendetVon,
            k.Bezeichnung AS Kostenstelle
        FROM Lagerbuchung l
        JOIN Ersatzteil e ON l.ErsatzteilID = e.ID
        LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
        LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
        WHERE l.ThemaID = ?
        ORDER BY l.Buchungsdatum DESC
    ''', (thema_id,)).fetchall()
    
    # Verfügbare Ersatzteile für den aktuellen Benutzer laden
    verfuegbare_ersatzteile = get_verfuegbare_ersatzteile_fuer_thema(mitarbeiter_id, conn, is_admin=is_admin)
    
    # Kostenstellen für Dropdown
    kostenstellen = conn.execute('SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    
    return {
        'thema': thema,
        'sichtbarkeiten': sichtbarkeiten,
        'status_liste': status_liste,
        'taetigkeiten': taetigkeiten,
        'bemerkungen': bemerkungen,
        'mitarbeiter': mitarbeiter,
        'thema_lagerbuchungen': thema_lagerbuchungen,
        'verfuegbare_ersatzteile': verfuegbare_ersatzteile,
        'kostenstellen': kostenstellen
    }


def get_verfuegbare_ersatzteile_fuer_thema(mitarbeiter_id, conn, is_admin=False):
    """
    Lädt verfügbare Ersatzteile für einen Mitarbeiter (mit Berechtigungsprüfung)
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob der Mitarbeiter Admin ist
        
    Returns:
        Liste von verfügbaren Ersatzteilen
    """
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    verfuegbare_query = '''
        SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.AktuellerBestand, e.Einheit
        FROM Ersatzteil e
        WHERE e.Gelöscht = 0 AND e.Aktiv = 1 AND e.AktuellerBestand > 0
    '''
    verfuegbare_params = []
    
    if not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        verfuegbare_query += f'''
            AND e.ID IN (
                SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                WHERE AbteilungID IN ({placeholders})
            )
        '''
        verfuegbare_params.extend(sichtbare_abteilungen)
    elif not is_admin:
        verfuegbare_query += ' AND 1=0'
    
    verfuegbare_query += ' ORDER BY e.Bezeichnung'
    return conn.execute(verfuegbare_query, verfuegbare_params).fetchall()


def create_thema(gewerk_id, status_id, mitarbeiter_id, taetigkeit_id, bemerkung, 
                 sichtbare_abteilungen, conn):
    """
    Erstellt ein neues Thema mit erster Bemerkung und Sichtbarkeiten
    
    Args:
        gewerk_id: ID des Gewerks
        status_id: ID des Status
        mitarbeiter_id: ID des Mitarbeiters
        taetigkeit_id: ID der Tätigkeit
        bemerkung: Text der ersten Bemerkung
        sichtbare_abteilungen: Liste von Abteilungs-IDs für Sichtbarkeit
        conn: Datenbankverbindung
        
    Returns:
        Tuple (thema_id, thema_dict) mit der ID und den Thema-Daten
    """
    from utils.helpers import row_to_dict
    from utils import get_untergeordnete_abteilungen, erstelle_benachrichtigung_fuer_neues_thema
    import sqlite3
    
    cur = conn.cursor()
    
    # Primärabteilung des Erstellers ermitteln
    mitarbeiter_row = conn.execute(
        'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
        (mitarbeiter_id,)
    ).fetchone()
    mitarbeiter = row_to_dict(mitarbeiter_row)
    
    ersteller_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None

    # Thema mit Abteilung anlegen
    cur.execute(
        'INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID) VALUES (?, ?, ?)',
        (gewerk_id, status_id, ersteller_abteilung_id)
    )
    thema_id = cur.lastrowid

    # Erste Bemerkung hinzufügen
    cur.execute('''
        INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung)
        VALUES (?, ?, datetime('now', 'localtime'), ?, ?)
    ''', (thema_id, mitarbeiter_id, taetigkeit_id, bemerkung))
    
    # Sichtbarkeiten speichern
    # Alle Abteilungs-IDs sammeln (inkl. Unterabteilungen und Duplikate vermeiden)
    alle_sichtbarkeits_ids = set()
    
    if sichtbare_abteilungen:
        for abt_id in sichtbare_abteilungen:
            abt_id_int = int(abt_id)
            alle_sichtbarkeits_ids.add(abt_id_int)
            # Unterabteilungen auch hinzufügen
            unterabteilungen = get_untergeordnete_abteilungen(abt_id_int, conn)
            alle_sichtbarkeits_ids.update(unterabteilungen)
    else:
        # Fallback: Wenn nichts ausgewählt, nur Ersteller-Abteilung
        if ersteller_abteilung_id:
            alle_sichtbarkeits_ids.add(ersteller_abteilung_id)
            unterabteilungen = get_untergeordnete_abteilungen(ersteller_abteilung_id, conn)
            alle_sichtbarkeits_ids.update(unterabteilungen)
    
    # Benachrichtigungen für Mitarbeiter in sichtbaren Abteilungen erstellen
    import logging
    logger = logging.getLogger(__name__)
    try:
        if alle_sichtbarkeits_ids:
            erstelle_benachrichtigung_fuer_neues_thema(thema_id, list(alle_sichtbarkeits_ids), conn)
    except Exception as e:
        logger.error(f"Fehler beim Erstellen von Benachrichtigungen für neues Thema: ThemaID={thema_id}, SichtbareAbteilungen={alle_sichtbarkeits_ids}, Fehler={str(e)}", exc_info=True)
    
    # Sichtbarkeiten einfügen (INSERT OR IGNORE verhindert Duplikate)
    for abt_id in alle_sichtbarkeits_ids:
        try:
            cur.execute('''
                INSERT OR IGNORE INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
                VALUES (?, ?)
            ''', (thema_id, abt_id))
        except sqlite3.IntegrityError:
            # Duplikat ignorieren
            pass

    # Thema-Daten für Rückgabe abrufen
    taetigkeit_row = conn.execute(
        "SELECT Bezeichnung FROM Taetigkeit WHERE ID = ?",
        (taetigkeit_id,)
    ).fetchone()
    taetigkeit_name = taetigkeit_row["Bezeichnung"] if taetigkeit_row else None

    thema = conn.execute('''
        SELECT 
            t.ID, 
            b.Bezeichnung AS Bereich,
            g.Bezeichnung AS Gewerk,
            s.Bezeichnung AS Status,
            ? AS LetzteBemerkung,
            datetime('now', 'localtime') AS LetzteBemerkungDatum
        FROM SchichtbuchThema t
        JOIN Gewerke g ON t.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Status s ON t.StatusID = s.ID
        WHERE t.ID = ?
    ''', (bemerkung, thema_id)).fetchone()
    
    thema_dict = {
        "ID": thema["ID"],
        "Bereich": thema["Bereich"],
        "Gewerk": thema["Gewerk"],
        "Taetigkeit": taetigkeit_name,
        "Status": thema["Status"],
        "LetzteBemerkung": thema["LetzteBemerkung"],
        "LetzteBemerkungDatum": thema["LetzteBemerkungDatum"]
    }
    
    return thema_id, thema_dict


def process_ersatzteile_fuer_thema(thema_id, ersatzteil_ids, ersatzteil_mengen, 
                                   ersatzteil_bemerkungen, mitarbeiter_id, conn, is_admin=False,
                                   ersatzteil_kostenstellen=None):
    """
    Verarbeitet Ersatzteile bei Thema-Erstellung und erstellt Lagerbuchungen
    
    Args:
        thema_id: ID des Themas
        ersatzteil_ids: Liste von Ersatzteil-IDs
        ersatzteil_mengen: Liste von Mengen
        ersatzteil_bemerkungen: Liste von Bemerkungen
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob der Mitarbeiter Admin ist
        ersatzteil_kostenstellen: Liste von Kostenstellen-IDs (optional)
        
    Returns:
        Anzahl der erfolgreich verarbeiteten Ersatzteile
    """
    from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
    
    if not ersatzteil_ids:
        return 0
    
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    verarbeitet = 0
    
    for i, ersatzteil_id_str in enumerate(ersatzteil_ids):
        if not ersatzteil_id_str or not ersatzteil_id_str.strip():
            continue
        
        try:
            ersatzteil_id = int(ersatzteil_id_str)
            menge = int(ersatzteil_mengen[i]) if i < len(ersatzteil_mengen) and ersatzteil_mengen[i] else 1
            bemerkung = ersatzteil_bemerkungen[i].strip() if i < len(ersatzteil_bemerkungen) and ersatzteil_bemerkungen[i] else None
            kostenstelle_id = int(ersatzteil_kostenstellen[i]) if ersatzteil_kostenstellen and i < len(ersatzteil_kostenstellen) and ersatzteil_kostenstellen[i] and ersatzteil_kostenstellen[i].strip() else None
            
            if menge <= 0:
                continue
            
            # Ersatzteil prüfen
            ersatzteil = conn.execute('''
                SELECT ID, AktuellerBestand, Preis, Waehrung, Bezeichnung
                FROM Ersatzteil
                WHERE ID = ? AND Gelöscht = 0 AND Aktiv = 1
            ''', (ersatzteil_id,)).fetchone()
            
            if not ersatzteil:
                continue
            
            # Berechtigung prüfen (nur für Admins oder wenn Ersatzteil sichtbar ist)
            if not is_admin:
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    zugriff = conn.execute(f'''
                        SELECT 1 FROM ErsatzteilAbteilungZugriff
                        WHERE ErsatzteilID = ? AND AbteilungID IN ({placeholders})
                    ''', [ersatzteil_id] + sichtbare_abteilungen).fetchone()
                    if not zugriff:
                        continue
                else:
                    # Keine Berechtigung
                    continue
            
            # Bestand prüfen
            aktueller_bestand = ersatzteil['AktuellerBestand'] or 0
            if aktueller_bestand < menge:
                print(f"Warnung: Nicht genug Bestand für Ersatzteil {ersatzteil_id}. Verfügbar: {aktueller_bestand}, benötigt: {menge}")
                continue
            
            # Neuer Bestand berechnen
            neuer_bestand = aktueller_bestand - menge
            
            # Preis und Währung
            artikel_preis = ersatzteil['Preis']
            artikel_waehrung = ersatzteil['Waehrung'] or 'EUR'
            
            # Lagerbuchung erstellen (Ausgang)
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID,
                    VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum, KostenstelleID
                ) VALUES (?, 'Ausgang', ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
            ''', (
                ersatzteil_id, 
                menge, 
                f'Verwendung für Thema {thema_id}',
                thema_id,
                mitarbeiter_id,
                bemerkung if bemerkung else None,
                artikel_preis,
                artikel_waehrung,
                kostenstelle_id
            ))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            verarbeitet += 1
            
        except (ValueError, TypeError) as e:
            print(f"Fehler beim Verarbeiten von Ersatzteil {ersatzteil_id_str}: {e}")
            continue
        except Exception as e:
            print(f"Unerwarteter Fehler beim Verarbeiten von Ersatzteil {ersatzteil_id_str}: {e}")
            continue
    
    return verarbeitet


def get_thema_erstellung_form_data(mitarbeiter_id, conn):
    """
    Lädt alle Daten für das Thema-Erstellungs-Formular
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        
    Returns:
        Dictionary mit Formular-Daten:
        - gewerke: Liste von Gewerken
        - taetigkeiten: Liste von Tätigkeiten
        - status: Liste von Status-Werten
        - bereiche: Liste von Bereichen
        - auswaehlbare_abteilungen: Auswählbare Abteilungen
        - primaer_abteilung_id: Primärabteilung des Mitarbeiters
    """
    from utils import get_auswaehlbare_abteilungen_fuer_neues_thema
    from utils.helpers import row_to_dict
    
    gewerke = conn.execute('''
        SELECT G.ID, G.Bezeichnung, B.ID AS BereichID, B.Bezeichnung AS Bereich
        FROM Gewerke G
        JOIN Bereich B ON G.BereichID = B.ID
        WHERE G.Aktiv = 1 AND B.Aktiv = 1
        ORDER BY B.Bezeichnung, G.Bezeichnung
    ''').fetchall()

    taetigkeiten = conn.execute('SELECT * FROM Taetigkeit WHERE Aktiv = 1 ORDER BY Sortierung ASC').fetchall()
    status = conn.execute('SELECT * FROM Status WHERE Aktiv = 1 ORDER BY Sortierung ASC').fetchall()
    bereiche = conn.execute('SELECT * FROM Bereich WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
    
    # Primärabteilung des Mitarbeiters
    mitarbeiter = conn.execute(
        'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
        (mitarbeiter_id,)
    ).fetchone()
    primaer_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
    
    # Auswählbare Abteilungen für Sichtbarkeitssteuerung
    auswaehlbare_abteilungen = get_auswaehlbare_abteilungen_fuer_neues_thema(mitarbeiter_id, conn)
    
    # Kostenstellen für Dropdown
    kostenstellen = conn.execute('SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()

    return {
        'gewerke': gewerke,
        'taetigkeiten': taetigkeiten,
        'status': status,
        'bereiche': bereiche,
        'auswaehlbare_abteilungen': auswaehlbare_abteilungen,
        'primaer_abteilung_id': primaer_abteilung_id,
        'kostenstellen': kostenstellen
    }


def get_thema_sichtbarkeit_data(thema_id, mitarbeiter_id, conn):
    """
    Lädt Sichtbarkeits-Daten für ein Thema im JSON-Format
    
    Args:
        thema_id: ID des Themas
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        
    Returns:
        Dictionary mit Sichtbarkeits-Daten im JSON-Format
    """
    from utils import get_auswaehlbare_abteilungen_fuer_mitarbeiter, get_mitarbeiter_abteilungen, get_untergeordnete_abteilungen
    from utils.helpers import row_to_dict
    
    # Primärabteilung des Mitarbeiters
    mitarbeiter = conn.execute(
        'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
        (mitarbeiter_id,)
    ).fetchone()
    primaer_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
    
    # Auswählbare Abteilungen (eigene + untergeordnete)
    auswaehlbare = get_auswaehlbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    eigene_abteilungen_ids = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    
    # Aktuell ausgewählte Sichtbarkeiten mit Details
    aktuelle = conn.execute('''
        SELECT sv.AbteilungID, a.Bezeichnung, a.ParentAbteilungID, a.Sortierung
        FROM SchichtbuchThemaSichtbarkeit sv
        JOIN Abteilung a ON sv.AbteilungID = a.ID
        WHERE sv.ThemaID = ?
        ORDER BY a.Sortierung, a.Bezeichnung
    ''', (thema_id,)).fetchall()
    aktuelle_ids = [a['AbteilungID'] for a in aktuelle]
    
    # Alle eigenen Abteilungen mit allen Unterabteilungen (für Vergleich)
    alle_eigene_mit_unter = set()
    for abt_id in eigene_abteilungen_ids:
        alle_eigene_mit_unter.update(get_untergeordnete_abteilungen(abt_id, conn))
    
    # Alle aktuell zugewiesenen Abteilungen, die NICHT in den eigenen (inkl. Unterabteilungen) sind
    zusaetzliche_aktuelle = []
    for akt in aktuelle:
        if akt['AbteilungID'] not in alle_eigene_mit_unter:
            # Parent-Abteilung finden (falls vorhanden)
            parent_info = None
            if akt['ParentAbteilungID']:
                parent = conn.execute(
                    'SELECT ID, Bezeichnung FROM Abteilung WHERE ID = ?',
                    (akt['ParentAbteilungID'],)
                ).fetchone()
                if parent:
                    parent_info = {'id': parent['ID'], 'name': parent['Bezeichnung']}
            
            zusaetzliche_aktuelle.append({
                'id': akt['AbteilungID'],
                'name': akt['Bezeichnung'],
                'parent': parent_info,
                'is_own': False
            })
    
    # In JSON-Format umwandeln
    auswaehlbare_json = []
    for gruppe in auswaehlbare:
        children_json = []
        for c in gruppe['children']:
            is_current = c['ID'] in aktuelle_ids
            children_json.append({
                'id': c['ID'], 
                'name': c['Bezeichnung'],
                'is_current': is_current
            })
        
        is_current_parent = gruppe['parent']['ID'] in aktuelle_ids
        auswaehlbare_json.append({
            'parent': {
                'id': gruppe['parent']['ID'],
                'name': gruppe['parent']['Bezeichnung'],
                'is_primaer': gruppe['parent']['ID'] == primaer_abteilung_id,
                'is_current': is_current_parent
            },
            'children': children_json
        })
    
    return {
        'success': True,
        'thema_id': thema_id,
        'auswaehlbare': auswaehlbare_json,
        'zusaetzliche': zusaetzliche_aktuelle,
        'aktuelle': aktuelle_ids
    }


def update_thema_sichtbarkeiten(thema_id, sichtbare_abteilungen, conn):
    """
    Aktualisiert die Sichtbarkeiten eines Themas
    
    Args:
        thema_id: ID des Themas
        sichtbare_abteilungen: Liste von Abteilungs-IDs
        conn: Datenbankverbindung
        
    Returns:
        Tuple (success: bool, message: str)
    """
    import sqlite3
    
    if not sichtbare_abteilungen:
        return False, 'Mindestens eine Abteilung muss ausgewählt sein.'
    
    try:
        # Alte Sichtbarkeiten löschen
        conn.execute('DELETE FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?', (thema_id,))
        
        # Neue Sichtbarkeiten einfügen
        for abt_id in sichtbare_abteilungen:
            try:
                conn.execute('''
                    INSERT INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
                    VALUES (?, ?)
                ''', (thema_id, abt_id))
            except sqlite3.IntegrityError:
                pass  # Duplikat ignorieren
        
        conn.commit()
        return True, 'Sichtbarkeit erfolgreich aktualisiert.'
    except Exception as e:
        return False, f'Fehler: {str(e)}'


def check_thema_datei_berechtigung(thema_id, mitarbeiter_id, conn):
    """
    Prüft ob ein Mitarbeiter Berechtigung hat, auf Dateien eines Themas zuzugreifen
    
    Args:
        thema_id: ID des Themas
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        
    Returns:
        Tuple (berechtigt: bool, thema_exists: bool)
    """
    # Prüfen ob Thema existiert
    thema = conn.execute('''
        SELECT t.ID, t.ErstellerAbteilungID
        FROM SchichtbuchThema t
        WHERE t.ID = ? AND t.Gelöscht = 0
    ''', (thema_id,)).fetchone()
    
    if not thema:
        return False, False
    
    # Prüfen ob Thema für Benutzer sichtbar ist
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    if not sichtbare_abteilungen:
        return False, True
    
    thema_sichtbarkeiten = conn.execute('''
        SELECT AbteilungID FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?
    ''', (thema_id,)).fetchall()
    
    thema_abteilungen = [s['AbteilungID'] for s in thema_sichtbarkeiten]
    
    if not any(abt in sichtbare_abteilungen for abt in thema_abteilungen):
        return False, True
    
    return True, True


def get_thema_dateien_liste(thema_id, upload_folder):
    """
    Erstellt eine Liste aller Dateien für ein Thema
    
    Args:
        thema_id: ID des Themas
        upload_folder: Upload-Ordner-Pfad
        
    Returns:
        Liste von Datei-Dictionaries mit name, size, type, ext (ohne url, wird in Route hinzugefügt)
    """
    import os
    
    thema_folder = os.path.join(upload_folder, str(thema_id))
    
    dateien = []
    if os.path.exists(thema_folder):
        for filename in os.listdir(thema_folder):
            filepath = os.path.join(thema_folder, filename)
            if os.path.isfile(filepath):
                # Dateigröße ermitteln
                file_size = os.path.getsize(filepath)
                file_size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
                
                # Dateiendung ermitteln
                file_ext = os.path.splitext(filename)[1].lower()
                
                # Dateityp kategorisieren
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    file_type = 'image'
                elif file_ext == '.pdf':
                    file_type = 'pdf'
                else:
                    file_type = 'document'
                
                dateien.append({
                    'name': filename,
                    'size': file_size_str,
                    'type': file_type,
                    'ext': file_ext
                })
    
    return dateien