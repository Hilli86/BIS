"""
Migration: Bestellung-Tabellen erstellen
Erstellt Tabellen für Bestellungen, BestellungPosition und BestellungSichtbarkeit
"""

import sqlite3
import os

DB_PATH = 'database_main.db'

def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def table_exists(conn, table_name):
    """Prüft, ob eine Tabelle existiert"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None

def migrate():
    """Erstellt die Bestellung-Tabellen"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # 1. Bestellung-Tabelle erstellen
        if not table_exists(conn, 'Bestellung'):
            conn.execute('''
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
            ''')
            
            # Indizes erstellen
            conn.execute('CREATE INDEX idx_bestellung_angebotsanfrage ON Bestellung(AngebotsanfrageID)')
            conn.execute('CREATE INDEX idx_bestellung_lieferant ON Bestellung(LieferantID)')
            conn.execute('CREATE INDEX idx_bestellung_status ON Bestellung(Status)')
            conn.execute('CREATE INDEX idx_bestellung_erstellt_von ON Bestellung(ErstelltVonID)')
            conn.execute('CREATE INDEX idx_bestellung_abteilung ON Bestellung(ErstellerAbteilungID)')
            conn.execute('CREATE INDEX idx_bestellung_erstellt_am ON Bestellung(ErstelltAm)')
            print("Bestellung-Tabelle erfolgreich erstellt.")
        else:
            print("Bestellung-Tabelle existiert bereits.")
        
        # 2. BestellungPosition-Tabelle erstellen
        if not table_exists(conn, 'BestellungPosition'):
            conn.execute('''
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
            ''')
            
            # Indizes erstellen
            conn.execute('CREATE INDEX idx_bestellung_position_bestellung ON BestellungPosition(BestellungID)')
            conn.execute('CREATE INDEX idx_bestellung_position_ersatzteil ON BestellungPosition(ErsatzteilID)')
            conn.execute('CREATE INDEX idx_bestellung_position_angebotsanfrage ON BestellungPosition(AngebotsanfragePositionID)')
            print("BestellungPosition-Tabelle erfolgreich erstellt.")
        else:
            print("BestellungPosition-Tabelle existiert bereits.")
            # Prüfe auf fehlende Spalte ErhalteneMenge
            if not column_exists(conn, 'BestellungPosition', 'ErhalteneMenge'):
                conn.execute('ALTER TABLE BestellungPosition ADD COLUMN ErhalteneMenge INTEGER NOT NULL DEFAULT 0')
                print("ErhalteneMenge-Spalte zu BestellungPosition hinzugefügt.")
        
        # 3. BestellungSichtbarkeit-Tabelle erstellen
        if not table_exists(conn, 'BestellungSichtbarkeit'):
            conn.execute('''
                CREATE TABLE BestellungSichtbarkeit (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    BestellungID INTEGER NOT NULL,
                    AbteilungID INTEGER NOT NULL,
                    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (BestellungID) REFERENCES Bestellung(ID) ON DELETE CASCADE,
                    FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                    UNIQUE(BestellungID, AbteilungID)
                )
            ''')
            
            # Indizes erstellen
            conn.execute('CREATE INDEX idx_bestellung_sichtbarkeit_bestellung ON BestellungSichtbarkeit(BestellungID)')
            conn.execute('CREATE INDEX idx_bestellung_sichtbarkeit_abteilung ON BestellungSichtbarkeit(AbteilungID)')
            print("BestellungSichtbarkeit-Tabelle erfolgreich erstellt.")
        else:
            print("BestellungSichtbarkeit-Tabelle existiert bereits.")
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen.")
        return True
        
    except Exception as e:
        print(f"Fehler beim Erstellen der Tabellen: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

