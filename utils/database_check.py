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
            # Entferne mögliche zusätzliche Teile wie ASC/DESC
            column_name = column_part.split()[0]
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
                    if column_name and column_exists(conn, table_name, column_name):
                        try:
                            conn.execute(index_sql)
                        except sqlite3.OperationalError as e:
                            # Ignoriere Fehler wenn Spalte nicht existiert oder Index bereits existiert
                            print(f"[WARN] Index '{index_name}' konnte nicht erstellt werden: {e}")
                    elif column_name:
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
        'Benachrichtigung',
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
        'LoginLog',
        'Firmendaten',
        'Angebotsanfrage',
        'AngebotsanfragePosition',
        'Bestellung',
        'BestellungPosition',
        'BestellungSichtbarkeit'
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


def init_database_schema(db_path, verbose=False):
    """
    Initialisiert die Datenbank mit allen Tabellen, Spalten und Indexes.
    Erstellt nur fehlende Strukturen, ohne bestehende Daten zu löschen.
    """
    # Datenbankverbindung erstellen (wird automatisch erstellt falls nicht vorhanden)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # ========== 1. Mitarbeiter ==========
        created = create_table_if_not_exists(conn, 'Mitarbeiter', '''
            CREATE TABLE Mitarbeiter (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Personalnummer TEXT NOT NULL UNIQUE,
                Vorname TEXT,
                Nachname TEXT NOT NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Passwort TEXT NOT NULL,
                PrimaerAbteilungID INTEGER,
                FOREIGN KEY (PrimaerAbteilungID) REFERENCES Abteilung(ID)
            )
        ''', [
            'CREATE INDEX idx_mitarbeiter_aktiv ON Mitarbeiter(Aktiv)',
            'CREATE INDEX idx_mitarbeiter_personalnummer ON Mitarbeiter(Personalnummer)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten
            create_column_if_not_exists(conn, 'Mitarbeiter', 'PrimaerAbteilungID', 'ALTER TABLE Mitarbeiter ADD COLUMN PrimaerAbteilungID INTEGER')
            create_column_if_not_exists(conn, 'Mitarbeiter', 'Email', 'ALTER TABLE Mitarbeiter ADD COLUMN Email TEXT NULL')
            create_column_if_not_exists(conn, 'Mitarbeiter', 'Handynummer', 'ALTER TABLE Mitarbeiter ADD COLUMN Handynummer TEXT NULL')
        
        # ========== 2. Abteilung ==========
        create_table_if_not_exists(conn, 'Abteilung', '''
            CREATE TABLE Abteilung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                ParentAbteilungID INTEGER NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0,
                FOREIGN KEY (ParentAbteilungID) REFERENCES Abteilung(ID)
            )
        ''', [
            'CREATE INDEX idx_abteilung_parent ON Abteilung(ParentAbteilungID)',
            'CREATE INDEX idx_abteilung_aktiv ON Abteilung(Aktiv)'
        ])
        
        # ========== 3. MitarbeiterAbteilung ==========
        create_table_if_not_exists(conn, 'MitarbeiterAbteilung', '''
            CREATE TABLE MitarbeiterAbteilung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                MitarbeiterID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(MitarbeiterID, AbteilungID)
            )
        ''', [
            'CREATE INDEX idx_mitarbeiter_abteilung_ma ON MitarbeiterAbteilung(MitarbeiterID)',
            'CREATE INDEX idx_mitarbeiter_abteilung_abt ON MitarbeiterAbteilung(AbteilungID)'
        ])
        
        # ========== 4. Bereich ==========
        create_table_if_not_exists(conn, 'Bereich', '''
            CREATE TABLE Bereich (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''', [
            'CREATE INDEX idx_bereich_aktiv ON Bereich(Aktiv)'
        ])
        
        # ========== 5. Gewerke ==========
        create_table_if_not_exists(conn, 'Gewerke', '''
            CREATE TABLE Gewerke (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                BereichID INTEGER NOT NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (BereichID) REFERENCES Bereich(ID)
            )
        ''', [
            'CREATE INDEX idx_gewerke_bereich ON Gewerke(BereichID)',
            'CREATE INDEX idx_gewerke_aktiv ON Gewerke(Aktiv)'
        ])
        
        # ========== 6. Status ==========
        create_table_if_not_exists(conn, 'Status', '''
            CREATE TABLE Status (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Farbe TEXT,
                Sortierung INTEGER DEFAULT 0,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''', [
            'CREATE INDEX idx_status_aktiv ON Status(Aktiv)'
        ])
        
        # ========== 7. Taetigkeit ==========
        create_table_if_not_exists(conn, 'Taetigkeit', '''
            CREATE TABLE Taetigkeit (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Sortierung INTEGER DEFAULT 0,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''', [
            'CREATE INDEX idx_taetigkeit_aktiv ON Taetigkeit(Aktiv)'
        ])
        
        # ========== 8. SchichtbuchThema ==========
        created = create_table_if_not_exists(conn, 'SchichtbuchThema', '''
            CREATE TABLE SchichtbuchThema (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                GewerkID INTEGER NOT NULL,
                StatusID INTEGER NOT NULL,
                ErstellerAbteilungID INTEGER,
                Gelöscht INTEGER NOT NULL DEFAULT 0,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (GewerkID) REFERENCES Gewerke(ID),
                FOREIGN KEY (StatusID) REFERENCES Status(ID),
                FOREIGN KEY (ErstellerAbteilungID) REFERENCES Abteilung(ID)
            )
        ''', [
            'CREATE INDEX idx_thema_gewerk ON SchichtbuchThema(GewerkID)',
            'CREATE INDEX idx_thema_status ON SchichtbuchThema(StatusID)',
            'CREATE INDEX idx_thema_abteilung ON SchichtbuchThema(ErstellerAbteilungID)',
            'CREATE INDEX idx_thema_geloescht ON SchichtbuchThema(Gelöscht)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten
            if create_column_if_not_exists(conn, 'SchichtbuchThema', 'ErstelltAm', 'ALTER TABLE SchichtbuchThema ADD COLUMN ErstelltAm DATETIME'):
                # SQLite unterstützt kein DEFAULT CURRENT_TIMESTAMP beim ALTER TABLE
                # Setze für bestehende Einträge das Datum der ersten Bemerkung oder aktuelles Datum
                conn.execute('''
                    UPDATE SchichtbuchThema 
                    SET ErstelltAm = COALESCE(
                        (SELECT MIN(Datum) FROM SchichtbuchBemerkungen WHERE ThemaID = SchichtbuchThema.ID),
                        datetime('now')
                    )
                    WHERE ErstelltAm IS NULL
                ''')
                print(f"[INFO] Spalte 'ErstelltAm' zu 'SchichtbuchThema' hinzugefügt")
        
        # ========== 9. SchichtbuchBemerkungen ==========
        create_table_if_not_exists(conn, 'SchichtbuchBemerkungen', '''
            CREATE TABLE SchichtbuchBemerkungen (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ThemaID INTEGER NOT NULL,
                MitarbeiterID INTEGER NOT NULL,
                Datum DATETIME DEFAULT CURRENT_TIMESTAMP,
                TaetigkeitID INTEGER,
                Bemerkung TEXT,
                Gelöscht INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
                FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID),
                FOREIGN KEY (TaetigkeitID) REFERENCES Taetigkeit(ID)
            )
        ''', [
            'CREATE INDEX idx_bemerkung_thema ON SchichtbuchBemerkungen(ThemaID)',
            'CREATE INDEX idx_bemerkung_mitarbeiter ON SchichtbuchBemerkungen(MitarbeiterID)',
            'CREATE INDEX idx_bemerkung_geloescht ON SchichtbuchBemerkungen(Gelöscht)'
        ])
        
        # ========== 10. SchichtbuchThemaSichtbarkeit ==========
        created = create_table_if_not_exists(conn, 'SchichtbuchThemaSichtbarkeit', '''
            CREATE TABLE SchichtbuchThemaSichtbarkeit (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ThemaID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(ThemaID, AbteilungID)
            )
        ''', [
            'CREATE INDEX idx_sichtbarkeit_thema ON SchichtbuchThemaSichtbarkeit(ThemaID)',
            'CREATE INDEX idx_sichtbarkeit_abteilung ON SchichtbuchThemaSichtbarkeit(AbteilungID)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten
            if create_column_if_not_exists(conn, 'SchichtbuchThemaSichtbarkeit', 'ErstelltAm', 'ALTER TABLE SchichtbuchThemaSichtbarkeit ADD COLUMN ErstelltAm DATETIME'):
                conn.execute('UPDATE SchichtbuchThemaSichtbarkeit SET ErstelltAm = datetime(\'now\') WHERE ErstelltAm IS NULL')
        
        # ========== 11. Benachrichtigung ==========
        created = create_table_if_not_exists(conn, 'Benachrichtigung', '''
            CREATE TABLE Benachrichtigung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                MitarbeiterID INTEGER NOT NULL,
                ThemaID INTEGER NOT NULL,
                BemerkungID INTEGER NULL,
                Typ TEXT NOT NULL,
                Titel TEXT NOT NULL,
                Nachricht TEXT NOT NULL,
                Gelesen INTEGER NOT NULL DEFAULT 0,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
                FOREIGN KEY (BemerkungID) REFERENCES SchichtbuchBemerkungen(ID) ON DELETE CASCADE
            )
        ''', [
            'CREATE INDEX idx_benachrichtigung_mitarbeiter ON Benachrichtigung(MitarbeiterID)',
            'CREATE INDEX idx_benachrichtigung_thema ON Benachrichtigung(ThemaID)',
            'CREATE INDEX idx_benachrichtigung_gelesen ON Benachrichtigung(Gelesen)',
            'CREATE INDEX idx_benachrichtigung_erstellt ON Benachrichtigung(ErstelltAm)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten
            if create_column_if_not_exists(conn, 'Benachrichtigung', 'ErstelltAm', 'ALTER TABLE Benachrichtigung ADD COLUMN ErstelltAm DATETIME'):
                conn.execute('UPDATE Benachrichtigung SET ErstelltAm = datetime(\'now\') WHERE ErstelltAm IS NULL')
        
        # ========== 12. ErsatzteilKategorie ==========
        create_table_if_not_exists(conn, 'ErsatzteilKategorie', '''
            CREATE TABLE ErsatzteilKategorie (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0
            )
        ''', [
            'CREATE INDEX idx_ersatzteil_kategorie_aktiv ON ErsatzteilKategorie(Aktiv)',
            'CREATE INDEX idx_ersatzteil_kategorie_sortierung ON ErsatzteilKategorie(Sortierung)'
        ])
        
        # ========== 13. Kostenstelle ==========
        create_table_if_not_exists(conn, 'Kostenstelle', '''
            CREATE TABLE Kostenstelle (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0
            )
        ''', [
            'CREATE INDEX idx_kostenstelle_aktiv ON Kostenstelle(Aktiv)',
            'CREATE INDEX idx_kostenstelle_sortierung ON Kostenstelle(Sortierung)'
        ])
        
        # ========== 14. Lieferant ==========
        created = create_table_if_not_exists(conn, 'Lieferant', '''
            CREATE TABLE Lieferant (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                Kontaktperson TEXT,
                Telefon TEXT,
                Email TEXT,
                Strasse TEXT,
                PLZ TEXT,
                Ort TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Gelöscht INTEGER NOT NULL DEFAULT 0
            )
        ''', [
            'CREATE INDEX idx_lieferant_aktiv ON Lieferant(Aktiv)',
            'CREATE INDEX idx_lieferant_geloescht ON Lieferant(Gelöscht)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten (Migration 005)
            create_column_if_not_exists(conn, 'Lieferant', 'Strasse', 'ALTER TABLE Lieferant ADD COLUMN Strasse TEXT')
            create_column_if_not_exists(conn, 'Lieferant', 'PLZ', 'ALTER TABLE Lieferant ADD COLUMN PLZ TEXT')
            create_column_if_not_exists(conn, 'Lieferant', 'Ort', 'ALTER TABLE Lieferant ADD COLUMN Ort TEXT')
        
        # ========== 15. Lagerort ==========
        create_table_if_not_exists(conn, 'Lagerort', '''
            CREATE TABLE Lagerort (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0
            )
        ''', [
            'CREATE INDEX idx_lagerort_aktiv ON Lagerort(Aktiv)',
            'CREATE INDEX idx_lagerort_sortierung ON Lagerort(Sortierung)'
        ])
        
        # ========== 16. Lagerplatz ==========
        create_table_if_not_exists(conn, 'Lagerplatz', '''
            CREATE TABLE Lagerplatz (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0
            )
        ''', [
            'CREATE INDEX idx_lagerplatz_aktiv ON Lagerplatz(Aktiv)',
            'CREATE INDEX idx_lagerplatz_sortierung ON Lagerplatz(Sortierung)'
        ])
        
        # ========== 17. Ersatzteil ==========
        # Migration: Artikelnummer -> Bestellnummer (falls noch nicht durchgeführt)
        if table_exists(conn, 'Ersatzteil'):
            if column_exists(conn, 'Ersatzteil', 'Artikelnummer') and not column_exists(conn, 'Ersatzteil', 'Bestellnummer'):
                print("[INFO] Führe Migration durch: Artikelnummer -> Bestellnummer")
                try:
                    # SQLite unterstützt kein ALTER TABLE RENAME COLUMN direkt
                    # Wir müssen eine neue Tabelle erstellen, Daten kopieren, alte löschen, neue umbenennen
                    
                    # 1. Neue Tabelle mit Bestellnummer erstellen
                    cursor.execute('''
                        CREATE TABLE Ersatzteil_new (
                            ID INTEGER PRIMARY KEY AUTOINCREMENT,
                            Bestellnummer TEXT NOT NULL UNIQUE,
                            Bezeichnung TEXT NOT NULL,
                            Beschreibung TEXT,
                            KategorieID INTEGER,
                            Hersteller TEXT,
                            LieferantID INTEGER,
                            Preis REAL,
                            Waehrung TEXT DEFAULT 'EUR',
                            Lagerort TEXT,
                            LagerortID INTEGER,
                            LagerplatzID INTEGER,
                            Mindestbestand INTEGER DEFAULT 0,
                            AktuellerBestand INTEGER DEFAULT 0,
                            Einheit TEXT DEFAULT 'Stück',
                            EndOfLife INTEGER NOT NULL DEFAULT 0,
                            NachfolgeartikelID INTEGER,
                            Kennzeichen TEXT,
                            ArtikelnummerHersteller TEXT,
                            Aktiv INTEGER NOT NULL DEFAULT 1,
                            Gelöscht INTEGER NOT NULL DEFAULT 0,
                            ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                            ErstelltVonID INTEGER,
                            FOREIGN KEY (KategorieID) REFERENCES ErsatzteilKategorie(ID),
                            FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
                            FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID),
                            FOREIGN KEY (LagerortID) REFERENCES Lagerort(ID),
                            FOREIGN KEY (LagerplatzID) REFERENCES Lagerplatz(ID),
                            FOREIGN KEY (NachfolgeartikelID) REFERENCES Ersatzteil(ID)
                        )
                    ''')
                    
                    # 2. Daten kopieren
                    cursor.execute('''
                        INSERT INTO Ersatzteil_new (
                            ID, Bestellnummer, Bezeichnung, Beschreibung, KategorieID, Hersteller,
                            LieferantID, Preis, Waehrung, Lagerort, LagerortID, LagerplatzID,
                            Mindestbestand, AktuellerBestand, Einheit, EndOfLife, NachfolgeartikelID,
                            Kennzeichen, ArtikelnummerHersteller, Aktiv, Gelöscht, ErstelltAm, ErstelltVonID
                        )
                        SELECT 
                            ID, Artikelnummer, Bezeichnung, Beschreibung, KategorieID, Hersteller,
                            LieferantID, Preis, Waehrung, Lagerort, LagerortID, LagerplatzID,
                            Mindestbestand, AktuellerBestand, Einheit, EndOfLife, NachfolgeartikelID,
                            Kennzeichen, ArtikelnummerHersteller, Aktiv, Gelöscht, ErstelltAm, ErstelltVonID
                        FROM Ersatzteil
                    ''')
                    
                    # 3. Alte Tabelle löschen
                    cursor.execute('DROP TABLE Ersatzteil')
                    
                    # 4. Neue Tabelle umbenennen
                    cursor.execute('ALTER TABLE Ersatzteil_new RENAME TO Ersatzteil')
                    
                    # 5. Alten Index löschen falls vorhanden
                    cursor.execute('DROP INDEX IF EXISTS idx_ersatzteil_artikelnummer')
                    
                    conn.commit()
                    print("[OK] Migration erfolgreich abgeschlossen")
                except Exception as e:
                    conn.rollback()
                    print(f"[FEHLER] Migration fehlgeschlagen: {e}")
                    raise
        
        created = create_table_if_not_exists(conn, 'Ersatzteil', '''
            CREATE TABLE Ersatzteil (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bestellnummer TEXT NOT NULL UNIQUE,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                KategorieID INTEGER,
                Hersteller TEXT,
                LieferantID INTEGER,
                Preis REAL,
                Waehrung TEXT DEFAULT 'EUR',
                Lagerort TEXT,
                LagerortID INTEGER,
                LagerplatzID INTEGER,
                Mindestbestand INTEGER DEFAULT 0,
                AktuellerBestand INTEGER DEFAULT 0,
                Einheit TEXT DEFAULT 'Stück',
                EndOfLife INTEGER NOT NULL DEFAULT 0,
                NachfolgeartikelID INTEGER,
                Kennzeichen TEXT,
                ArtikelnummerHersteller TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Gelöscht INTEGER NOT NULL DEFAULT 0,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                ErstelltVonID INTEGER,
                FOREIGN KEY (KategorieID) REFERENCES ErsatzteilKategorie(ID),
                FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
                FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID),
                FOREIGN KEY (LagerortID) REFERENCES Lagerort(ID),
                FOREIGN KEY (LagerplatzID) REFERENCES Lagerplatz(ID),
                FOREIGN KEY (NachfolgeartikelID) REFERENCES Ersatzteil(ID)
            )
        ''', [
            'CREATE INDEX idx_ersatzteil_bestellnummer ON Ersatzteil(Bestellnummer)',
            'CREATE INDEX idx_ersatzteil_kategorie ON Ersatzteil(KategorieID)',
            'CREATE INDEX idx_ersatzteil_lieferant ON Ersatzteil(LieferantID)',
            'CREATE INDEX idx_ersatzteil_aktiv ON Ersatzteil(Aktiv)',
            'CREATE INDEX idx_ersatzteil_geloescht ON Ersatzteil(Gelöscht)',
            'CREATE INDEX idx_ersatzteil_bestand ON Ersatzteil(AktuellerBestand)',
            'CREATE INDEX idx_ersatzteil_lagerort ON Ersatzteil(LagerortID)',
            'CREATE INDEX idx_ersatzteil_lagerplatz ON Ersatzteil(LagerplatzID)',
            'CREATE INDEX idx_ersatzteil_nachfolgeartikel ON Ersatzteil(NachfolgeartikelID)',
            'CREATE INDEX idx_ersatzteil_kennzeichen ON Ersatzteil(Kennzeichen)',
            'CREATE INDEX idx_ersatzteil_artikelnummer_hersteller ON Ersatzteil(ArtikelnummerHersteller)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten (Migration 006, 007)
            create_column_if_not_exists(conn, 'Ersatzteil', 'LagerortID', 'ALTER TABLE Ersatzteil ADD COLUMN LagerortID INTEGER')
            create_column_if_not_exists(conn, 'Ersatzteil', 'LagerplatzID', 'ALTER TABLE Ersatzteil ADD COLUMN LagerplatzID INTEGER')
            create_column_if_not_exists(conn, 'Ersatzteil', 'EndOfLife', 'ALTER TABLE Ersatzteil ADD COLUMN EndOfLife INTEGER NOT NULL DEFAULT 0')
            create_column_if_not_exists(conn, 'Ersatzteil', 'NachfolgeartikelID', 'ALTER TABLE Ersatzteil ADD COLUMN NachfolgeartikelID INTEGER NULL')
            create_column_if_not_exists(conn, 'Ersatzteil', 'Kennzeichen', 'ALTER TABLE Ersatzteil ADD COLUMN Kennzeichen TEXT NULL')
            create_column_if_not_exists(conn, 'Ersatzteil', 'ArtikelnummerHersteller', 'ALTER TABLE Ersatzteil ADD COLUMN ArtikelnummerHersteller TEXT NULL')
            create_column_if_not_exists(conn, 'Ersatzteil', 'Preisstand', 'ALTER TABLE Ersatzteil ADD COLUMN Preisstand DATETIME NULL')
            # Prüfe auf fehlende Indexes
            create_index_if_not_exists(conn, 'idx_ersatzteil_lagerort', 'CREATE INDEX idx_ersatzteil_lagerort ON Ersatzteil(LagerortID)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_lagerplatz', 'CREATE INDEX idx_ersatzteil_lagerplatz ON Ersatzteil(LagerplatzID)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_nachfolgeartikel', 'CREATE INDEX idx_ersatzteil_nachfolgeartikel ON Ersatzteil(NachfolgeartikelID)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_kennzeichen', 'CREATE INDEX idx_ersatzteil_kennzeichen ON Ersatzteil(Kennzeichen)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_artikelnummer_hersteller', 'CREATE INDEX idx_ersatzteil_artikelnummer_hersteller ON Ersatzteil(ArtikelnummerHersteller)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_bestand', 'CREATE INDEX idx_ersatzteil_bestand ON Ersatzteil(AktuellerBestand)')
        
        # ========== 18. ErsatzteilBild ==========
        create_table_if_not_exists(conn, 'ErsatzteilBild', '''
            CREATE TABLE ErsatzteilBild (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                Dateiname TEXT NOT NULL,
                Dateipfad TEXT NOT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE
            )
        ''', [
            'CREATE INDEX idx_ersatzteil_bild_ersatzteil ON ErsatzteilBild(ErsatzteilID)'
        ])
        
        # ========== 19. ErsatzteilDokument ==========
        create_table_if_not_exists(conn, 'ErsatzteilDokument', '''
            CREATE TABLE ErsatzteilDokument (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                Dateiname TEXT NOT NULL,
                Dateipfad TEXT NOT NULL,
                Typ TEXT,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE
            )
        ''', [
            'CREATE INDEX idx_ersatzteil_dokument_ersatzteil ON ErsatzteilDokument(ErsatzteilID)'
        ])
        
        # ========== 20. Lagerbuchung ==========
        created = create_table_if_not_exists(conn, 'Lagerbuchung', '''
            CREATE TABLE Lagerbuchung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                Typ TEXT NOT NULL,
                Menge INTEGER NOT NULL,
                Grund TEXT,
                ThemaID INTEGER NULL,
                KostenstelleID INTEGER,
                VerwendetVonID INTEGER NOT NULL,
                Buchungsdatum DATETIME DEFAULT CURRENT_TIMESTAMP,
                Bemerkung TEXT,
                Preis REAL NULL,
                Waehrung TEXT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID),
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID),
                FOREIGN KEY (KostenstelleID) REFERENCES Kostenstelle(ID),
                FOREIGN KEY (VerwendetVonID) REFERENCES Mitarbeiter(ID)
            )
        ''', [
            'CREATE INDEX idx_lagerbuchung_ersatzteil ON Lagerbuchung(ErsatzteilID)',
            'CREATE INDEX idx_lagerbuchung_thema ON Lagerbuchung(ThemaID)',
            'CREATE INDEX idx_lagerbuchung_kostenstelle ON Lagerbuchung(KostenstelleID)',
            'CREATE INDEX idx_lagerbuchung_verwendet_von ON Lagerbuchung(VerwendetVonID)',
            'CREATE INDEX idx_lagerbuchung_buchungsdatum ON Lagerbuchung(Buchungsdatum)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten (Migration 009)
            create_column_if_not_exists(conn, 'Lagerbuchung', 'Preis', 'ALTER TABLE Lagerbuchung ADD COLUMN Preis REAL NULL')
            create_column_if_not_exists(conn, 'Lagerbuchung', 'Waehrung', 'ALTER TABLE Lagerbuchung ADD COLUMN Waehrung TEXT NULL')
            # BestellungID für Wareneingang
            if create_column_if_not_exists(conn, 'Lagerbuchung', 'BestellungID', 'ALTER TABLE Lagerbuchung ADD COLUMN BestellungID INTEGER NULL'):
                print("[INFO] Spalte 'BestellungID' zu 'Lagerbuchung' hinzugefügt")
            # Prüfe auf fehlende Indexes
            create_index_if_not_exists(conn, 'idx_lagerbuchung_verwendet_von', 'CREATE INDEX idx_lagerbuchung_verwendet_von ON Lagerbuchung(VerwendetVonID)')
            create_index_if_not_exists(conn, 'idx_lagerbuchung_buchungsdatum', 'CREATE INDEX idx_lagerbuchung_buchungsdatum ON Lagerbuchung(Buchungsdatum)')
            create_index_if_not_exists(conn, 'idx_lagerbuchung_bestellung', 'CREATE INDEX idx_lagerbuchung_bestellung ON Lagerbuchung(BestellungID)')
        
        # ========== 21. ErsatzteilAbteilungZugriff ==========
        create_table_if_not_exists(conn, 'ErsatzteilAbteilungZugriff', '''
            CREATE TABLE ErsatzteilAbteilungZugriff (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(ErsatzteilID, AbteilungID)
            )
        ''', [
            'CREATE INDEX idx_ersatzteil_abteilung_ersatzteil ON ErsatzteilAbteilungZugriff(ErsatzteilID)',
            'CREATE INDEX idx_ersatzteil_abteilung_abteilung ON ErsatzteilAbteilungZugriff(AbteilungID)'
        ])
        
        # ========== 22. LoginLog ==========
        create_table_if_not_exists(conn, 'LoginLog', '''
            CREATE TABLE LoginLog (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Personalnummer TEXT,
                MitarbeiterID INTEGER NULL,
                Erfolgreich INTEGER NOT NULL DEFAULT 1,
                IPAdresse TEXT,
                UserAgent TEXT,
                Fehlermeldung TEXT NULL,
                Zeitpunkt DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID)
            )
        ''', [
            'CREATE INDEX idx_loginlog_mitarbeiter ON LoginLog(MitarbeiterID)',
            'CREATE INDEX idx_loginlog_zeitpunkt ON LoginLog(Zeitpunkt)',
            'CREATE INDEX idx_loginlog_erfolgreich ON LoginLog(Erfolgreich)',
            'CREATE INDEX idx_loginlog_personalnummer ON LoginLog(Personalnummer)'
        ])
        
        # ========== 23. Firmendaten ==========
        create_table_if_not_exists(conn, 'Firmendaten', '''
            CREATE TABLE Firmendaten (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Firmenname TEXT NOT NULL,
                Strasse TEXT NULL,
                PLZ TEXT NULL,
                Ort TEXT NULL,
                LieferStrasse TEXT NULL,
                LieferPLZ TEXT NULL,
                LieferOrt TEXT NULL,
                Telefon TEXT NULL,
                Fax TEXT NULL,
                Email TEXT NULL,
                Website TEXT NULL,
                Steuernummer TEXT NULL,
                UStIdNr TEXT NULL,
                Geschaeftsfuehrer TEXT NULL,
                LogoPfad TEXT NULL,
                BankName TEXT NULL,
                IBAN TEXT NULL,
                BIC TEXT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                GeaendertAm DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Prüfe ob Firmendaten-Eintrag vorhanden ist, wenn nicht, Standard-Eintrag erstellen
        cursor.execute('SELECT COUNT(*) as count FROM Firmendaten')
        if cursor.fetchone()['count'] == 0:
            cursor.execute('INSERT INTO Firmendaten (Firmenname) VALUES (?)', ('Ihre Firma GmbH',))
        
        # Prüfe auf fehlende Lieferanschrift-Spalten
        if not created:
            create_column_if_not_exists(conn, 'Firmendaten', 'LieferStrasse', 'ALTER TABLE Firmendaten ADD COLUMN LieferStrasse TEXT NULL')
            create_column_if_not_exists(conn, 'Firmendaten', 'LieferPLZ', 'ALTER TABLE Firmendaten ADD COLUMN LieferPLZ TEXT NULL')
            create_column_if_not_exists(conn, 'Firmendaten', 'LieferOrt', 'ALTER TABLE Firmendaten ADD COLUMN LieferOrt TEXT NULL')
        
        # ========== 24. Angebotsanfrage ==========
        created = create_table_if_not_exists(conn, 'Angebotsanfrage', '''
            CREATE TABLE Angebotsanfrage (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                LieferantID INTEGER NOT NULL,
                ErstelltVonID INTEGER NOT NULL,
                ErstellerAbteilungID INTEGER NULL,
                Status TEXT NOT NULL DEFAULT 'Offen',
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                VersendetAm DATETIME NULL,
                AngebotErhaltenAm DATETIME NULL,
                Bemerkung TEXT NULL,
                FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
                FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID),
                FOREIGN KEY (ErstellerAbteilungID) REFERENCES Abteilung(ID)
            )
        ''', [
            'CREATE INDEX idx_angebotsanfrage_lieferant ON Angebotsanfrage(LieferantID)',
            'CREATE INDEX idx_angebotsanfrage_erstellt_von ON Angebotsanfrage(ErstelltVonID)',
            'CREATE INDEX idx_angebotsanfrage_abteilung ON Angebotsanfrage(ErstellerAbteilungID)',
            'CREATE INDEX idx_angebotsanfrage_status ON Angebotsanfrage(Status)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten
            if create_column_if_not_exists(conn, 'Angebotsanfrage', 'ErstellerAbteilungID', 'ALTER TABLE Angebotsanfrage ADD COLUMN ErstellerAbteilungID INTEGER NULL'):
                # Für bestehende Angebotsanfragen die Abteilung vom Ersteller übernehmen
                conn.execute('''
                    UPDATE Angebotsanfrage
                    SET ErstellerAbteilungID = (
                        SELECT PrimaerAbteilungID 
                        FROM Mitarbeiter 
                        WHERE Mitarbeiter.ID = Angebotsanfrage.ErstelltVonID
                    )
                    WHERE ErstellerAbteilungID IS NULL
                ''')
                print("[INFO] Spalte 'ErstellerAbteilungID' zu 'Angebotsanfrage' hinzugefügt")
            # Prüfe auf fehlende Indexes
            create_index_if_not_exists(conn, 'idx_angebotsanfrage_abteilung', 'CREATE INDEX idx_angebotsanfrage_abteilung ON Angebotsanfrage(ErstellerAbteilungID)')
        
        # ========== 25. AngebotsanfragePosition ==========
        created = create_table_if_not_exists(conn, 'AngebotsanfragePosition', '''
            CREATE TABLE AngebotsanfragePosition (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                AngebotsanfrageID INTEGER NOT NULL,
                ErsatzteilID INTEGER NULL,
                Menge INTEGER NOT NULL,
                Bemerkung TEXT NULL,
                Angebotspreis REAL NULL,
                Angebotswaehrung TEXT NULL,
                Bestellnummer TEXT NULL,
                Bezeichnung TEXT NULL,
                FOREIGN KEY (AngebotsanfrageID) REFERENCES Angebotsanfrage(ID) ON DELETE CASCADE,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID)
            )
        ''', [
            'CREATE INDEX idx_angebotsanfrage_position_anfrage ON AngebotsanfragePosition(AngebotsanfrageID)',
            'CREATE INDEX idx_angebotsanfrage_position_ersatzteil ON AngebotsanfragePosition(ErsatzteilID)'
        ])
        if not created:
            # Prüfe auf fehlende Spalten
            create_column_if_not_exists(conn, 'AngebotsanfragePosition', 'Bestellnummer', 'ALTER TABLE AngebotsanfragePosition ADD COLUMN Bestellnummer TEXT NULL')
            create_column_if_not_exists(conn, 'AngebotsanfragePosition', 'Bezeichnung', 'ALTER TABLE AngebotsanfragePosition ADD COLUMN Bezeichnung TEXT NULL')
        
        # ========== 26. Bestellung ==========
        created = create_table_if_not_exists(conn, 'Bestellung', '''
            CREATE TABLE Bestellung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                AngebotsanfrageID INTEGER NULL,
                LieferantID INTEGER NOT NULL,
                ErstelltVonID INTEGER NOT NULL,
                ErstellerAbteilungID INTEGER NULL,
                Status TEXT NOT NULL DEFAULT 'Erstellt',
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FreigegebenAm DATETIME NULL,
                FreigegebenVonID INTEGER NULL,
                BestelltAm DATETIME NULL,
                BestelltVonID INTEGER NULL,
                Bemerkung TEXT NULL,
                FOREIGN KEY (AngebotsanfrageID) REFERENCES Angebotsanfrage(ID),
                FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
                FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID),
                FOREIGN KEY (ErstellerAbteilungID) REFERENCES Abteilung(ID),
                FOREIGN KEY (FreigegebenVonID) REFERENCES Mitarbeiter(ID),
                FOREIGN KEY (BestelltVonID) REFERENCES Mitarbeiter(ID)
            )
        ''', [
            'CREATE INDEX idx_bestellung_angebotsanfrage ON Bestellung(AngebotsanfrageID)',
            'CREATE INDEX idx_bestellung_lieferant ON Bestellung(LieferantID)',
            'CREATE INDEX idx_bestellung_status ON Bestellung(Status)',
            'CREATE INDEX idx_bestellung_erstellt_von ON Bestellung(ErstelltVonID)',
            'CREATE INDEX idx_bestellung_abteilung ON Bestellung(ErstellerAbteilungID)',
            'CREATE INDEX idx_bestellung_erstellt_am ON Bestellung(ErstelltAm)'
        ])
        
        # ========== 27. BestellungPosition ==========
        created = create_table_if_not_exists(conn, 'BestellungPosition', '''
            CREATE TABLE BestellungPosition (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                BestellungID INTEGER NOT NULL,
                AngebotsanfragePositionID INTEGER NULL,
                ErsatzteilID INTEGER NULL,
                Menge INTEGER NOT NULL,
                ErhalteneMenge INTEGER NOT NULL DEFAULT 0,
                Bestellnummer TEXT NULL,
                Bezeichnung TEXT NULL,
                Bemerkung TEXT NULL,
                Preis REAL NULL,
                Waehrung TEXT NULL,
                FOREIGN KEY (BestellungID) REFERENCES Bestellung(ID) ON DELETE CASCADE,
                FOREIGN KEY (AngebotsanfragePositionID) REFERENCES AngebotsanfragePosition(ID),
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID)
            )
        ''', [
            'CREATE INDEX idx_bestellung_position_bestellung ON BestellungPosition(BestellungID)',
            'CREATE INDEX idx_bestellung_position_ersatzteil ON BestellungPosition(ErsatzteilID)',
            'CREATE INDEX idx_bestellung_position_angebotsanfrage ON BestellungPosition(AngebotsanfragePositionID)'
        ])
        if not created:
            # Prüfe auf fehlende Spalte ErhalteneMenge
            if create_column_if_not_exists(conn, 'BestellungPosition', 'ErhalteneMenge', 'ALTER TABLE BestellungPosition ADD COLUMN ErhalteneMenge INTEGER NOT NULL DEFAULT 0'):
                print("[INFO] Spalte 'ErhalteneMenge' zu 'BestellungPosition' hinzugefügt")
        
        # ========== 28. BestellungSichtbarkeit ==========
        created = create_table_if_not_exists(conn, 'BestellungSichtbarkeit', '''
            CREATE TABLE BestellungSichtbarkeit (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                BestellungID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (BestellungID) REFERENCES Bestellung(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(BestellungID, AbteilungID)
            )
        ''', [
            'CREATE INDEX idx_bestellung_sichtbarkeit_bestellung ON BestellungSichtbarkeit(BestellungID)',
            'CREATE INDEX idx_bestellung_sichtbarkeit_abteilung ON BestellungSichtbarkeit(AbteilungID)'
        ])
        if not created:
            # Prüfe auf fehlende Spalte ErstelltAm
            if create_column_if_not_exists(conn, 'BestellungSichtbarkeit', 'ErstelltAm', 'ALTER TABLE BestellungSichtbarkeit ADD COLUMN ErstelltAm DATETIME'):
                conn.execute('UPDATE BestellungSichtbarkeit SET ErstelltAm = datetime(\'now\') WHERE ErstelltAm IS NULL')
        
        # ========== 29. Berechtigung ==========
        created = create_table_if_not_exists(conn, 'Berechtigung', '''
            CREATE TABLE Berechtigung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Schluessel TEXT NOT NULL UNIQUE,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''', [
            'CREATE INDEX idx_berechtigung_schluessel ON Berechtigung(Schluessel)',
            'CREATE INDEX idx_berechtigung_aktiv ON Berechtigung(Aktiv)'
        ])
        if created:
            # Standard-Berechtigungen einfügen
            berechtigungen = [
                ('admin', 'Admin', 'Vollzugriff auf alle Admin-Funktionen'),
                ('artikel_buchen', 'Darf Artikel buchen', 'Erlaubt Lagerbuchungen von Ersatzteilen'),
                ('bestellungen_erstellen', 'Darf Bestellungen erstellen', 'Erlaubt das Erstellen von Bestellungen/Angebotsanfragen'),
                ('bestellungen_freigeben', 'Darf Bestellungen freigeben', 'Erlaubt die Freigabe von Bestellungen')
            ]
            for schluessel, bezeichnung, beschreibung in berechtigungen:
                conn.execute('''
                    INSERT OR IGNORE INTO Berechtigung (Schluessel, Bezeichnung, Beschreibung, Aktiv)
                    VALUES (?, ?, ?, 1)
                ''', (schluessel, bezeichnung, beschreibung))
        
        # ========== 30. MitarbeiterBerechtigung ==========
        created = create_table_if_not_exists(conn, 'MitarbeiterBerechtigung', '''
            CREATE TABLE MitarbeiterBerechtigung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                MitarbeiterID INTEGER NOT NULL,
                BerechtigungID INTEGER NOT NULL,
                FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
                FOREIGN KEY (BerechtigungID) REFERENCES Berechtigung(ID) ON DELETE CASCADE,
                UNIQUE(MitarbeiterID, BerechtigungID)
            )
        ''', [
            'CREATE INDEX idx_mitarbeiter_berechtigung_ma ON MitarbeiterBerechtigung(MitarbeiterID)',
            'CREATE INDEX idx_mitarbeiter_berechtigung_ber ON MitarbeiterBerechtigung(BerechtigungID)'
        ])
        
        # ========== Entferne ErsatzteilThemaVerknuepfung falls vorhanden (Migration 008) ==========
        if table_exists(conn, 'ErsatzteilThemaVerknuepfung'):
            conn.execute('DROP TABLE IF EXISTS ErsatzteilThemaVerknuepfung')
        
        # Änderungen speichern
        conn.commit()
        
        # BIS-Admin Abteilung und Benutzer erstellen (falls nicht vorhanden)
        if generate_password_hash:
            # BIS-Admin Abteilung erstellen (falls nicht vorhanden)
            cursor.execute("SELECT ID FROM Abteilung WHERE Bezeichnung = 'BIS-Admin'")
            abteilung = cursor.fetchone()
            if not abteilung:
                cursor.execute('''
                    INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung)
                    VALUES ('BIS-Admin', NULL, 1, 0)
                ''')
                abteilung_id = cursor.lastrowid
            else:
                abteilung_id = abteilung['ID']
            
            # BIS-Admin Benutzer erstellen (falls nicht vorhanden)
            cursor.execute("SELECT ID FROM Mitarbeiter WHERE Personalnummer = '99999'")
            benutzer = cursor.fetchone()
            if not benutzer:
                passwort_hash = generate_password_hash('a')
                cursor.execute('''
                    INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', ('99999', '', 'BIS-Admin', 1, passwort_hash, abteilung_id))
            
            # BIS-Admin Mitarbeitern Admin-Berechtigung geben
            cursor.execute("SELECT ID FROM Berechtigung WHERE Schluessel = 'admin'")
            admin_berechtigung = cursor.fetchone()
            if admin_berechtigung:
                admin_ber_id = admin_berechtigung['ID']
                # Primärabteilung BIS-Admin
                cursor.execute('SELECT ID FROM Mitarbeiter WHERE PrimaerAbteilungID = ?', (abteilung_id,))
                mitarbeiter_list = cursor.fetchall()
                for ma in mitarbeiter_list:
                    cursor.execute('''
                        INSERT OR IGNORE INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID)
                        VALUES (?, ?)
                    ''', (ma['ID'], admin_ber_id))
                # Zusätzliche Abteilung BIS-Admin
                cursor.execute('''
                    SELECT DISTINCT m.ID 
                    FROM Mitarbeiter m
                    JOIN MitarbeiterAbteilung ma ON m.ID = ma.MitarbeiterID
                    WHERE ma.AbteilungID = ?
                ''', (abteilung_id,))
                mitarbeiter_zusatz = cursor.fetchall()
                for ma in mitarbeiter_zusatz:
                    cursor.execute('''
                        INSERT OR IGNORE INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID)
                        VALUES (?, ?)
                    ''', (ma['ID'], admin_ber_id))
            
            conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database_on_startup(app):
    """
    Hauptfunktion: Prüft die Datenbank-Integrität beim App-Start und initialisiert fehlende Strukturen.
    Sollte in app.py beim Start aufgerufen werden.
    """
    db_path = app.config['DATABASE_URL']
    
    print("=" * 70)
    print("  BIS - Datenbank-Prüfung und Initialisierung")
    print("=" * 70)
    print()
    
    # Erstelle Datenbank falls nicht vorhanden
    if not os.path.exists(db_path):
        print(f"[INFO] Datenbank '{db_path}' existiert nicht, erstelle sie...")
        init_database_schema(db_path, verbose=False)
        print("[OK] Datenbank erstellt und initialisiert")
        print()
    
    # Prüfe Datenbank-Integrität
    print("[INFO] Prüfe Datenbank-Integrität...")
    is_valid, missing_tables, errors = check_database_integrity(db_path)
    
    if not is_valid:
        if missing_tables:
            print(f"[INFO] Fehlende Tabellen gefunden: {', '.join(missing_tables)}")
            print("[INFO] Initialisiere fehlende Strukturen...")
            init_database_schema(db_path, verbose=False)
            print("[OK] Datenbankstruktur aktualisiert")
        else:
            for error in errors:
                print(f"[FEHLER] {error}")
            print()
            sys.exit(1)
    else:
        print("[OK] Datenbank-Integrität OK")
        # Auch wenn alle Tabellen vorhanden sind, prüfe auf fehlende Spalten
        print("[INFO] Prüfe auf fehlende Spalten und Indexes...")
        init_database_schema(db_path, verbose=False)
        print("[OK] Spaltenprüfung abgeschlossen")
    
    print()
    print("=" * 70)
    print("  Datenbank-Prüfung abgeschlossen")
    print("=" * 70)
    print()
    
    return True

