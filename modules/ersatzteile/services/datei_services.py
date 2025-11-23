"""
Datei-Services - Einheitliche Dateiverwaltung für alle Bereiche
"""

from datetime import datetime
import os


def get_dateien_fuer_bereich(bereich_typ, bereich_id, conn):
    """
    Lädt alle Dateien für einen bestimmten Bereich
    
    Args:
        bereich_typ: 'Ersatzteil', 'Bestellung', 'Thema', etc.
        bereich_id: ID des Bereichs
        conn: Datenbankverbindung
    
    Returns:
        Liste von Datei-Datensätzen
    """
    dateien = conn.execute('''
        SELECT 
            d.ID,
            d.BereichTyp,
            d.BereichID,
            d.Dateiname,
            d.Dateipfad,
            d.Beschreibung,
            d.Typ,
            d.ErstelltAm,
            d.ErstelltVonID,
            m.Vorname || ' ' || m.Nachname AS ErstelltVon
        FROM Datei d
        LEFT JOIN Mitarbeiter m ON d.ErstelltVonID = m.ID
        WHERE d.BereichTyp = ? AND d.BereichID = ?
        ORDER BY d.ErstelltAm DESC
    ''', (bereich_typ, bereich_id)).fetchall()
    
    return dateien


def speichere_datei(bereich_typ, bereich_id, dateiname, dateipfad, beschreibung, typ, mitarbeiter_id, conn):
    """
    Speichert eine Datei in der Datenbank
    
    Args:
        bereich_typ: 'Ersatzteil', 'Bestellung', 'Thema', etc.
        bereich_id: ID des Bereichs
        dateiname: Originaler Dateiname
        dateipfad: Relativer Pfad zur Datei
        beschreibung: Optional Beschreibung
        typ: Optional Typ ('Bild', 'Dokument', 'PDF', etc.)
        mitarbeiter_id: ID des Mitarbeiters, der die Datei hochgeladen hat
        conn: Datenbankverbindung
    
    Returns:
        ID der erstellten Datei
    """
    cursor = conn.execute('''
        INSERT INTO Datei (BereichTyp, BereichID, Dateiname, Dateipfad, Beschreibung, Typ, ErstelltVonID)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (bereich_typ, bereich_id, dateiname, dateipfad, beschreibung or '', typ or None, mitarbeiter_id))
    
    return cursor.lastrowid


def loesche_datei(datei_id, conn):
    """
    Löscht eine Datei aus der Datenbank
    
    Args:
        datei_id: ID der Datei
        conn: Datenbankverbindung
    
    Returns:
        Tuple (erfolg, dateipfad) - dateipfad für physisches Löschen der Datei
    """
    datei = conn.execute('SELECT Dateipfad FROM Datei WHERE ID = ?', (datei_id,)).fetchone()
    
    if not datei:
        return False, None
    
    conn.execute('DELETE FROM Datei WHERE ID = ?', (datei_id,))
    
    return True, datei['Dateipfad']


def importiere_datei_aus_ordner(bereich_typ, bereich_id, dateiname, ziel_ordner, beschreibung, mitarbeiter_id, conn, upload_base_folder):
    """
    Importiert eine Datei aus dem Import-Ordner und erstellt einen Datenbankeintrag
    
    Args:
        bereich_typ: 'Ersatzteil', 'Bestellung', 'Thema', etc.
        bereich_id: ID des Bereichs
        dateiname: Name der Datei im Import-Ordner
        ziel_ordner: Relativer Zielordner (z.B. 'Ersatzteile/123/bilder')
        beschreibung: Optional Beschreibung
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        upload_base_folder: Basis-Upload-Ordner
    
    Returns:
        Tuple (erfolg, dateipfad, fehlermeldung)
    """
    import_folder = os.path.join(upload_base_folder, 'Import')
    ziel_pfad = os.path.join(upload_base_folder, ziel_ordner)
    
    # Quell- und Zieldateipfade
    quelle = os.path.join(import_folder, dateiname)
    ziel = os.path.join(ziel_pfad, dateiname)
    
    # Prüfen ob Datei existiert
    if not os.path.exists(quelle):
        return False, None, f"Datei '{dateiname}' nicht im Import-Ordner gefunden"
    
    # Zielordner erstellen
    os.makedirs(ziel_pfad, exist_ok=True)
    
    # Datei verschieben
    try:
        import shutil
        shutil.move(quelle, ziel)
    except Exception as e:
        return False, None, f"Fehler beim Verschieben der Datei: {str(e)}"
    
    # Dateityp ermitteln
    datei_ext = os.path.splitext(dateiname)[1].lower()
    typ = None
    if datei_ext in ['.jpg', '.jpeg', '.png', '.gif']:
        typ = 'Bild'
    elif datei_ext == '.pdf':
        typ = 'PDF'
    elif datei_ext in ['.doc', '.docx']:
        typ = 'Dokument'
    elif datei_ext in ['.xls', '.xlsx']:
        typ = 'Excel'
    else:
        typ = 'Dokument'
    
    # Relativer Pfad für Datenbank (mit Forward-Slashes)
    relativer_pfad = ziel_ordner.replace('\\', '/') + '/' + dateiname
    
    # Datenbankeintrag erstellen
    try:
        datei_id = speichere_datei(
            bereich_typ=bereich_typ,
            bereich_id=bereich_id,
            dateiname=dateiname,
            dateipfad=relativer_pfad,
            beschreibung=beschreibung or '',
            typ=typ,
            mitarbeiter_id=mitarbeiter_id,
            conn=conn
        )
        return True, relativer_pfad, None
    except Exception as e:
        # Datei wieder zurückverschieben bei Fehler
        try:
            shutil.move(ziel, quelle)
        except:
            pass
        return False, None, f"Fehler beim Erstellen des Datenbankeintrags: {str(e)}"


def get_datei_typ_aus_dateiname(dateiname):
    """
    Ermittelt den Dateityp basierend auf der Dateiendung
    
    Args:
        dateiname: Name der Datei
    
    Returns:
        Typ-String ('Bild', 'PDF', 'Dokument', etc.)
    """
    datei_ext = os.path.splitext(dateiname)[1].lower()
    
    if datei_ext in ['.jpg', '.jpeg', '.png', '.gif']:
        return 'Bild'
    elif datei_ext == '.pdf':
        return 'PDF'
    elif datei_ext in ['.doc', '.docx']:
        return 'Dokument'
    elif datei_ext in ['.xls', '.xlsx']:
        return 'Excel'
    elif datei_ext in ['.txt']:
        return 'Text'
    else:
        return 'Dokument'

