"""
Migration 009: Preis und Währung in Lagerbuchung speichern
Speichert den aktuellen Artikelpreis und die Währung zum Zeitpunkt der Buchung
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
        print("  Migration 009: Preis und Währung in Lagerbuchung")
        print("=" * 70)
        print()
        
        # 1. Preis hinzufügen
        if not column_exists(cursor, 'Lagerbuchung', 'Preis'):
            cursor.execute('ALTER TABLE Lagerbuchung ADD COLUMN Preis REAL NULL')
            print("  [OK] Spalte 'Preis' zu Lagerbuchung hinzugefügt")
        else:
            print("  [INFO] Spalte 'Preis' existiert bereits")
        
        # 2. Währung hinzufügen
        if not column_exists(cursor, 'Lagerbuchung', 'Waehrung'):
            cursor.execute('ALTER TABLE Lagerbuchung ADD COLUMN Waehrung TEXT NULL')
            print("  [OK] Spalte 'Waehrung' zu Lagerbuchung hinzugefügt")
        else:
            print("  [INFO] Spalte 'Waehrung' existiert bereits")
        
        # Optional: Bestehende Buchungen mit aktuellen Preisen aktualisieren
        print()
        print("  [INFO] Aktualisiere bestehende Buchungen mit aktuellen Preisen...")
        cursor.execute('''
            UPDATE Lagerbuchung
            SET Preis = (
                SELECT e.Preis FROM Ersatzteil e WHERE e.ID = Lagerbuchung.ErsatzteilID
            ),
            Waehrung = (
                SELECT e.Waehrung FROM Ersatzteil e WHERE e.ID = Lagerbuchung.ErsatzteilID
            )
            WHERE Preis IS NULL OR Waehrung IS NULL
        ''')
        updated_count = cursor.rowcount
        print(f"  [OK] {updated_count} bestehende Buchungen aktualisiert")
        
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

