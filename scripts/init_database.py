"""
Datenbank-Initialisierungsskript für BIS
Erstellt die komplette Datenbankstruktur und legt einen BIS-Admin Benutzer an.
Prüft auf vorhandene Tabellen, Spalten und Indexes und erstellt sie nur, falls nicht vorhanden.

Voraussetzungen:
  - Python 3.x
  - pip install -r requirements.txt

Aufruf: py init_database.py
"""

import sqlite3
import os
import sys

# Prüfen ob Werkzeug verfügbar ist
try:
    from werkzeug.security import generate_password_hash
except ImportError:
    print("\n[FEHLER] Das Modul 'werkzeug' ist nicht installiert.")
    print("\nBitte fuehren Sie zuerst aus:")
    print("  pip install -r requirements.txt")
    print("\noder:")
    print("  pip install Werkzeug")
    print()
    sys.exit(1)

# Datenbankpfad
DB_PATH = 'database_main.db'


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
                    conn.execute(index_sql)
    
    return table_created


def create_column_if_not_exists(conn, table_name, column_name, alter_sql):
    """Erstellt eine Spalte falls sie nicht existiert"""
    if not column_exists(conn, table_name, column_name):
        try:
            conn.execute(alter_sql)
            return True
        except sqlite3.OperationalError as e:
            # Spalte könnte bereits existieren oder andere Probleme
            print(f"  [WARNUNG] Konnte Spalte {column_name} nicht hinzufügen: {e}")
            return False
    return False


def create_index_if_not_exists(conn, index_name, create_sql):
    """Erstellt einen Index falls er nicht existiert"""
    if not index_exists(conn, index_name):
        conn.execute(create_sql)
        return True
    return False


