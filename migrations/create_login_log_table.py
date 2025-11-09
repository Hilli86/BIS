"""
Migration: LoginLog-Tabelle erstellen
Erstellt eine Tabelle für Login-Logs
"""

import sqlite3
import os

DB_PATH = 'database_main.db'

def migrate():
    """Erstellt die LoginLog-Tabelle"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Prüfe ob Tabelle bereits existiert
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='LoginLog'"
        )
        if cursor.fetchone():
            print("LoginLog-Tabelle existiert bereits.")
            return True
        
        # Erstelle LoginLog-Tabelle
        conn.execute('''
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
        ''')
        
        # Erstelle Indizes
        conn.execute('CREATE INDEX idx_loginlog_mitarbeiter ON LoginLog(MitarbeiterID)')
        conn.execute('CREATE INDEX idx_loginlog_zeitpunkt ON LoginLog(Zeitpunkt)')
        conn.execute('CREATE INDEX idx_loginlog_erfolgreich ON LoginLog(Erfolgreich)')
        conn.execute('CREATE INDEX idx_loginlog_personalnummer ON LoginLog(Personalnummer)')
        
        conn.commit()
        print("LoginLog-Tabelle erfolgreich erstellt.")
        return True
        
    except Exception as e:
        print(f"Fehler beim Erstellen der LoginLog-Tabelle: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

