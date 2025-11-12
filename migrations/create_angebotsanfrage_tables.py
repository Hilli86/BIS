"""
Migration: Angebotsanfrage-Tabellen erstellen
Erstellt Tabellen für Angebotsanfragen und erweitert Ersatzteil um Preisstand-Spalte
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
    """Erstellt die Angebotsanfrage-Tabellen und erweitert Ersatzteil"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # 1. Angebotsanfrage-Tabelle erstellen
        if not table_exists(conn, 'Angebotsanfrage'):
            conn.execute('''
                CREATE TABLE Angebotsanfrage (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    LieferantID INTEGER NOT NULL,
                    ErstelltVonID INTEGER NOT NULL,
                    Status TEXT NOT NULL DEFAULT 'Offen',
                    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                    VersendetAm DATETIME NULL,
                    AngebotErhaltenAm DATETIME NULL,
                    Bemerkung TEXT NULL,
                    FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
                    FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID)
                )
            ''')
            
            # Indizes erstellen
            conn.execute('CREATE INDEX idx_angebotsanfrage_lieferant ON Angebotsanfrage(LieferantID)')
            conn.execute('CREATE INDEX idx_angebotsanfrage_status ON Angebotsanfrage(Status)')
            conn.execute('CREATE INDEX idx_angebotsanfrage_erstellt_von ON Angebotsanfrage(ErstelltVonID)')
            conn.execute('CREATE INDEX idx_angebotsanfrage_erstellt_am ON Angebotsanfrage(ErstelltAm)')
            print("Angebotsanfrage-Tabelle erfolgreich erstellt.")
        else:
            print("Angebotsanfrage-Tabelle existiert bereits.")
        
        # 2. AngebotsanfragePosition-Tabelle erstellen
        if not table_exists(conn, 'AngebotsanfragePosition'):
            conn.execute('''
                CREATE TABLE AngebotsanfragePosition (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    AngebotsanfrageID INTEGER NOT NULL,
                    ErsatzteilID INTEGER NOT NULL,
                    Menge INTEGER NOT NULL,
                    Bemerkung TEXT NULL,
                    Angebotspreis REAL NULL,
                    Angebotswaehrung TEXT NULL,
                    FOREIGN KEY (AngebotsanfrageID) REFERENCES Angebotsanfrage(ID) ON DELETE CASCADE,
                    FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID)
                )
            ''')
            
            # Indizes erstellen
            conn.execute('CREATE INDEX idx_angebotsanfrage_position_anfrage ON AngebotsanfragePosition(AngebotsanfrageID)')
            conn.execute('CREATE INDEX idx_angebotsanfrage_position_ersatzteil ON AngebotsanfragePosition(ErsatzteilID)')
            print("AngebotsanfragePosition-Tabelle erfolgreich erstellt.")
        else:
            print("AngebotsanfragePosition-Tabelle existiert bereits.")
        
        # 3. Preisstand-Spalte zu Ersatzteil hinzufügen
        if not column_exists(conn, 'Ersatzteil', 'Preisstand'):
            conn.execute('ALTER TABLE Ersatzteil ADD COLUMN Preisstand DATETIME NULL')
            print("Preisstand-Spalte zu Ersatzteil hinzugefügt.")
        else:
            print("Preisstand-Spalte existiert bereits in Ersatzteil.")
        
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

