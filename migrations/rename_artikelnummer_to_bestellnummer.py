"""
Migration: Artikelnummer -> Bestellnummer umbenennen
Führt die Umbenennung der Spalte Artikelnummer zu Bestellnummer in der Ersatzteil-Tabelle durch.
"""

import sqlite3
import os
import sys

# Pfad zur Datenbank
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database_main.db')


def run_migration():
    """Führt die Migration durch"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank nicht gefunden: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Prüfe ob Spalte Artikelnummer existiert
        cursor.execute("PRAGMA table_info(Ersatzteil)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'Artikelnummer' not in columns:
            print("Artikelnummer-Spalte existiert nicht. Migration möglicherweise bereits durchgeführt.")
            conn.close()
            return True
        
        if 'Bestellnummer' in columns:
            print("Bestellnummer-Spalte existiert bereits. Migration möglicherweise bereits durchgeführt.")
            conn.close()
            return True
        
        print("Starte Migration: Artikelnummer -> Bestellnummer")
        
        # SQLite unterstützt kein ALTER TABLE RENAME COLUMN direkt
        # Wir müssen eine neue Tabelle erstellen, Daten kopieren, alte löschen, neue umbenennen
        
        # 1. Neue Tabelle mit Bestellnummer erstellen
        print("  Erstelle neue Tabelle...")
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
        print("  Kopiere Daten...")
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
        print("  Lösche alte Tabelle...")
        cursor.execute('DROP TABLE Ersatzteil')
        
        # 4. Neue Tabelle umbenennen
        print("  Benenne neue Tabelle um...")
        cursor.execute('ALTER TABLE Ersatzteil_new RENAME TO Ersatzteil')
        
        # 5. Indexe neu erstellen
        print("  Erstelle Indexe neu...")
        cursor.execute('DROP INDEX IF EXISTS idx_ersatzteil_artikelnummer')
        cursor.execute('CREATE INDEX idx_ersatzteil_bestellnummer ON Ersatzteil(Bestellnummer)')
        
        # Bestehende Indexe bleiben erhalten, da sie nicht auf Artikelnummer verweisen
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen!")
        conn.close()
        return True
        
    except Exception as e:
        print(f"Fehler bei der Migration: {e}")
        conn.rollback()
        conn.close()
        return False


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

