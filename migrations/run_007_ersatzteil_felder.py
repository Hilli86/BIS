"""
Migration 007: Erweiterung Ersatzteil-Tabelle
Hinzufügen von EndOfLife, NachfolgeartikelID, Kennzeichen und ArtikelnummerHersteller
"""

import sqlite3
import os
import sys

DB_PATH = 'database_main.db'

def column_exists(cursor, table_name, column_name):
    """Prüft ob eine Spalte existiert"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def index_exists(cursor, index_name):
    """Prüft ob ein Index existiert"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
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
        print("  Migration 007: Erweiterung Ersatzteil-Tabelle")
        print("=" * 70)
        print()
        
        # 1. EndOfLife hinzufügen
        if not column_exists(cursor, 'Ersatzteil', 'EndOfLife'):
            cursor.execute('ALTER TABLE Ersatzteil ADD COLUMN EndOfLife INTEGER NOT NULL DEFAULT 0')
            print("  [OK] Spalte 'EndOfLife' hinzugefügt")
        else:
            print("  [INFO] Spalte 'EndOfLife' existiert bereits")
        
        # 2. NachfolgeartikelID hinzufügen
        if not column_exists(cursor, 'Ersatzteil', 'NachfolgeartikelID'):
            cursor.execute('ALTER TABLE Ersatzteil ADD COLUMN NachfolgeartikelID INTEGER NULL')
            print("  [OK] Spalte 'NachfolgeartikelID' hinzugefügt")
        else:
            print("  [INFO] Spalte 'NachfolgeartikelID' existiert bereits")
        
        if not index_exists(cursor, 'idx_ersatzteil_nachfolgeartikel'):
            cursor.execute('CREATE INDEX idx_ersatzteil_nachfolgeartikel ON Ersatzteil(NachfolgeartikelID)')
            print("  [OK] Index 'idx_ersatzteil_nachfolgeartikel' erstellt")
        else:
            print("  [INFO] Index 'idx_ersatzteil_nachfolgeartikel' existiert bereits")
        
        # 3. Kennzeichen hinzufügen
        if not column_exists(cursor, 'Ersatzteil', 'Kennzeichen'):
            cursor.execute('ALTER TABLE Ersatzteil ADD COLUMN Kennzeichen TEXT NULL')
            print("  [OK] Spalte 'Kennzeichen' hinzugefügt")
        else:
            print("  [INFO] Spalte 'Kennzeichen' existiert bereits")
        
        if not index_exists(cursor, 'idx_ersatzteil_kennzeichen'):
            cursor.execute('CREATE INDEX idx_ersatzteil_kennzeichen ON Ersatzteil(Kennzeichen)')
            print("  [OK] Index 'idx_ersatzteil_kennzeichen' erstellt")
        else:
            print("  [INFO] Index 'idx_ersatzteil_kennzeichen' existiert bereits")
        
        # 4. ArtikelnummerHersteller hinzufügen
        if not column_exists(cursor, 'Ersatzteil', 'ArtikelnummerHersteller'):
            cursor.execute('ALTER TABLE Ersatzteil ADD COLUMN ArtikelnummerHersteller TEXT NULL')
            print("  [OK] Spalte 'ArtikelnummerHersteller' hinzugefügt")
        else:
            print("  [INFO] Spalte 'ArtikelnummerHersteller' existiert bereits")
        
        if not index_exists(cursor, 'idx_ersatzteil_artikelnummer_hersteller'):
            cursor.execute('CREATE INDEX idx_ersatzteil_artikelnummer_hersteller ON Ersatzteil(ArtikelnummerHersteller)')
            print("  [OK] Index 'idx_ersatzteil_artikelnummer_hersteller' erstellt")
        else:
            print("  [INFO] Index 'idx_ersatzteil_artikelnummer_hersteller' existiert bereits")
        
        conn.commit()
        conn.close()
        
        print()
        print("=" * 70)
        print("  [ERFOLG] Migration erfolgreich abgeschlossen!")
        print("=" * 70)
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

