"""
Migration 006: Lagerort und Lagerplatz als separate Tabellen
Ersetzt Lagerort TEXT durch LagerortID und LagerplatzID (Foreign Keys)
"""

import sqlite3
import os
import sys

DB_PATH = 'database_main.db'

def run_migration():
    """Führt die Migration durch"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank '{DB_PATH}' nicht gefunden.")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("Starte Migration: Lagerort und Lagerplatz als separate Tabellen...")
        print()
        
        # Prüfe ob Tabellen bereits existieren
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Lagerort'")
        has_lagerort = cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Lagerplatz'")
        has_lagerplatz = cursor.fetchone() is not None
        
        # Prüfe ob Spalten bereits existieren
        cursor.execute("PRAGMA table_info(Ersatzteil)")
        columns = [row[1] for row in cursor.fetchall()]
        has_lagerort_id = 'LagerortID' in columns
        has_lagerplatz_id = 'LagerplatzID' in columns
        has_lagerort_text = 'Lagerort' in columns
        
        # 1. Tabellen erstellen (falls nicht vorhanden)
        if not has_lagerort:
            cursor.execute('''
                CREATE TABLE Lagerort (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Bezeichnung TEXT NOT NULL,
                    Beschreibung TEXT,
                    Aktiv INTEGER NOT NULL DEFAULT 1,
                    Sortierung INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('CREATE INDEX idx_lagerort_aktiv ON Lagerort(Aktiv)')
            cursor.execute('CREATE INDEX idx_lagerort_sortierung ON Lagerort(Sortierung)')
            print("  [OK] Tabelle 'Lagerort' erstellt")
        else:
            print("  [INFO] Tabelle 'Lagerort' existiert bereits")
        
        if not has_lagerplatz:
            cursor.execute('''
                CREATE TABLE Lagerplatz (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Bezeichnung TEXT NOT NULL,
                    Beschreibung TEXT,
                    Aktiv INTEGER NOT NULL DEFAULT 1,
                    Sortierung INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('CREATE INDEX idx_lagerplatz_aktiv ON Lagerplatz(Aktiv)')
            cursor.execute('CREATE INDEX idx_lagerplatz_sortierung ON Lagerplatz(Sortierung)')
            print("  [OK] Tabelle 'Lagerplatz' erstellt")
        else:
            print("  [INFO] Tabelle 'Lagerplatz' existiert bereits")
        
        # 2. Neue Spalten zu Ersatzteil hinzufügen (falls nicht vorhanden)
        if not has_lagerort_id:
            cursor.execute('ALTER TABLE Ersatzteil ADD COLUMN LagerortID INTEGER')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ersatzteil_lagerort ON Ersatzteil(LagerortID)')
            print("  [OK] Spalte 'LagerortID' zu Ersatzteil hinzugefügt")
        else:
            print("  [INFO] Spalte 'LagerortID' existiert bereits")
        
        if not has_lagerplatz_id:
            cursor.execute('ALTER TABLE Ersatzteil ADD COLUMN LagerplatzID INTEGER')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ersatzteil_lagerplatz ON Ersatzteil(LagerplatzID)')
            print("  [OK] Spalte 'LagerplatzID' zu Ersatzteil hinzugefügt")
        else:
            print("  [INFO] Spalte 'LagerplatzID' existiert bereits")
        
        # 3. Optional: Daten migrieren (falls Lagerort TEXT vorhanden)
        if has_lagerort_text:
            print()
            print("  [INFO] Alte 'Lagerort' TEXT-Spalte gefunden.")
            print("  [INFO] Bitte migrieren Sie die Daten manuell:")
            print("         - Erstellen Sie Lagerorte in der Admin-Verwaltung")
            print("         - Weisen Sie die Lagerorte den Ersatzteilen zu")
            print("  [INFO] Die alte 'Lagerort' TEXT-Spalte bleibt bestehen, wird aber nicht mehr verwendet.")
        
        conn.commit()
        conn.close()
        
        print()
        print("=" * 70)
        print("  [ERFOLG] Migration erfolgreich abgeschlossen!")
        print("=" * 70)
        print()
        
        if has_lagerort_text:
            print("HINWEIS: Die alte 'Lagerort' TEXT-Spalte existiert noch.")
            print("Sie können die Daten manuell migrieren oder die Spalte ignorieren.")
            print()
        
        return True
        
    except Exception as e:
        print(f"\n[FEHLER] Fehler bei der Migration: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
            conn.close()
        return False

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

