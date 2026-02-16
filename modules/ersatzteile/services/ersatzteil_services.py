"""
Ersatzteil Services
Business-Logik für Ersatzteil-Funktionen
"""

import re
from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_ersatzteil_zugriff_filter
from utils.zebra_client import send_zpl_to_printer


def build_ersatzteil_liste_query(
    mitarbeiter_id,
    sichtbare_abteilungen,
    is_admin,
    kategorie_filter=None,
    lieferant_filter=None,
    lagerort_filter=None,
    lagerplatz_filter=None,
    kennzeichen_filter=None,
    bestandswarnung=False,
    q_filter=None,
    sort_by='kategorie',
    sort_dir='asc',
    nur_ohne_preis=False,
    limit=None,
    offset=None,
):
    """
    Baut die SQL-Query für Ersatzteil-Liste auf
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        is_admin: Ob der Mitarbeiter Admin ist
        kategorie_filter: Optionaler Kategorie-Filter
        lieferant_filter: Optionaler Lieferanten-Filter
        lagerort_filter: Optionaler Lagerort-Filter
        lagerplatz_filter: Optionaler Lagerplatz-Filter
        kennzeichen_filter: Optionaler Kennzeichen-Filter
        bestandswarnung: Ob nur Bestandswarnungen angezeigt werden sollen
        q_filter: Optionaler Such-Filter
        sort_by: Sortierspalte
        sort_dir: Sortierrichtung ('asc' oder 'desc')
        limit: Optionales Limit
        offset: Optionales Offset
        
    Returns:
        Tuple (query, params)
    """
    # Basis-Query
    # Anzahl sichtbarer Abteilungen für Admins hinzufügen
    abteilungen_count_select = ''
    if is_admin:
        abteilungen_count_select = ', (SELECT COUNT(*) FROM ErsatzteilAbteilungZugriff WHERE ErsatzteilID = e.ID) AS AbteilungenAnzahl'
    
    query = f'''
        SELECT 
            e.ID,
            e.Bestellnummer,
            e.Bezeichnung,
            e.Hersteller,
            e.AktuellerBestand,
            e.Mindestbestand,
            e.Einheit,
            e.EndOfLife,
            e.Kennzeichen,
            e.LieferantID,
            e.Preis,
            e.Waehrung,
            e.ArtikelfotoPfad,
            k.Bezeichnung AS Kategorie,
            l.Name AS Lieferant,
            lo.Bezeichnung AS LagerortName,
            lp.Bezeichnung AS LagerplatzName,
            e.Aktiv,
            e.Gelöscht
            {abteilungen_count_select}
        FROM Ersatzteil e
        LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
        LEFT JOIN Lieferant l ON e.LieferantID = l.ID
        LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
        LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
        WHERE e.Gelöscht = 0
    '''
    params = []
    
    # Berechtigungsfilter
    query, params = build_ersatzteil_zugriff_filter(
        query,
        mitarbeiter_id,
        sichtbare_abteilungen,
        is_admin,
        params
    )
    
    # Filter anwenden
    if kategorie_filter:
        query += ' AND e.KategorieID = ?'
        params.append(kategorie_filter)
    
    if lieferant_filter:
        query += ' AND e.LieferantID = ?'
        params.append(lieferant_filter)
    
    if bestandswarnung:
        query += ' AND e.AktuellerBestand < e.Mindestbestand AND e.Mindestbestand > 0 AND e.EndOfLife = 0'

    if nur_ohne_preis:
        # Nur Artikel ohne Preis (NULL oder 0)
        query += ' AND (e.Preis IS NULL OR e.Preis = 0)'
    
    if q_filter:
        query += ' AND (CAST(e.ID AS TEXT) LIKE ? OR e.Bestellnummer LIKE ? OR e.Bezeichnung LIKE ? OR e.Beschreibung LIKE ? OR e.ArtikelnummerHersteller LIKE ?)'
        search_term = f'%{q_filter}%'
        params.extend([search_term, search_term, search_term, search_term, search_term])
    
    if lagerort_filter:
        query += ' AND e.LagerortID = ?'
        params.append(lagerort_filter)
    
    if lagerplatz_filter:
        query += ' AND e.LagerplatzID = ?'
        params.append(lagerplatz_filter)
    
    if kennzeichen_filter:
        query += ' AND e.Kennzeichen = ?'
        params.append(kennzeichen_filter)
    
    # Sortierung
    sort_mapping = {
        'id': 'e.ID',
        'artikelnummer': 'e.Bestellnummer',
        'kategorie': 'k.Bezeichnung',
        'bezeichnung': 'e.Bezeichnung',
        'lieferant': 'l.Name',
        'bestand': 'e.AktuellerBestand',
        'preis': 'e.Preis',
        'lagerort': 'lo.Bezeichnung',
        'lagerplatz': 'lp.Bezeichnung'
    }
    
    sort_column = sort_mapping.get(sort_by, 'k.Bezeichnung')
    sort_direction = 'DESC' if sort_dir == 'desc' else 'ASC'
    
    # Sekundäre Sortierung nach Bezeichnung, wenn nicht bereits danach sortiert wird
    if sort_by != 'bezeichnung':
        query += f' ORDER BY {sort_column} {sort_direction}, e.Bezeichnung ASC'
    else:
        query += f' ORDER BY {sort_column} {sort_direction}'
    
    # LIMIT und OFFSET
    if limit is not None:
        query += ' LIMIT ?'
        params.append(limit)
        if offset is not None:
            query += ' OFFSET ?'
            params.append(offset)
    
    return query, params


