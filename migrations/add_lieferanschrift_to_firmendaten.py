"""
Migration: Lieferanschrift zur Firmendaten-Tabelle hinzufügen
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
    """Fügt Lieferanschrift-Felder zur Firmendaten-Tabelle hinzu"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # LieferStrasse-Spalte hinzufügen
        if not column_exists(conn, 'Firmendaten', 'LieferStrasse'):
            conn.execute('ALTER TABLE Firmendaten ADD COLUMN LieferStrasse TEXT NULL')
            print("LieferStrasse-Spalte zur Firmendaten-Tabelle hinzugefügt.")
        else:
            print("LieferStrasse-Spalte existiert bereits in Firmendaten-Tabelle.")
        
        # LieferPLZ-Spalte hinzufügen
        if not column_exists(conn, 'Firmendaten', 'LieferPLZ'):
            conn.execute('ALTER TABLE Firmendaten ADD COLUMN LieferPLZ TEXT NULL')
            print("LieferPLZ-Spalte zur Firmendaten-Tabelle hinzugefügt.")
        else:
            print("LieferPLZ-Spalte existiert bereits in Firmendaten-Tabelle.")
        
        # LieferOrt-Spalte hinzufügen
        if not column_exists(conn, 'Firmendaten', 'LieferOrt'):
            conn.execute('ALTER TABLE Firmendaten ADD COLUMN LieferOrt TEXT NULL')
            print("LieferOrt-Spalte zur Firmendaten-Tabelle hinzugefügt.")
        else:
            print("LieferOrt-Spalte existiert bereits in Firmendaten-Tabelle.")
        
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

