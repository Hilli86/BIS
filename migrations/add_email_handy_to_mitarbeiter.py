"""
Migration: Email und Handynummer zur Mitarbeiter-Tabelle hinzufügen
"""

import sqlite3
import os

DB_PATH = 'database_main.db'

def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def migrate():
    """Fügt Email und Handynummer zur Mitarbeiter-Tabelle hinzu"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Email-Spalte hinzufügen
        if not column_exists(conn, 'Mitarbeiter', 'Email'):
            conn.execute('ALTER TABLE Mitarbeiter ADD COLUMN Email TEXT NULL')
            print("Email-Spalte zur Mitarbeiter-Tabelle hinzugefügt.")
        else:
            print("Email-Spalte existiert bereits in Mitarbeiter-Tabelle.")
        
        # Handynummer-Spalte hinzufügen
        if not column_exists(conn, 'Mitarbeiter', 'Handynummer'):
            conn.execute('ALTER TABLE Mitarbeiter ADD COLUMN Handynummer TEXT NULL')
            print("Handynummer-Spalte zur Mitarbeiter-Tabelle hinzugefügt.")
        else:
            print("Handynummer-Spalte existiert bereits in Mitarbeiter-Tabelle.")
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen.")
        return True
        
    except Exception as e:
        print(f"Fehler beim Hinzufügen der Spalten: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

