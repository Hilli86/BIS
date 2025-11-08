"""
Migration 008: Entfernung der redundanten ErsatzteilThemaVerknuepfung-Tabelle
Die Tabelle ist redundant, da alle Informationen bereits in Lagerbuchung mit ThemaID vorhanden sind.
"""

import sqlite3
import os
import sys

DB_PATH = 'database_main.db'

def table_exists(cursor, table_name):
    """Prüft ob eine Tabelle existiert"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def run_migration():
    """Führt die Migration durch"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank '{DB_PATH}' nicht gefunden.")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print("=" * 70)
        print("  Migration 008: Entfernung ErsatzteilThemaVerknuepfung-Tabelle")
        print("=" * 70)
        print()
        
        # Prüfe ob Tabelle existiert
        if table_exists(cursor, 'ErsatzteilThemaVerknuepfung'):
            # Anzahl der Einträge prüfen
            count = cursor.execute('SELECT COUNT(*) as cnt FROM ErsatzteilThemaVerknuepfung').fetchone()['cnt']
            print(f"  [INFO] Tabelle 'ErsatzteilThemaVerknuepfung' gefunden ({count} Einträge)")
            print(f"  [INFO] Alle Daten werden gelöscht (sind bereits in Lagerbuchung vorhanden)")
            
            # Tabelle löschen
            cursor.execute('DROP TABLE IF EXISTS ErsatzteilThemaVerknuepfung')
            print("  [OK] Tabelle 'ErsatzteilThemaVerknuepfung' gelöscht")
        else:
            print("  [INFO] Tabelle 'ErsatzteilThemaVerknuepfung' existiert nicht (bereits entfernt)")
        
        conn.commit()
        conn.close()
        
        print()
        print("=" * 70)
        print("  [ERFOLG] Migration erfolgreich abgeschlossen!")
        print("=" * 70)
        print()
        print("HINWEIS: Alle Funktionen wurden bereits auf Lagerbuchung WHERE ThemaID umgestellt.")
        print("Die Tabelle war redundant und konnte sicher entfernt werden.")
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

