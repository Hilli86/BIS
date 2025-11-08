"""
Datenbank-Prüfung und automatische Migration
Prüft beim Start der App die Datenbank-Integrität und führt fehlende Migrations aus.
"""

import sqlite3
import os
import sys
import importlib.util
from pathlib import Path
from flask import current_app


def table_exists(conn, table_name):
    """Prüft, ob eine Tabelle existiert"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns


def get_required_tables():
    """Gibt eine Liste aller erforderlichen Tabellen zurück"""
    return [
        'Mitarbeiter',
        'Abteilung',
        'MitarbeiterAbteilung',
        'Bereich',
        'Gewerke',
        'Status',
        'Taetigkeit',
        'SchichtbuchThema',
        'SchichtbuchBemerkungen',
        'SchichtbuchThemaSichtbarkeit',
        'Benachrichtigung',
        'ErsatzteilKategorie',
        'Kostenstelle',
        'Lieferant',
        'Ersatzteil',
        'ErsatzteilBild',
        'ErsatzteilDokument',
        'Lagerbuchung',
        'ErsatzteilAbteilungZugriff'
    ]


def check_database_integrity(db_path):
    """
    Prüft die Datenbank-Integrität:
    - Existiert die Datenbank?
    - Sind alle erforderlichen Tabellen vorhanden?
    
    Returns:
        tuple: (is_valid, missing_tables, errors)
    """
    errors = []
    missing_tables = []
    
    # Prüfe ob Datenbank existiert
    if not os.path.exists(db_path):
        errors.append(f"Datenbank '{db_path}' existiert nicht!")
        return False, missing_tables, errors
    
    # Prüfe ob Datenbank nicht leer ist
    if os.path.getsize(db_path) == 0:
        errors.append(f"Datenbank '{db_path}' ist leer!")
        return False, missing_tables, errors
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Prüfe alle erforderlichen Tabellen
        required_tables = get_required_tables()
        for table in required_tables:
            if not table_exists(conn, table):
                missing_tables.append(table)
        
        conn.close()
        
        is_valid = len(missing_tables) == 0
        if not is_valid:
            errors.append(f"Fehlende Tabellen: {', '.join(missing_tables)}")
        
        return is_valid, missing_tables, errors
        
    except sqlite3.Error as e:
        errors.append(f"Datenbankfehler: {e}")
        return False, missing_tables, errors
    except Exception as e:
        errors.append(f"Unerwarteter Fehler: {e}")
        return False, missing_tables, errors


def create_migration_tracking_table(conn):
    """Erstellt die Migrations-Tracking-Tabelle falls nicht vorhanden"""
    if not table_exists(conn, 'SchemaMigration'):
        conn.execute('''
            CREATE TABLE SchemaMigration (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                MigrationName TEXT NOT NULL UNIQUE,
                ExecutedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                Success INTEGER NOT NULL DEFAULT 1
            )
        ''')
        conn.execute('CREATE INDEX idx_migration_name ON SchemaMigration(MigrationName)')
        conn.commit()


def migration_already_executed(conn, migration_name):
    """Prüft, ob eine Migration bereits ausgeführt wurde"""
    if not table_exists(conn, 'SchemaMigration'):
        return False
    
    cursor = conn.execute(
        "SELECT Success FROM SchemaMigration WHERE MigrationName = ?",
        (migration_name,)
    )
    result = cursor.fetchone()
    return result is not None and result[0] == 1


def mark_migration_executed(conn, migration_name, success=True):
    """Markiert eine Migration als ausgeführt"""
    create_migration_tracking_table(conn)
    
    # Prüfe ob bereits vorhanden
    cursor = conn.execute(
        "SELECT ID FROM SchemaMigration WHERE MigrationName = ?",
        (migration_name,)
    )
    existing = cursor.fetchone()
    
    if existing:
        # Update bestehenden Eintrag
        conn.execute(
            "UPDATE SchemaMigration SET ExecutedAt = CURRENT_TIMESTAMP, Success = ? WHERE MigrationName = ?",
            (1 if success else 0, migration_name)
        )
    else:
        # Neuen Eintrag erstellen
        conn.execute(
            "INSERT INTO SchemaMigration (MigrationName, Success) VALUES (?, ?)",
            (migration_name, 1 if success else 0)
        )
    conn.commit()


def find_migration_scripts():
    """Findet alle Migrations-Skripte im migrations-Ordner"""
    import os
    # Verwende absoluten Pfad relativ zum Projektverzeichnis
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migrations_dir = Path(project_root) / 'migrations'
    
    if not migrations_dir.exists():
        return []
    
    migration_scripts = []
    
    # Suche nach Python-Migrations-Skripten (run_*.py)
    for script_file in migrations_dir.glob('run_*.py'):
        migration_scripts.append({
            'name': script_file.stem,
            'path': str(script_file),
            'type': 'python'
        })
    
    # Sortiere nach Namen (für konsistente Reihenfolge)
    migration_scripts.sort(key=lambda x: x['name'])
    
    return migration_scripts


def execute_migration_script(script_path, script_name, db_path):
    """Führt ein Migrations-Skript aus"""
    try:
        # Lade das Modul dynamisch
        spec = importlib.util.spec_from_file_location(script_name, script_path)
        if spec is None or spec.loader is None:
            return False, f"Konnte Modul nicht laden: {script_name}"
        
        module = importlib.util.module_from_spec(spec)
        
        spec.loader.exec_module(module)
        
        # Führe die Migration aus - suche nach verschiedenen möglichen Funktionsnamen
        migration_function = None
        if hasattr(module, 'run_migration'):
            migration_function = module.run_migration
        elif hasattr(module, f'run_{script_name.replace("run_", "")}'):
            # Versuche Funktionsname basierend auf Skriptnamen (z.B. run_benachrichtigungen_migration)
            func_name = f'run_{script_name.replace("run_", "")}'
            migration_function = getattr(module, func_name)
        elif hasattr(module, 'main'):
            migration_function = module.main
        
        if migration_function:
            # Für Skripte die den DB-Pfad direkt verwenden (z.B. 'database_main.db'),
            # müssen wir sicherstellen, dass sie im Projekt-Root ausgeführt werden
            import os
            original_cwd = os.getcwd()
            try:
                # Wechsle ins Projekt-Root-Verzeichnis, damit relative Pfade wie
                # 'database_main.db' funktionieren
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                os.chdir(project_root)
                
                # Setze DB_PATH als Umgebungsvariable für Skripte die os.environ verwenden
                os.environ['DATABASE_URL'] = os.path.abspath(db_path)
                
                # Wenn das Skript DB_PATH verwendet, setze es auf absoluten Pfad
                if hasattr(module, 'DB_PATH'):
                    module.DB_PATH = os.path.abspath(db_path)
                
                success = migration_function()
                return success, None if success else "Migration fehlgeschlagen"
            finally:
                os.chdir(original_cwd)
        else:
            return False, f"Keine Migration-Funktion gefunden in {script_name} (erwartet: run_migration, run_{script_name.replace('run_', '')}, oder main)"
            
    except Exception as e:
        import traceback
        return False, f"Fehler beim Ausführen der Migration: {e}\n{traceback.format_exc()}"


def run_pending_migrations(db_path, verbose=True):
    """
    Führt alle noch nicht ausgeführten Migrations aus.
    
    Returns:
        tuple: (success, executed_migrations, errors)
    """
    executed_migrations = []
    errors = []
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Stelle sicher, dass Tracking-Tabelle existiert
        create_migration_tracking_table(conn)
        
        # Finde alle Migrations-Skripte
        migration_scripts = find_migration_scripts()
        
        if verbose:
            print(f"[INFO] Gefunden: {len(migration_scripts)} Migrations-Skript(e)")
        
        for script_info in migration_scripts:
            script_name = script_info['name']
            script_path = script_info['path']
            
            # Prüfe ob Migration bereits ausgeführt wurde
            if migration_already_executed(conn, script_name):
                if verbose:
                    print(f"[SKIP] Migration '{script_name}' bereits ausgeführt")
                continue
            
            if verbose:
                print(f"[INFO] Führe Migration aus: {script_name}...")
            
            # Führe Migration aus
            success, error_msg = execute_migration_script(script_path, script_name, db_path)
            
            if success:
                mark_migration_executed(conn, script_name, success=True)
                executed_migrations.append(script_name)
                if verbose:
                    print(f"[OK] Migration '{script_name}' erfolgreich ausgeführt")
            else:
                mark_migration_executed(conn, script_name, success=False)
                error = f"Migration '{script_name}' fehlgeschlagen: {error_msg}"
                errors.append(error)
                if verbose:
                    print(f"[FEHLER] {error}")
        
        conn.close()
        
        return len(errors) == 0, executed_migrations, errors
        
    except Exception as e:
        errors.append(f"Fehler beim Ausführen der Migrations: {e}")
        return False, executed_migrations, errors


def initialize_database_on_startup(app):
    """
    Hauptfunktion: Prüft und initialisiert die Datenbank beim App-Start.
    Sollte in app.py beim Start aufgerufen werden.
    """
    db_path = app.config['DATABASE_URL']
    
    print("=" * 70)
    print("  BIS - Datenbank-Prüfung")
    print("=" * 70)
    print()
    
    # 1. Prüfe Datenbank-Integrität
    print("[1/2] Prüfe Datenbank-Integrität...")
    is_valid, missing_tables, errors = check_database_integrity(db_path)
    
    if not is_valid:
        if not os.path.exists(db_path):
            print(f"[FEHLER] Datenbank '{db_path}' existiert nicht!")
            print("[INFO] Bitte führen Sie 'python init_database.py' aus, um die Datenbank zu erstellen.")
            print()
            sys.exit(1)
        
        if missing_tables:
            print(f"[WARNUNG] Fehlende Tabellen: {', '.join(missing_tables)}")
            print("[INFO] Versuche Migrations auszuführen...")
            print()
        else:
            for error in errors:
                print(f"[FEHLER] {error}")
            print()
            sys.exit(1)
    else:
        print("[OK] Datenbank-Integrität OK")
    
    # 2. Führe ausstehende Migrations aus
    print()
    print("[2/2] Prüfe auf ausstehende Migrations...")
    success, executed, migration_errors = run_pending_migrations(db_path, verbose=True)
    
    if executed:
        print(f"[OK] {len(executed)} Migration(s) ausgeführt: {', '.join(executed)}")
    
    if migration_errors:
        print()
        print("[FEHLER] Fehler bei Migrations:")
        for error in migration_errors:
            print(f"  - {error}")
        print()
        # Im Produktionsbetrieb könnte man hier entscheiden, ob die App starten soll
        # oder nicht. Für jetzt: Warnung, aber App startet trotzdem.
        print("[WARNUNG] App startet trotz Migrations-Fehlern!")
    
    print()
    print("=" * 70)
    print("  Datenbank-Prüfung abgeschlossen")
    print("=" * 70)
    print()
    
    return success and is_valid

