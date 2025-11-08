"""
Datenbank-Initialisierungsskript für BIS
Erstellt die komplette Datenbankstruktur und legt einen BIS-Admin Benutzer an.

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

def init_database():
    """Initialisiert die Datenbank mit allen Tabellen und dem BIS-Admin User"""
    
    print("=" * 70)
    print("  BIS - Datenbank-Initialisierung")
    print("=" * 70)
    print()
    
    # Prüfen ob Datenbank bereits existiert
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        antwort = input(f"WARNUNG: Datenbank '{DB_PATH}' existiert bereits. Wirklich ueberschreiben? (ja/nein): ")
        if antwort.lower() not in ['ja', 'j', 'yes', 'y']:
            print("Abgebrochen.")
            return
        
        # Alte Datenbank löschen
        os.remove(DB_PATH)
        print(f"[OK] Alte Datenbank geloescht")
        print()
    
    # Neue Datenbankverbindung
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("[1/10] Erstelle Tabelle: Mitarbeiter...")
        cursor.execute('''
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
        ''')
        cursor.execute('CREATE INDEX idx_mitarbeiter_aktiv ON Mitarbeiter(Aktiv)')
        cursor.execute('CREATE INDEX idx_mitarbeiter_personalnummer ON Mitarbeiter(Personalnummer)')
        print("  [OK] Tabelle Mitarbeiter erstellt")
        
        print("[2/10] Erstelle Tabelle: Abteilung...")
        cursor.execute('''
            CREATE TABLE Abteilung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                ParentAbteilungID INTEGER NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0,
                FOREIGN KEY (ParentAbteilungID) REFERENCES Abteilung(ID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_abteilung_parent ON Abteilung(ParentAbteilungID)')
        cursor.execute('CREATE INDEX idx_abteilung_aktiv ON Abteilung(Aktiv)')
        print("  [OK] Tabelle Abteilung erstellt")
        
        print("[3/10] Erstelle Tabelle: MitarbeiterAbteilung...")
        cursor.execute('''
            CREATE TABLE MitarbeiterAbteilung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                MitarbeiterID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(MitarbeiterID, AbteilungID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_mitarbeiter_abteilung_ma ON MitarbeiterAbteilung(MitarbeiterID)')
        cursor.execute('CREATE INDEX idx_mitarbeiter_abteilung_abt ON MitarbeiterAbteilung(AbteilungID)')
        print("  [OK] Tabelle MitarbeiterAbteilung erstellt")
        
        print("[4/10] Erstelle Tabelle: Bereich...")
        cursor.execute('''
            CREATE TABLE Bereich (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''')
        cursor.execute('CREATE INDEX idx_bereich_aktiv ON Bereich(Aktiv)')
        print("  [OK] Tabelle Bereich erstellt")
        
        print("[5/10] Erstelle Tabelle: Gewerke...")
        cursor.execute('''
            CREATE TABLE Gewerke (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                BereichID INTEGER NOT NULL,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (BereichID) REFERENCES Bereich(ID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_gewerke_bereich ON Gewerke(BereichID)')
        cursor.execute('CREATE INDEX idx_gewerke_aktiv ON Gewerke(Aktiv)')
        print("  [OK] Tabelle Gewerke erstellt")
        
        print("[6/10] Erstelle Tabelle: Status...")
        cursor.execute('''
            CREATE TABLE Status (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Farbe TEXT,
                Sortierung INTEGER DEFAULT 0,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''')
        cursor.execute('CREATE INDEX idx_status_aktiv ON Status(Aktiv)')
        print("  [OK] Tabelle Status erstellt")
        
        print("[7/10] Erstelle Tabelle: Taetigkeit...")
        cursor.execute('''
            CREATE TABLE Taetigkeit (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Sortierung INTEGER DEFAULT 0,
                Aktiv INTEGER NOT NULL DEFAULT 1
            )
        ''')
        cursor.execute('CREATE INDEX idx_taetigkeit_aktiv ON Taetigkeit(Aktiv)')
        print("  [OK] Tabelle Taetigkeit erstellt")
        
        print("[8/10] Erstelle Tabelle: SchichtbuchThema...")
        cursor.execute('''
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
        ''')
        cursor.execute('CREATE INDEX idx_thema_gewerk ON SchichtbuchThema(GewerkID)')
        cursor.execute('CREATE INDEX idx_thema_status ON SchichtbuchThema(StatusID)')
        cursor.execute('CREATE INDEX idx_thema_abteilung ON SchichtbuchThema(ErstellerAbteilungID)')
        cursor.execute('CREATE INDEX idx_thema_geloescht ON SchichtbuchThema(Gelöscht)')
        print("  [OK] Tabelle SchichtbuchThema erstellt")
        
        print("[9/10] Erstelle Tabelle: SchichtbuchBemerkungen...")
        cursor.execute('''
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
        ''')
        cursor.execute('CREATE INDEX idx_bemerkung_thema ON SchichtbuchBemerkungen(ThemaID)')
        cursor.execute('CREATE INDEX idx_bemerkung_mitarbeiter ON SchichtbuchBemerkungen(MitarbeiterID)')
        cursor.execute('CREATE INDEX idx_bemerkung_geloescht ON SchichtbuchBemerkungen(Gelöscht)')
        print("  [OK] Tabelle SchichtbuchBemerkungen erstellt")
        
        print("[10/11] Erstelle Tabelle: SchichtbuchThemaSichtbarkeit...")
        cursor.execute('''
            CREATE TABLE SchichtbuchThemaSichtbarkeit (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ThemaID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(ThemaID, AbteilungID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_sichtbarkeit_thema ON SchichtbuchThemaSichtbarkeit(ThemaID)')
        cursor.execute('CREATE INDEX idx_sichtbarkeit_abteilung ON SchichtbuchThemaSichtbarkeit(AbteilungID)')
        print("  [OK] Tabelle SchichtbuchThemaSichtbarkeit erstellt")
        
        print("[11/12] Erstelle Tabelle: Benachrichtigung...")
        cursor.execute('''
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
        ''')
        cursor.execute('CREATE INDEX idx_benachrichtigung_mitarbeiter ON Benachrichtigung(MitarbeiterID)')
        cursor.execute('CREATE INDEX idx_benachrichtigung_thema ON Benachrichtigung(ThemaID)')
        cursor.execute('CREATE INDEX idx_benachrichtigung_gelesen ON Benachrichtigung(Gelesen)')
        print("  [OK] Tabelle Benachrichtigung erstellt")
        
        print("[12/12] Erstelle Tabellen: Ersatzteilverwaltung...")
        # ErsatzteilKategorie
        cursor.execute('''
            CREATE TABLE ErsatzteilKategorie (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('CREATE INDEX idx_ersatzteil_kategorie_aktiv ON ErsatzteilKategorie(Aktiv)')
        print("  [OK] Tabelle ErsatzteilKategorie erstellt")
        
        # Kostenstelle
        cursor.execute('''
            CREATE TABLE Kostenstelle (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Sortierung INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('CREATE INDEX idx_kostenstelle_aktiv ON Kostenstelle(Aktiv)')
        print("  [OK] Tabelle Kostenstelle erstellt")
        
        # Lieferant
        cursor.execute('''
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
        ''')
        cursor.execute('CREATE INDEX idx_lieferant_aktiv ON Lieferant(Aktiv)')
        print("  [OK] Tabelle Lieferant erstellt")
        
        # Ersatzteil
        cursor.execute('''
            CREATE TABLE Ersatzteil (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Artikelnummer TEXT NOT NULL UNIQUE,
                Bezeichnung TEXT NOT NULL,
                Beschreibung TEXT,
                KategorieID INTEGER,
                Hersteller TEXT,
                LieferantID INTEGER,
                Preis REAL,
                Waehrung TEXT DEFAULT 'EUR',
                Lagerort TEXT,
                Mindestbestand INTEGER DEFAULT 0,
                AktuellerBestand INTEGER DEFAULT 0,
                Einheit TEXT DEFAULT 'Stück',
                Aktiv INTEGER NOT NULL DEFAULT 1,
                Gelöscht INTEGER NOT NULL DEFAULT 0,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                ErstelltVonID INTEGER,
                FOREIGN KEY (KategorieID) REFERENCES ErsatzteilKategorie(ID),
                FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
                FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_ersatzteil_artikelnummer ON Ersatzteil(Artikelnummer)')
        cursor.execute('CREATE INDEX idx_ersatzteil_kategorie ON Ersatzteil(KategorieID)')
        cursor.execute('CREATE INDEX idx_ersatzteil_lieferant ON Ersatzteil(LieferantID)')
        cursor.execute('CREATE INDEX idx_ersatzteil_aktiv ON Ersatzteil(Aktiv)')
        cursor.execute('CREATE INDEX idx_ersatzteil_geloescht ON Ersatzteil(Gelöscht)')
        print("  [OK] Tabelle Ersatzteil erstellt")
        
        # ErsatzteilBild
        cursor.execute('''
            CREATE TABLE ErsatzteilBild (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                Dateiname TEXT NOT NULL,
                Dateipfad TEXT NOT NULL,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX idx_ersatzteil_bild_ersatzteil ON ErsatzteilBild(ErsatzteilID)')
        print("  [OK] Tabelle ErsatzteilBild erstellt")
        
        # ErsatzteilDokument
        cursor.execute('''
            CREATE TABLE ErsatzteilDokument (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                Dateiname TEXT NOT NULL,
                Dateipfad TEXT NOT NULL,
                Typ TEXT,
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX idx_ersatzteil_dokument_ersatzteil ON ErsatzteilDokument(ErsatzteilID)')
        print("  [OK] Tabelle ErsatzteilDokument erstellt")
        
        # Lagerbuchung (kein Gelöscht-Flag!)
        cursor.execute('''
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
                ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID),
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID),
                FOREIGN KEY (KostenstelleID) REFERENCES Kostenstelle(ID),
                FOREIGN KEY (VerwendetVonID) REFERENCES Mitarbeiter(ID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_lagerbuchung_ersatzteil ON Lagerbuchung(ErsatzteilID)')
        cursor.execute('CREATE INDEX idx_lagerbuchung_thema ON Lagerbuchung(ThemaID)')
        cursor.execute('CREATE INDEX idx_lagerbuchung_kostenstelle ON Lagerbuchung(KostenstelleID)')
        print("  [OK] Tabelle Lagerbuchung erstellt")
        
        # ErsatzteilThemaVerknuepfung
        cursor.execute('''
            CREATE TABLE ErsatzteilThemaVerknuepfung (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                ThemaID INTEGER NOT NULL,
                Menge INTEGER NOT NULL,
                VerwendetVonID INTEGER NOT NULL,
                VerwendetAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                Bemerkung TEXT,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID),
                FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
                FOREIGN KEY (VerwendetVonID) REFERENCES Mitarbeiter(ID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_ersatzteil_thema_ersatzteil ON ErsatzteilThemaVerknuepfung(ErsatzteilID)')
        cursor.execute('CREATE INDEX idx_ersatzteil_thema_thema ON ErsatzteilThemaVerknuepfung(ThemaID)')
        print("  [OK] Tabelle ErsatzteilThemaVerknuepfung erstellt")
        
        # ErsatzteilAbteilungZugriff
        cursor.execute('''
            CREATE TABLE ErsatzteilAbteilungZugriff (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ErsatzteilID INTEGER NOT NULL,
                AbteilungID INTEGER NOT NULL,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE,
                FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                UNIQUE(ErsatzteilID, AbteilungID)
            )
        ''')
        cursor.execute('CREATE INDEX idx_ersatzteil_abteilung_ersatzteil ON ErsatzteilAbteilungZugriff(ErsatzteilID)')
        cursor.execute('CREATE INDEX idx_ersatzteil_abteilung_abteilung ON ErsatzteilAbteilungZugriff(AbteilungID)')
        print("  [OK] Tabelle ErsatzteilAbteilungZugriff erstellt")
        
        print()
        print("=" * 70)
        print("  Erstelle BIS-Admin Abteilung und Benutzer")
        print("=" * 70)
        print()
        
        # BIS-Admin Abteilung erstellen
        cursor.execute('''
            INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung)
            VALUES ('BIS-Admin', NULL, 1, 0)
        ''')
        abteilung_id = cursor.lastrowid
        print(f"[OK] Abteilung 'BIS-Admin' erstellt (ID: {abteilung_id})")
        
        # Passwort hashen
        passwort_hash = generate_password_hash('a')
        
        # BIS-Admin Benutzer erstellen
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
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    init_database()

