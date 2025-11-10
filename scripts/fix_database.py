"""
Schnellfix: Fügt fehlende Spalte ErstelltAm zu SchichtbuchThema hinzu
"""

import sqlite3
import sys

DB_PATH = 'database_main.db'

def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def fix_database():
    """Fügt fehlende Spalte hinzu"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        if not column_exists(conn, 'SchichtbuchThema', 'ErstelltAm'):
            print("[INFO] Füge fehlende Spalte 'ErstelltAm' zu 'SchichtbuchThema' hinzu...")
            # SQLite unterstützt kein DEFAULT CURRENT_TIMESTAMP beim ALTER TABLE
            # Füge Spalte ohne DEFAULT hinzu
            conn.execute('ALTER TABLE SchichtbuchThema ADD COLUMN ErstelltAm DATETIME')
            # Setze für bestehende Einträge das Datum der ersten Bemerkung oder aktuelles Datum
            conn.execute('''
                UPDATE SchichtbuchThema 
                SET ErstelltAm = COALESCE(
                    (SELECT MIN(Datum) FROM SchichtbuchBemerkungen WHERE ThemaID = SchichtbuchThema.ID),
                    datetime('now')
                )
                WHERE ErstelltAm IS NULL
            ''')
            conn.commit()
            print("[OK] Spalte erfolgreich hinzugefügt!")
        else:
            print("[OK] Spalte 'ErstelltAm' existiert bereits in 'SchichtbuchThema'")
        
        # Prüfe auch andere Tabellen
        if not column_exists(conn, 'SchichtbuchThemaSichtbarkeit', 'ErstelltAm'):
            print("[INFO] Füge fehlende Spalte 'ErstelltAm' zu 'SchichtbuchThemaSichtbarkeit' hinzu...")
            conn.execute('ALTER TABLE SchichtbuchThemaSichtbarkeit ADD COLUMN ErstelltAm DATETIME')
            conn.execute('UPDATE SchichtbuchThemaSichtbarkeit SET ErstelltAm = datetime(\'now\') WHERE ErstelltAm IS NULL')
            conn.commit()
            print("[OK] Spalte erfolgreich hinzugefügt!")
        
        if not column_exists(conn, 'Benachrichtigung', 'ErstelltAm'):
            print("[INFO] Füge fehlende Spalte 'ErstelltAm' zu 'Benachrichtigung' hinzu...")
            conn.execute('ALTER TABLE Benachrichtigung ADD COLUMN ErstelltAm DATETIME')
            conn.execute('UPDATE Benachrichtigung SET ErstelltAm = datetime(\'now\') WHERE ErstelltAm IS NULL')
            conn.commit()
            print("[OK] Spalte erfolgreich hinzugefügt!")
        
        if not column_exists(conn, 'Mitarbeiter', 'PrimaerAbteilungID'):
            print("[INFO] Füge fehlende Spalte 'PrimaerAbteilungID' zu 'Mitarbeiter' hinzu...")
            conn.execute('ALTER TABLE Mitarbeiter ADD COLUMN PrimaerAbteilungID INTEGER')
            conn.commit()
            print("[OK] Spalte erfolgreich hinzugefügt!")
        
        conn.close()
        print("\n[ERFOLG] Datenbank-Update abgeschlossen!")
        
    except Exception as e:
        print(f"\n[FEHLER] Fehler beim Update: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    fix_database()

