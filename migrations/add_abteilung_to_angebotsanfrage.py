"""
Migration: Abteilungs-Spalte zu Angebotsanfrage hinzufügen
Fügt ErstellerAbteilungID zur Angebotsanfrage-Tabelle hinzu für abteilungsbasierte Filterung
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
    """Fügt ErstellerAbteilungID zur Angebotsanfrage-Tabelle hinzu"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # ErstellerAbteilungID-Spalte hinzufügen
        if not column_exists(conn, 'Angebotsanfrage', 'ErstellerAbteilungID'):
            conn.execute('ALTER TABLE Angebotsanfrage ADD COLUMN ErstellerAbteilungID INTEGER NULL')
            conn.execute('CREATE INDEX idx_angebotsanfrage_abteilung ON Angebotsanfrage(ErstellerAbteilungID)')
            print("ErstellerAbteilungID-Spalte zu Angebotsanfrage hinzugefügt.")
            
            # Bestehende Angebotsanfragen aktualisieren: Primärabteilung des Erstellers übernehmen
            update_query = '''
                UPDATE Angebotsanfrage
                SET ErstellerAbteilungID = (
                    SELECT PrimaerAbteilungID 
                    FROM Mitarbeiter 
                    WHERE Mitarbeiter.ID = Angebotsanfrage.ErstelltVonID
                )
                WHERE ErstellerAbteilungID IS NULL
            '''
            conn.execute(update_query)
            updated = conn.total_changes
            print(f"Abteilung für {updated} bestehende Angebotsanfragen aktualisiert.")
        else:
            print("ErstellerAbteilungID-Spalte existiert bereits in Angebotsanfrage.")
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen.")
        return True
        
    except Exception as e:
        print(f"Fehler bei der Migration: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

