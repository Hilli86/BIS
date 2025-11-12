"""
Migration: Bestellnummer und Bezeichnung zu AngebotsanfragePosition hinzufügen
Erweitert die Tabelle um Spalten für Bestellnummer und Bezeichnung
"""

import sqlite3
import os

DB_PATH = 'database_main.db'

def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def migrate():
    """Erweitert AngebotsanfragePosition um Bestellnummer und Bezeichnung"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Bestellnummer-Spalte hinzufügen
        if not column_exists(conn, 'AngebotsanfragePosition', 'Bestellnummer'):
            conn.execute('ALTER TABLE AngebotsanfragePosition ADD COLUMN Bestellnummer TEXT NULL')
            print("Bestellnummer-Spalte zu AngebotsanfragePosition hinzugefügt.")
        else:
            print("Bestellnummer-Spalte existiert bereits in AngebotsanfragePosition.")
        
        # Bezeichnung-Spalte hinzufügen
        if not column_exists(conn, 'AngebotsanfragePosition', 'Bezeichnung'):
            conn.execute('ALTER TABLE AngebotsanfragePosition ADD COLUMN Bezeichnung TEXT NULL')
            print("Bezeichnung-Spalte zu AngebotsanfragePosition hinzugefügt.")
        else:
            print("Bezeichnung-Spalte existiert bereits in AngebotsanfragePosition.")
        
        # Bestehende Einträge aktualisieren: Bestellnummer und Bezeichnung aus Ersatzteil holen
        conn.execute('''
            UPDATE AngebotsanfragePosition
            SET Bestellnummer = (
                SELECT e.Bestellnummer FROM Ersatzteil e 
                WHERE e.ID = AngebotsanfragePosition.ErsatzteilID
            ),
            Bezeichnung = (
                SELECT e.Bezeichnung FROM Ersatzteil e 
                WHERE e.ID = AngebotsanfragePosition.ErsatzteilID
            )
            WHERE Bestellnummer IS NULL OR Bezeichnung IS NULL
        ''')
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen.")
        return True
        
    except Exception as e:
        print(f"Fehler beim Erweitern der Tabelle: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

