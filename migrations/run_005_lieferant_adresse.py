"""
Migration 005: Lieferant Adresse erweitern
Ersetzt Adresse-Feld durch Straße, PLZ, Ort
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
        
        # Prüfe ob Adresse-Spalte existiert
        cursor.execute("PRAGMA table_info(Lieferant)")
        columns = [row[1] for row in cursor.fetchall()]
        
        has_adresse = 'Adresse' in columns
        has_strasse = 'Strasse' in columns
        has_plz = 'PLZ' in columns
        has_ort = 'Ort' in columns
        
        if has_strasse and has_plz and has_ort:
            print("Migration bereits durchgeführt - Felder existieren bereits.")
            conn.close()
            return True
        
        print("Starte Migration: Lieferant Adresse erweitern...")
        
        # Neue Spalten hinzufügen (falls nicht vorhanden)
        if not has_strasse:
            cursor.execute("ALTER TABLE Lieferant ADD COLUMN Strasse TEXT")
            print("  [OK] Spalte 'Strasse' hinzugefügt")
        
        if not has_plz:
            cursor.execute("ALTER TABLE Lieferant ADD COLUMN PLZ TEXT")
            print("  [OK] Spalte 'PLZ' hinzugefügt")
        
        if not has_ort:
            cursor.execute("ALTER TABLE Lieferant ADD COLUMN Ort TEXT")
            print("  [OK] Spalte 'Ort' hinzugefügt")
        
        # Optional: Daten aus Adresse migrieren (falls vorhanden)
        if has_adresse:
            print("  [INFO] Alte 'Adresse'-Spalte gefunden.")
            print("  [INFO] Bitte migrieren Sie die Daten manuell von 'Adresse' zu 'Strasse', 'PLZ', 'Ort'.")
            print("  [INFO] Die 'Adresse'-Spalte bleibt bestehen, wird aber nicht mehr verwendet.")
        
        conn.commit()
        conn.close()
        
        print()
        print("=" * 70)
        print("  [ERFOLG] Migration erfolgreich abgeschlossen!")
        print("=" * 70)
        print()
        
        if has_adresse:
            print("HINWEIS: Die alte 'Adresse'-Spalte existiert noch.")
            print("Sie können die Daten manuell migrieren oder die Spalte ignorieren.")
            print()
        
        return True
        
    except Exception as e:
        print(f"\n[FEHLER] Fehler bei der Migration: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

if __name__ == '__main__':
    run_migration()

