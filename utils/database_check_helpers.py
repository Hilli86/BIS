"""
Datenbank-Prüfung und Initialisierung beim App-Start
Prüft beim Start der App die Datenbank-Integrität und initialisiert fehlende Strukturen.
"""

import sqlite3
import os
import sys

try:
    from werkzeug.security import generate_password_hash
except ImportError:
    generate_password_hash = None


def table_exists(conn, table_name):
    """Prüft, ob eine Tabelle existiert"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns


def index_exists(conn, index_name):
    """Prüft, ob ein Index existiert"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cursor.fetchone() is not None


def extract_column_from_index(index_sql):
    """Extrahiert den Spaltennamen aus einem CREATE INDEX Statement"""
    # CREATE INDEX name ON table(column)
    try:
        # Finde die Spalte zwischen den Klammern
        start = index_sql.find('(')
        end = index_sql.find(')')
        if start != -1 and end != -1:
            column_part = index_sql[start+1:end].strip()
            # Prüfe ob es ein zusammengesetzter Index ist (mehrere Spalten)
            if ',' in column_part:
                # Bei zusammengesetzten Indizes geben wir None zurück
                # Die Spaltenprüfung wird übersprungen
                return None
            # Entferne mögliche zusätzliche Teile wie ASC/DESC
            column_name = column_part.split()[0]
            # Entferne Komma am Ende falls vorhanden
            column_name = column_name.rstrip(',')
            return column_name
    except:
        pass
    return None


def create_table_if_not_exists(conn, table_name, create_sql, indices=None):
    """Erstellt eine Tabelle falls sie nicht existiert und erstellt fehlende Indexes"""
    table_created = False
    if not table_exists(conn, table_name):
        conn.execute(create_sql)
        table_created = True
    
    # Erstelle fehlende Indexes (auch wenn Tabelle bereits existiert)
    if indices:
        for index_sql in indices:
            # Extrahiere Index-Name aus CREATE INDEX name ON ...
            parts = index_sql.split()
            if len(parts) >= 3 and parts[0].upper() == 'CREATE' and parts[1].upper() == 'INDEX':
                index_name = parts[2]
                if not index_exists(conn, index_name):
                    # Prüfe ob die Spalte existiert, bevor der Index erstellt wird
                    column_name = extract_column_from_index(index_sql)
                    if column_name is None:
                        # Zusammengesetzter Index - versuche direkt zu erstellen
                        try:
                            conn.execute(index_sql)
                        except sqlite3.OperationalError as e:
                            # Ignoriere Fehler wenn Spalte nicht existiert oder Index bereits existiert
                            print(f"[WARN] Index '{index_name}' konnte nicht erstellt werden: {e}")
                    elif column_exists(conn, table_name, column_name):
                        try:
                            conn.execute(index_sql)
                        except sqlite3.OperationalError as e:
                            # Ignoriere Fehler wenn Spalte nicht existiert oder Index bereits existiert
                            print(f"[WARN] Index '{index_name}' konnte nicht erstellt werden: {e}")
                    else:
                        print(f"[WARN] Spalte '{column_name}' existiert nicht in Tabelle '{table_name}', überspringe Index '{index_name}'")
    
    return table_created


def create_column_if_not_exists(conn, table_name, column_name, alter_sql):
    """Erstellt eine Spalte falls sie nicht existiert"""
    if not column_exists(conn, table_name, column_name):
        try:
            conn.execute(alter_sql)
            return True
        except sqlite3.OperationalError as e:
            # Spalte könnte bereits existieren oder andere Probleme
            # Ignoriere Fehler, da Spalte möglicherweise bereits existiert
            return False
    return False


def create_index_if_not_exists(conn, index_name, create_sql):
    """Erstellt einen Index falls er nicht existiert"""
    if not index_exists(conn, index_name):
        conn.execute(create_sql)
        return True
    return False


def get_required_tables():
    """Gibt eine Liste aller erforderlichen Tabellen zurück"""
    return [
        'Mitarbeiter',
        'Abteilung',
        'MitarbeiterAbteilung',
        'Bereich',
        'Gewerke',
        'Status',
        'Taetigkeit',
        'SchichtbuchThema',
        'SchichtbuchBemerkungen',
        'SchichtbuchThemaSichtbarkeit',
        'Aufgabenliste',
        'AufgabenlisteSichtbarkeitAbteilung',
        'AufgabenlisteSichtbarkeitMitarbeiter',
        'AufgabenlisteThema',
        'Benachrichtigung',
        'BenachrichtigungEinstellung',
        'BenachrichtigungKanal',
        'BenachrichtigungVersand',
        'ErsatzteilKategorie',
        'Kostenstelle',
        'Lieferant',
        'Lagerort',
        'Lagerplatz',
        'Ersatzteil',
        'ErsatzteilBild',
        'ErsatzteilDokument',
        'Lagerbuchung',
        'ErsatzteilAbteilungZugriff',
        'Datei',
        'LoginLog',
        'Firmendaten',
        'Angebotsanfrage',
        'AngebotsanfragePosition',
        'Bestellung',
        'BestellungPosition',
        'BestellungSichtbarkeit',
        'Berechtigung',
        'MitarbeiterBerechtigung',
        'zebra_printers',
        'label_formats',
        'Etikett',
        'WebAuthnCredential',
        'MitarbeiterMenueSichtbarkeit',
        'Wartung',
        'WartungAbteilungZugriff',
        'Fremdfirma',
        'Wartungsplan',
        'Wartungsdurchfuehrung',
        'WartungsdurchfuehrungMitarbeiter',
        'WartungsdurchfuehrungFremdfirma',
    ]


def check_database_integrity(db_path):
    """
    Prüft die Datenbank-Integrität:
    - Existiert die Datenbank?
    - Sind alle erforderlichen Tabellen vorhanden?
    
    Returns:
        tuple: (is_valid, missing_tables, errors)
    """
    errors = []
    missing_tables = []
    
    # Prüfe ob Datenbank existiert
    if not os.path.exists(db_path):
        errors.append(f"Datenbank '{db_path}' existiert nicht!")
        return False, missing_tables, errors
    
    # Prüfe ob Datenbank nicht leer ist
    if os.path.getsize(db_path) == 0:
        errors.append(f"Datenbank '{db_path}' ist leer!")
        return False, missing_tables, errors
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Prüfe alle erforderlichen Tabellen
        required_tables = get_required_tables()
        for table in required_tables:
            if not table_exists(conn, table):
                missing_tables.append(table)
        
        conn.close()
        
        is_valid = len(missing_tables) == 0
        if not is_valid:
            errors.append(f"Fehlende Tabellen: {', '.join(missing_tables)}")
        
        return is_valid, missing_tables, errors
        
    except sqlite3.Error as e:
        errors.append(f"Datenbankfehler: {e}")
        return False, missing_tables, errors
    except Exception as e:
        errors.append(f"Unerwarteter Fehler: {e}")
        return False, missing_tables, errors

