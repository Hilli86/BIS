"""
Script zum sicheren Ausführen der Abteilungs-Migration

Dieses Script prüft, welche Änderungen bereits vorhanden sind
und führt nur die noch fehlenden Migrationsschritte aus.
"""
import sqlite3
import sys

def column_exists(conn, table_name, column_name):
    """Prüft, ob eine Spalte in einer Tabelle existiert"""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def table_exists(conn, table_name):
    """Prüft, ob eine Tabelle existiert"""
    cursor = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    return cursor.fetchone() is not None

def index_exists(conn, index_name):
    """Prüft, ob ein Index existiert"""
    cursor = conn.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'")
    return cursor.fetchone() is not None

def run_migration():
    print("="*70)
    print("  ABTEILUNGS-MIGRATION für BIS")
    print("="*70)
    print()
    
    try:
        # Verbindung zur Datenbank
        conn = sqlite3.connect('database_main.db')
        conn.row_factory = sqlite3.Row
        
        print("[INFO] Verbindung zur Datenbank hergestellt")
        print()
        
        migration_steps = []
        
        # ========== 1. Tabelle Abteilung erstellen ==========
        if not table_exists(conn, 'Abteilung'):
            conn.execute('''
                CREATE TABLE Abteilung (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Bezeichnung TEXT NOT NULL,
                    ParentAbteilungID INTEGER NULL,
                    Aktiv INTEGER NOT NULL DEFAULT 1,
                    Sortierung INTEGER DEFAULT 0,
                    FOREIGN KEY (ParentAbteilungID) REFERENCES Abteilung(ID)
                )
            ''')
            migration_steps.append("[OK] Tabelle 'Abteilung' erstellt")
        else:
            migration_steps.append("[SKIP] Tabelle 'Abteilung' existiert bereits")
        
        # Indices für Abteilung
        if not index_exists(conn, 'idx_abteilung_parent'):
            conn.execute('CREATE INDEX idx_abteilung_parent ON Abteilung(ParentAbteilungID)')
            migration_steps.append("[OK] Index 'idx_abteilung_parent' erstellt")
        else:
            migration_steps.append("[SKIP] Index 'idx_abteilung_parent' existiert bereits")
            
        if not index_exists(conn, 'idx_abteilung_aktiv'):
            conn.execute('CREATE INDEX idx_abteilung_aktiv ON Abteilung(Aktiv)')
            migration_steps.append("[OK] Index 'idx_abteilung_aktiv' erstellt")
        else:
            migration_steps.append("[SKIP] Index 'idx_abteilung_aktiv' existiert bereits")
        
        # ========== 2. Spalte PrimaerAbteilungID zu Mitarbeiter hinzufügen ==========
        if not column_exists(conn, 'Mitarbeiter', 'PrimaerAbteilungID'):
            conn.execute('ALTER TABLE Mitarbeiter ADD COLUMN PrimaerAbteilungID INTEGER REFERENCES Abteilung(ID)')
            migration_steps.append("[OK] Spalte 'PrimaerAbteilungID' zu Mitarbeiter hinzugefuegt")
        else:
            migration_steps.append("[SKIP] Spalte 'PrimaerAbteilungID' existiert bereits")
        
        # ========== 3. Tabelle MitarbeiterAbteilung erstellen ==========
        if not table_exists(conn, 'MitarbeiterAbteilung'):
            conn.execute('''
                CREATE TABLE MitarbeiterAbteilung (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    MitarbeiterID INTEGER NOT NULL,
                    AbteilungID INTEGER NOT NULL,
                    FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
                    FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
                    UNIQUE(MitarbeiterID, AbteilungID)
                )
            ''')
            migration_steps.append("[OK] Tabelle 'MitarbeiterAbteilung' erstellt")
        else:
            migration_steps.append("[SKIP] Tabelle 'MitarbeiterAbteilung' existiert bereits")
        
        # Indices für MitarbeiterAbteilung
        if not index_exists(conn, 'idx_mitarbeiter_abteilung_ma'):
            conn.execute('CREATE INDEX idx_mitarbeiter_abteilung_ma ON MitarbeiterAbteilung(MitarbeiterID)')
            migration_steps.append("[OK] Index 'idx_mitarbeiter_abteilung_ma' erstellt")
        else:
            migration_steps.append("[SKIP] Index 'idx_mitarbeiter_abteilung_ma' existiert bereits")
            
        if not index_exists(conn, 'idx_mitarbeiter_abteilung_abt'):
            conn.execute('CREATE INDEX idx_mitarbeiter_abteilung_abt ON MitarbeiterAbteilung(AbteilungID)')
            migration_steps.append("[OK] Index 'idx_mitarbeiter_abteilung_abt' erstellt")
        else:
            migration_steps.append("[SKIP] Index 'idx_mitarbeiter_abteilung_abt' existiert bereits")
        
        # ========== 4. Spalte ErstellerAbteilungID zu SchichtbuchThema hinzufügen ==========
        if not column_exists(conn, 'SchichtbuchThema', 'ErstellerAbteilungID'):
            conn.execute('ALTER TABLE SchichtbuchThema ADD COLUMN ErstellerAbteilungID INTEGER REFERENCES Abteilung(ID)')
            migration_steps.append("[OK] Spalte 'ErstellerAbteilungID' zu SchichtbuchThema hinzugefuegt")
        else:
            migration_steps.append("[SKIP] Spalte 'ErstellerAbteilungID' existiert bereits")
        
        # Index für SchichtbuchThema
        if not index_exists(conn, 'idx_thema_abteilung'):
            conn.execute('CREATE INDEX idx_thema_abteilung ON SchichtbuchThema(ErstellerAbteilungID)')
            migration_steps.append("[OK] Index 'idx_thema_abteilung' erstellt")
        else:
            migration_steps.append("[SKIP] Index 'idx_thema_abteilung' existiert bereits")
        
        # ========== 5. Standard-Abteilung erstellen ==========
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM Abteilung")
        if cursor.fetchone()[0] == 0:
            conn.execute("INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) VALUES ('Standard', NULL, 1, 1)")
            migration_steps.append("[OK] Standard-Abteilung erstellt")
        else:
            migration_steps.append("[SKIP] Abteilungen bereits vorhanden")
        
        # Änderungen speichern
        conn.commit()
        
        # Ausgabe aller Schritte
        print("MIGRATIONS-SCHRITTE:")
        print("-" * 70)
        for step in migration_steps:
            print(step)
        
        print()
        print("="*70)
        print("  MIGRATION ERFOLGREICH ABGESCHLOSSEN!")
        print("="*70)
        print()
        
        # Statistik ausgeben
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM Abteilung")
        abt_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM Mitarbeiter WHERE PrimaerAbteilungID IS NOT NULL")
        ma_mit_abt = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM Mitarbeiter")
        ma_gesamt = cursor.fetchone()[0]
        
        print(f"Statistik:")
        print(f"  - {abt_count} Abteilung(en) in der Datenbank")
        print(f"  - {ma_mit_abt} von {ma_gesamt} Mitarbeitern haben eine Primaer-Abteilung")
        print()
        print("Naechste Schritte:")
        print("  1. Anwendung starten: python app.py")
        print("  2. Im Admin-Bereich Abteilungen anlegen")
        print("  3. Mitarbeitern Abteilungen zuweisen")
        print("  4. Optional: Testdaten laden mit 'testdaten_abteilungen.sql'")
        print()
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print()
        print("[FEHLER] Fehler bei der Migration:")
        print(f"  {e}")
        print()
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print()
        print("[FEHLER] Unerwarteter Fehler:")
        print(f"  {e}")
        print()
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)