def init_database():
    """Initialisiert die Datenbank mit allen Tabellen und dem BIS-Admin User"""
    
    print("=" * 70)
    print("  BIS - Datenbank-Initialisierung")
    print("=" * 70)
    print()
    
    # Datenbankverbindung erstellen (wird automatisch erstellt falls nicht vorhanden)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        step = 1
        total_steps = 21
        
        # ========== 1. Mitarbeiter ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Mitarbeiter...")
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
        if created:
            print("  [OK] Tabelle Mitarbeiter erstellt")
        else:
            print("  [SKIP] Tabelle Mitarbeiter existiert bereits")
        step += 1
        
        # ========== 2. Abteilung ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Abteilung...")
        created = create_table_if_not_exists(conn, 'Abteilung', '''
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
        if created:
            print("  [OK] Tabelle Abteilung erstellt")
        else:
            print("  [SKIP] Tabelle Abteilung existiert bereits")
        step += 1
        
        # ========== 3. MitarbeiterAbteilung ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: MitarbeiterAbteilung...")
        created = create_table_if_not_exists(conn, 'MitarbeiterAbteilung', '''
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
        if created:
            print("  [OK] Tabelle MitarbeiterAbteilung erstellt")
        else:
            print("  [SKIP] Tabelle MitarbeiterAbteilung existiert bereits")
        step += 1
        
        # ========== 4. Bereich ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Bereich...")
        created = create_table_if_not_exists(conn, 'Bereich', '''
            CREATE TABLE Bereich (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''', [
            'CREATE INDEX idx_bereich_aktiv ON Bereich(Aktiv)'
        ])
        if created:
            print("  [OK] Tabelle Bereich erstellt")
        else:
            print("  [SKIP] Tabelle Bereich existiert bereits")
        step += 1
        
        # ========== 5. Gewerke ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Gewerke...")
        created = create_table_if_not_exists(conn, 'Gewerke', '''
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
        if created:
            print("  [OK] Tabelle Gewerke erstellt")
        else:
            print("  [SKIP] Tabelle Gewerke existiert bereits")
        step += 1
        
        # ========== 6. Status ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Status...")
        created = create_table_if_not_exists(conn, 'Status', '''
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
        if created:
            print("  [OK] Tabelle Status erstellt")
        else:
            print("  [SKIP] Tabelle Status existiert bereits")
        step += 1
        
        # ========== 7. Taetigkeit ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Taetigkeit...")
        created = create_table_if_not_exists(conn, 'Taetigkeit', '''
            CREATE TABLE Taetigkeit (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Sortierung INTEGER DEFAULT 0,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''', [
            'CREATE INDEX idx_taetigkeit_aktiv ON Taetigkeit(Aktiv)'
        ])
        if created:
            print("  [OK] Tabelle Taetigkeit erstellt")
        else:
            print("  [SKIP] Tabelle Taetigkeit existiert bereits")
        step += 1
        
        # ========== 8. SchichtbuchThema ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: SchichtbuchThema...")
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
        if created:
            print("  [OK] Tabelle SchichtbuchThema erstellt")
        else:
            print("  [SKIP] Tabelle SchichtbuchThema existiert bereits")
        step += 1
        
        # ========== 9. SchichtbuchBemerkungen ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: SchichtbuchBemerkungen...")
        created = create_table_if_not_exists(conn, 'SchichtbuchBemerkungen', '''
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
        if created:
            print("  [OK] Tabelle SchichtbuchBemerkungen erstellt")
        else:
            print("  [SKIP] Tabelle SchichtbuchBemerkungen existiert bereits")
        step += 1
        
        # ========== 10. SchichtbuchThemaSichtbarkeit ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: SchichtbuchThemaSichtbarkeit...")
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
        if created:
            print("  [OK] Tabelle SchichtbuchThemaSichtbarkeit erstellt")
        else:
            print("  [SKIP] Tabelle SchichtbuchThemaSichtbarkeit existiert bereits")
        step += 1
        
        # ========== 11. Benachrichtigung ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Benachrichtigung...")
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
        if created:
            print("  [OK] Tabelle Benachrichtigung erstellt")
        else:
            print("  [SKIP] Tabelle Benachrichtigung existiert bereits")
        step += 1
        
        # ========== 12. ErsatzteilKategorie ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: ErsatzteilKategorie...")
        created = create_table_if_not_exists(conn, 'ErsatzteilKategorie', '''
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
        if created:
            print("  [OK] Tabelle ErsatzteilKategorie erstellt")
        else:
            print("  [SKIP] Tabelle ErsatzteilKategorie existiert bereits")
        step += 1
        
        # ========== 13. Kostenstelle ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Kostenstelle...")
        created = create_table_if_not_exists(conn, 'Kostenstelle', '''
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
        if created:
            print("  [OK] Tabelle Kostenstelle erstellt")
        else:
            print("  [SKIP] Tabelle Kostenstelle existiert bereits")
        step += 1
        
        # ========== 14. Lieferant ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Lieferant...")
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
        if created:
            print("  [OK] Tabelle Lieferant erstellt")
        else:
            print("  [SKIP] Tabelle Lieferant existiert bereits")
            # Prüfe auf fehlende Spalten (Migration 005)
            create_column_if_not_exists(conn, 'Lieferant', 'Strasse', 'ALTER TABLE Lieferant ADD COLUMN Strasse TEXT')
            create_column_if_not_exists(conn, 'Lieferant', 'PLZ', 'ALTER TABLE Lieferant ADD COLUMN PLZ TEXT')
            create_column_if_not_exists(conn, 'Lieferant', 'Ort', 'ALTER TABLE Lieferant ADD COLUMN Ort TEXT')
        step += 1
        
        # ========== 15. Lagerort ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Lagerort...")
        created = create_table_if_not_exists(conn, 'Lagerort', '''
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
        if created:
            print("  [OK] Tabelle Lagerort erstellt")
        else:
            print("  [SKIP] Tabelle Lagerort existiert bereits")
        step += 1
        
        # ========== 16. Lagerplatz ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Lagerplatz...")
        created = create_table_if_not_exists(conn, 'Lagerplatz', '''
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
        if created:
            print("  [OK] Tabelle Lagerplatz erstellt")
        else:
            print("  [SKIP] Tabelle Lagerplatz existiert bereits")
        step += 1
        
        # ========== 17. Ersatzteil ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Ersatzteil...")
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
        if created:
            print("  [OK] Tabelle Ersatzteil erstellt")
        else:
            print("  [SKIP] Tabelle Ersatzteil existiert bereits")
            # Prüfe auf fehlende Spalten (Migration 006, 007)
            create_column_if_not_exists(conn, 'Ersatzteil', 'LagerortID', 'ALTER TABLE Ersatzteil ADD COLUMN LagerortID INTEGER')
            create_column_if_not_exists(conn, 'Ersatzteil', 'LagerplatzID', 'ALTER TABLE Ersatzteil ADD COLUMN LagerplatzID INTEGER')
            create_column_if_not_exists(conn, 'Ersatzteil', 'EndOfLife', 'ALTER TABLE Ersatzteil ADD COLUMN EndOfLife INTEGER NOT NULL DEFAULT 0')
            create_column_if_not_exists(conn, 'Ersatzteil', 'NachfolgeartikelID', 'ALTER TABLE Ersatzteil ADD COLUMN NachfolgeartikelID INTEGER NULL')
            create_column_if_not_exists(conn, 'Ersatzteil', 'Kennzeichen', 'ALTER TABLE Ersatzteil ADD COLUMN Kennzeichen TEXT NULL')
            create_column_if_not_exists(conn, 'Ersatzteil', 'ArtikelnummerHersteller', 'ALTER TABLE Ersatzteil ADD COLUMN ArtikelnummerHersteller TEXT NULL')
            # Prüfe auf fehlende Indexes
            create_index_if_not_exists(conn, 'idx_ersatzteil_lagerort', 'CREATE INDEX idx_ersatzteil_lagerort ON Ersatzteil(LagerortID)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_lagerplatz', 'CREATE INDEX idx_ersatzteil_lagerplatz ON Ersatzteil(LagerplatzID)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_nachfolgeartikel', 'CREATE INDEX idx_ersatzteil_nachfolgeartikel ON Ersatzteil(NachfolgeartikelID)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_kennzeichen', 'CREATE INDEX idx_ersatzteil_kennzeichen ON Ersatzteil(Kennzeichen)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_artikelnummer_hersteller', 'CREATE INDEX idx_ersatzteil_artikelnummer_hersteller ON Ersatzteil(ArtikelnummerHersteller)')
            create_index_if_not_exists(conn, 'idx_ersatzteil_bestand', 'CREATE INDEX idx_ersatzteil_bestand ON Ersatzteil(AktuellerBestand)')
        step += 1
        
        # ========== 18. ErsatzteilBild ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: ErsatzteilBild...")
        created = create_table_if_not_exists(conn, 'ErsatzteilBild', '''
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
        if created:
            print("  [OK] Tabelle ErsatzteilBild erstellt")
        else:
            print("  [SKIP] Tabelle ErsatzteilBild existiert bereits")
        step += 1
        
        # ========== 19. ErsatzteilDokument ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: ErsatzteilDokument...")
        created = create_table_if_not_exists(conn, 'ErsatzteilDokument', '''
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
        if created:
            print("  [OK] Tabelle ErsatzteilDokument erstellt")
        else:
            print("  [SKIP] Tabelle ErsatzteilDokument existiert bereits")
        step += 1
        
        # ========== 20. Lagerbuchung ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: Lagerbuchung...")
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
        if created:
            print("  [OK] Tabelle Lagerbuchung erstellt")
        else:
            print("  [SKIP] Tabelle Lagerbuchung existiert bereits")
            # Prüfe auf fehlende Spalten (Migration 009)
            create_column_if_not_exists(conn, 'Lagerbuchung', 'Preis', 'ALTER TABLE Lagerbuchung ADD COLUMN Preis REAL NULL')
            create_column_if_not_exists(conn, 'Lagerbuchung', 'Waehrung', 'ALTER TABLE Lagerbuchung ADD COLUMN Waehrung TEXT NULL')
            # Prüfe auf fehlende Indexes
            create_index_if_not_exists(conn, 'idx_lagerbuchung_verwendet_von', 'CREATE INDEX idx_lagerbuchung_verwendet_von ON Lagerbuchung(VerwendetVonID)')
            create_index_if_not_exists(conn, 'idx_lagerbuchung_buchungsdatum', 'CREATE INDEX idx_lagerbuchung_buchungsdatum ON Lagerbuchung(Buchungsdatum)')
        step += 1
        
        # ========== 21. ErsatzteilAbteilungZugriff ==========
        print(f"[{step}/{total_steps}] Prüfe Tabelle: ErsatzteilAbteilungZugriff...")
        created = create_table_if_not_exists(conn, 'ErsatzteilAbteilungZugriff', '''
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
        if created:
            print("  [OK] Tabelle ErsatzteilAbteilungZugriff erstellt")
        else:
            print("  [SKIP] Tabelle ErsatzteilAbteilungZugriff existiert bereits")
        
        # ========== Entferne ErsatzteilThemaVerknuepfung falls vorhanden (Migration 008) ==========
        if table_exists(conn, 'ErsatzteilThemaVerknuepfung'):
            print("[INFO] Entferne veraltete Tabelle: ErsatzteilThemaVerknuepfung...")
            conn.execute('DROP TABLE IF EXISTS ErsatzteilThemaVerknuepfung')
            print("  [OK] Tabelle ErsatzteilThemaVerknuepfung entfernt")
        
        # Änderungen speichern
        conn.commit()
        
        print()
        print("=" * 70)
        print("  Erstelle BIS-Admin Abteilung und Benutzer")
        print("=" * 70)
        print()
        
        # BIS-Admin Abteilung erstellen (falls nicht vorhanden)
        cursor.execute("SELECT ID FROM Abteilung WHERE Bezeichnung = 'BIS-Admin'")
        abteilung = cursor.fetchone()
        if abteilung:
            abteilung_id = abteilung['ID']
            print(f"[SKIP] Abteilung 'BIS-Admin' existiert bereits (ID: {abteilung_id})")
        else:
            cursor.execute('''
                INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung)
                VALUES ('BIS-Admin', NULL, 1, 0)
            ''')
            abteilung_id = cursor.lastrowid
            print(f"[OK] Abteilung 'BIS-Admin' erstellt (ID: {abteilung_id})")
        
        # BIS-Admin Benutzer erstellen (falls nicht vorhanden)
        cursor.execute("SELECT ID FROM Mitarbeiter WHERE Personalnummer = '99999'")
        benutzer = cursor.fetchone()
        if benutzer:
            user_id = benutzer['ID']
            print(f"[SKIP] Benutzer 'BIS-Admin' existiert bereits (ID: {user_id})")
        else:
            # Passwort hashen
            passwort_hash = generate_password_hash('a')
            
            cursor.execute('''
                INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('99999', '', 'BIS-Admin', 1, passwort_hash, abteilung_id))
            user_id = cursor.lastrowid
            print(f"[OK] Benutzer 'BIS-Admin' erstellt (ID: {user_id})")
            print(f"  - Personalnummer: 99999")
            print(f"  - Passwort: a")
        
        # Änderungen speichern
        conn.commit()
        
        print()
        print("=" * 70)
        print("  [ERFOLG] Datenbank erfolgreich initialisiert!")
        print("=" * 70)
        print()
        print("Login-Daten:")
        print("  Personalnummer: 99999")
        print("  Passwort: a")
        print()
        
    except Exception as e:
        print(f"\n[FEHLER] Fehler bei der Initialisierung: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    init_database()