def get_ersatzteil_liste_filter_options(conn):
    """
    Lädt alle Filter-Optionen für die Ersatzteil-Liste
    
    Args:
        conn: Datenbankverbindung
        
    Returns:
        Dictionary mit Filter-Optionen:
        - kategorien: Liste von Kategorien
        - lieferanten: Liste von Lieferanten
        - lagerorte: Liste von Lagerorten
        - lagerplaetze: Liste von Lagerplätzen
        - kennzeichen_liste: Liste von Kennzeichen
    """
    kategorien = conn.execute('SELECT ID, Bezeichnung FROM ErsatzteilKategorie WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
    lagerorte = conn.execute('SELECT ID, Bezeichnung FROM Lagerort WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    lagerplaetze = conn.execute('SELECT ID, Bezeichnung FROM Lagerplatz WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    # Eindeutige Kennzeichen-Werte laden (nur nicht-leere Werte)
    kennzeichen_liste = conn.execute('SELECT DISTINCT Kennzeichen FROM Ersatzteil WHERE Kennzeichen IS NOT NULL AND Kennzeichen != "" AND Gelöscht = 0 ORDER BY Kennzeichen').fetchall()
    
    return {
        'kategorien': kategorien,
        'lieferanten': lieferanten,
        'lagerorte': lagerorte,
        'lagerplaetze': lagerplaetze,
        'kennzeichen_liste': kennzeichen_liste
    }


def get_ersatzteil_detail_data(ersatzteil_id, mitarbeiter_id, conn, upload_folder):
    """
    Lädt alle Daten für die Ersatzteil-Detail-Seite
    
    Args:
        ersatzteil_id: ID des Ersatzteils
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        upload_folder: Upload-Ordner-Pfad
        
    Returns:
        Dictionary mit allen benötigten Daten:
        - ersatzteil: Ersatzteil-Informationen
        - bilder: Liste von Bildern
        - dokumente: Liste von Dokumenten
        - lagerbuchungen: Liste von Lagerbuchungen
        - verknuepfungen: Liste von Thema-Verknüpfungen
        - zugriffe: Liste von Abteilungszugriffen
        - kostenstellen: Liste von Kostenstellen
    """
    import os
    
    # Ersatzteil laden
    ersatzteil = conn.execute('''
        SELECT 
            e.*,
            k.Bezeichnung AS Kategorie,
            l.Name AS Lieferant,
            l.Kontaktperson AS LieferantKontakt,
            l.Telefon AS LieferantTelefon,
            l.Email AS LieferantEmail,
            lo.Bezeichnung AS LagerortName,
            lp.Bezeichnung AS LagerplatzName,
            m.Vorname || ' ' || m.Nachname AS ErstelltVon,
            n.Bestellnummer AS NachfolgeartikelNummer,
            n.Bezeichnung AS NachfolgeartikelBezeichnung
        FROM Ersatzteil e
        LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
        LEFT JOIN Lieferant l ON e.LieferantID = l.ID
        LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
        LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
        LEFT JOIN Mitarbeiter m ON e.ErstelltVonID = m.ID
        LEFT JOIN Ersatzteil n ON e.NachfolgeartikelID = n.ID
        WHERE e.ID = ? AND e.Gelöscht = 0
    ''', (ersatzteil_id,)).fetchone()
    
    if not ersatzteil:
        return None
    
    # Bilder laden
    bilder = conn.execute('''
        SELECT ID, Dateiname, Dateipfad FROM ErsatzteilBild
        WHERE ErsatzteilID = ?
        ORDER BY ErstelltAm DESC
    ''', (ersatzteil_id,)).fetchall()
    
    # Dokumente laden
    dokumente = conn.execute('''
        SELECT ID, Dateiname, Dateipfad, Typ FROM ErsatzteilDokument
        WHERE ErsatzteilID = ?
        ORDER BY ErstelltAm DESC
    ''', (ersatzteil_id,)).fetchall()
    
    # Dateien aus dem Dateisystem scannen, falls Dateien vorhanden sind, aber nicht in DB
    dokumente_list = list(dokumente)
    dokumente_db_pfade = {d['Dateipfad'].replace('\\', '/') for d in dokumente_list}
    
    # Dateisystem-Ordner prüfen
    dokumente_ordner = os.path.join(upload_folder, str(ersatzteil_id), 'dokumente')
    if os.path.exists(dokumente_ordner):
        for filename in os.listdir(dokumente_ordner):
            file_path = os.path.join(dokumente_ordner, filename)
            if os.path.isfile(file_path):
                relative_path = f'Ersatzteile/{ersatzteil_id}/dokumente/{filename}'
                if relative_path not in dokumente_db_pfade:
                    # Datei ist im Dateisystem, aber nicht in DB - hinzufügen
                    # Versuche Timestamp aus Dateiname zu entfernen (Format: YYYYMMDD_HHMMSS_originalname)
                    display_name = filename
                    if '_' in filename and len(filename.split('_')) >= 3:
                        # Versuche Timestamp-Präfix zu entfernen
                        parts = filename.split('_', 2)
                        if len(parts[0]) == 8 and len(parts[1]) == 6:  # YYYYMMDD_HHMMSS
                            display_name = parts[2]
                    dokumente_list.append({
                        'ID': None,
                        'Dateiname': display_name,
                        'Dateipfad': relative_path,
                        'Typ': None
                    })
    
    dokumente = dokumente_list
    
    # Lagerbuchungen laden
    lagerbuchungen = conn.execute('''
        SELECT 
            l.ID,
            l.Typ,
            l.Menge,
            l.Grund,
            l.Buchungsdatum,
            l.Bemerkung,
            l.Preis,
            l.Waehrung,
            l.BestellungID,
            m.Vorname || ' ' || m.Nachname AS VerwendetVon,
            k.Bezeichnung AS Kostenstelle,
            t.ID AS ThemaID
        FROM Lagerbuchung l
        LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
        LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
        LEFT JOIN SchichtbuchThema t ON l.ThemaID = t.ID
        WHERE l.ErsatzteilID = ?
        ORDER BY l.Buchungsdatum DESC
        LIMIT 50
    ''', (ersatzteil_id,)).fetchall()
    
    # Thema-Verknüpfungen laden (aus Lagerbuchungen)
    verknuepfungen = conn.execute('''
        SELECT 
            l.ID,
            l.Menge,
            l.Buchungsdatum AS VerwendetAm,
            l.Bemerkung,
            l.ThemaID,
            l.Typ,
            m.Vorname || ' ' || m.Nachname AS VerwendetVon
        FROM Lagerbuchung l
        JOIN SchichtbuchThema t ON l.ThemaID = t.ID
        LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
        WHERE l.ErsatzteilID = ? AND l.ThemaID IS NOT NULL
        ORDER BY l.Buchungsdatum DESC
    ''', (ersatzteil_id,)).fetchall()
    
    # Abteilungszugriffe laden
    zugriffe = conn.execute('''
        SELECT a.ID, a.Bezeichnung
        FROM ErsatzteilAbteilungZugriff ez
        JOIN Abteilung a ON ez.AbteilungID = a.ID
        WHERE ez.ErsatzteilID = ?
        ORDER BY a.Bezeichnung
    ''', (ersatzteil_id,)).fetchall()
    
    # Kostenstellen für Dropdown
    kostenstellen = conn.execute('SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    
    return {
        'ersatzteil': ersatzteil,
        'bilder': bilder,
        'dokumente': dokumente,
        'lagerbuchungen': lagerbuchungen,
        'verknuepfungen': verknuepfungen,
        'zugriffe': zugriffe,
        'kostenstellen': kostenstellen
    }


def drucke_ersatzteil_etikett_intern(ersatzteil_id, anzahl, conn, mitarbeiter_id=None):
    """
    Wiederverwendbare Funktion zum Drucken von Ersatzteil-Etiketten.
    
    :param ersatzteil_id: ID des Ersatzteils
    :param anzahl: Anzahl der zu druckenden Etiketten
    :param conn: Datenbankverbindung
    :param mitarbeiter_id: Optional: Mitarbeiter-ID für Berechtigungsprüfung (wird aktuell nicht verwendet)
    :return: (success: bool, message: str)
    """
    # Ersatzteil-Daten laden
    et = conn.execute('''
        SELECT e.ID, e.Bezeichnung, e.Bestellnummer, lo.Bezeichnung AS LagerortName, lp.Bezeichnung AS LagerplatzName
        FROM Ersatzteil e
        LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
        LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
        WHERE e.ID = ? AND e.Gelöscht = 0
    ''', (ersatzteil_id,)).fetchone()
    
    if not et:
        return False, f'Ersatzteil {ersatzteil_id} nicht gefunden.'
    
    # Etikett "ErsatzteilLabel" aus der DB laden
    etikett = conn.execute('''
        SELECT e.*, p.ip_address, lf.zpl_header
        FROM Etikett e
        JOIN zebra_printers p ON e.drucker_id = p.id
        JOIN label_formats lf ON e.etikettformat_id = lf.id
        WHERE e.bezeichnung = ? AND p.active = 1
        LIMIT 1
    ''', ('ErsatzteilLabel',)).fetchone()
    
    if not etikett:
        return False, 'Etikett "ErsatzteilLabel" nicht gefunden oder Drucker nicht aktiv.'
    
    # Daten für Platzhalter vorbereiten
    artnr = str(et['ID'])
    bestellnummer = et['Bestellnummer'] or ''
    bezeichnung = et['Bezeichnung'] or ''
    lagerort = et['LagerortName'] or ''
    lagerplatz = et['LagerplatzName'] or ''
    
    # Bezeichnung auf 3 Zeilen umbrechen
    max_len = 28
    words = (bezeichnung or "").split()
    lines = ["", "", ""]
    current_line = 0
    
    for w in words:
        sep = "" if len(lines[current_line]) == 0 else " "
        if len(lines[current_line]) + len(sep) + len(w) <= max_len:
            lines[current_line] += sep + w
        elif current_line < 2:
            current_line += 1
            lines[current_line] = w
        else:
            break
    
    line1, line2, line3 = lines
    
    # ZPL-Template aus DB laden und Platzhalter ersetzen
    zpl_template = etikett['druckbefehle']
    zpl = zpl_template.format(
        artnr=artnr,
        bestellnummer=bestellnummer,
        line1=line1,
        line2=line2,
        line3=line3,
        lagerort=lagerort,
        lagerplatz=lagerplatz,
        zpl_header=etikett['zpl_header']
    )
    
    # Anzahl im ZPL-Befehl anpassen (^PQ Befehl)
    zpl = re.sub(r'\^PQ(\d+)', f'^PQ{anzahl}', zpl)
    
    # Kompletten ZPL-Befehl in der Konsole ausgeben (für Debugging)
    print("===== ERSATZTEIL LABEL ZPL =====")
    print(zpl)
    print("===== END ERSATZTEIL LABEL ZPL =====")
    
    # An Drucker senden
    try:
        send_zpl_to_printer(etikett['ip_address'], zpl)
        return True, f'{anzahl} Etikett{"en" if anzahl > 1 else ""} für Artikel {artnr} gedruckt.'
    except Exception as e:
        return False, f'Fehler beim Senden an Drucker: {e}'

