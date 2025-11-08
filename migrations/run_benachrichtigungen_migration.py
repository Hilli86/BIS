"""
Migration Script für Benachrichtigungen
Führt die Migration 003_add_benachrichtigungen.sql aus
"""

import sqlite3
import os

def run_migration():
    """Führt die Benachrichtigungs-Migration aus (Standard-Funktionsname für automatische Ausführung)"""
    return run_benachrichtigungen_migration()

def run_benachrichtigungen_migration():
    """Führt die Benachrichtigungs-Migration aus"""
    db_path = os.environ.get('DATABASE_URL', 'database_main.db')
    
    if not os.path.exists(db_path):
        print(f"[FEHLER] Datenbank '{db_path}' nicht gefunden!")
        return False
    
    migration_file = os.path.join(os.path.dirname(__file__), '003_add_benachrichtigungen.sql')
    
    if not os.path.exists(migration_file):
        print(f"[FEHLER] Migrationsdatei '{migration_file}' nicht gefunden!")
        return False
    
    print("=" * 70)
    print("  BENACHRICHTIGUNGS-MIGRATION für BIS")
    print("=" * 70)
    print()
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Prüfen ob Tabelle bereits existiert
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='Benachrichtigung'
        """)
        
        if cursor.fetchone():
            print("[INFO] Tabelle 'Benachrichtigung' existiert bereits.")
            print("[SKIP] Migration wird übersprungen.")
            conn.close()
            return True
        
        # Migration ausführen
        print("[INFO] Führe Migration aus...")
        with open(migration_file, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # SQL-Befehle ausführen
        conn.executescript(sql_script)
        conn.commit()
        
        print("[OK] Migration erfolgreich ausgeführt!")
        print()
        print("Die Tabelle 'Benachrichtigung' wurde erstellt.")
        print("Benachrichtigungen werden nun automatisch erstellt bei:")
        print("  - Neuen Bemerkungen zu Themen")
        print("  - Neuen Themen in sichtbaren Abteilungen")
        print()
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"[FEHLER] Fehler bei der Migration: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

if __name__ == '__main__':
    success = run_benachrichtigungen_migration()
    exit(0 if success else 1)

