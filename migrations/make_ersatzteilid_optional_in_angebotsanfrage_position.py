"""
Migration: ErsatzteilID in AngebotsanfragePosition optional machen
Erlaubt das Erstellen von Positionen ohne ErsatzteilID
"""

import sqlite3
import os

DB_PATH = 'database_main.db'

def migrate():
    """Macht ErsatzteilID in AngebotsanfragePosition optional"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # SQLite unterstützt kein ALTER COLUMN direkt
        # Wir müssen die Tabelle neu erstellen
        
        # 1. Neue Tabelle mit optionaler ErsatzteilID erstellen
        conn.execute('''
            CREATE TABLE AngebotsanfragePosition_new (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                AngebotsanfrageID INTEGER NOT NULL,
                ErsatzteilID INTEGER NULL,
                Menge INTEGER NOT NULL,
                Bestellnummer TEXT NULL,
                Bezeichnung TEXT NULL,
                Bemerkung TEXT NULL,
                Angebotspreis REAL NULL,
                Angebotswaehrung TEXT NULL,
                FOREIGN KEY (AngebotsanfrageID) REFERENCES Angebotsanfrage(ID) ON DELETE CASCADE,
                FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID)
            )
        ''')
        
        # 2. Daten kopieren
        conn.execute('''
            INSERT INTO AngebotsanfragePosition_new 
            (ID, AngebotsanfrageID, ErsatzteilID, Menge, Bestellnummer, Bezeichnung, Bemerkung, Angebotspreis, Angebotswaehrung)
            SELECT ID, AngebotsanfrageID, ErsatzteilID, Menge, Bestellnummer, Bezeichnung, Bemerkung, Angebotspreis, Angebotswaehrung
            FROM AngebotsanfragePosition
        ''')
        
        # 3. Alte Tabelle löschen
        conn.execute('DROP TABLE AngebotsanfragePosition')
        
        # 4. Neue Tabelle umbenennen
        conn.execute('ALTER TABLE AngebotsanfragePosition_new RENAME TO AngebotsanfragePosition')
        
        # 5. Indizes neu erstellen
        conn.execute('CREATE INDEX idx_angebotsanfrage_position_anfrage ON AngebotsanfragePosition(AngebotsanfrageID)')
        conn.execute('CREATE INDEX idx_angebotsanfrage_position_ersatzteil ON AngebotsanfragePosition(ErsatzteilID)')
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen: ErsatzteilID ist jetzt optional.")
        return True
        
    except Exception as e:
        print(f"Fehler beim Migrieren der Tabelle: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

