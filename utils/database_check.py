"""
Datenbank-Prüfung und Initialisierung beim App-Start
Prüft beim Start der App die Datenbank-Integrität und initialisiert fehlende Strukturen.
"""

import os
import sys

from .database_check_helpers import check_database_integrity
from .database_schema_init import init_database_schema

def initialize_database_on_startup(app):
    """
    Hauptfunktion: Prüft die Datenbank-Integrität beim App-Start und initialisiert fehlende Strukturen.
    Sollte in app.py beim Start aufgerufen werden.
    """
    db_path = app.config['DATABASE_URL']
    
    print("=" * 70)
    print("  BIS - Datenbank-Prüfung und Initialisierung")
    print("=" * 70)
    print()
    
    # Erstelle Datenbank falls nicht vorhanden
    if not os.path.exists(db_path):
        print(f"[INFO] Datenbank '{db_path}' existiert nicht, erstelle sie...")
        init_database_schema(db_path, verbose=False)
        print("[OK] Datenbank erstellt und initialisiert")
        print()
    
    # Prüfe Datenbank-Integrität
    print("[INFO] Prüfe Datenbank-Integrität...")
    is_valid, missing_tables, errors = check_database_integrity(db_path)
    
    if not is_valid:
        if missing_tables:
            print(f"[INFO] Fehlende Tabellen gefunden: {', '.join(missing_tables)}")
            print("[INFO] Initialisiere fehlende Strukturen...")
            init_database_schema(db_path, verbose=False)
            print("[OK] Datenbankstruktur aktualisiert")
        else:
            for error in errors:
                print(f"[FEHLER] {error}")
            print()
            sys.exit(1)
    else:
        print("[OK] Datenbank-Integrität OK")
        # Auch wenn alle Tabellen vorhanden sind, prüfe auf fehlende Spalten
        print("[INFO] Prüfe auf fehlende Spalten und Indexes...")
        init_database_schema(db_path, verbose=False)
        print("[OK] Spaltenprüfung abgeschlossen")
    
    print()
    print("=" * 70)
    print("  Datenbank-Prüfung abgeschlossen")
    print("=" * 70)
    print()
    
    return True

