"""
Migration: Berechtigungssystem
Erstellt Tabellen für Berechtigungen und verknüpft diese mit Mitarbeitern
"""

import sqlite3
import sys
import os

# Pfad zum Projektverzeichnis hinzufügen
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def run_migration(conn):
    """Führt die Migration aus"""
    cursor = conn.cursor()
    
    print("Starte Migration: Berechtigungssystem...")
    
    # 1. Tabelle Berechtigung erstellen
    print("  - Erstelle Tabelle 'Berechtigung'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Berechtigung (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Schluessel TEXT NOT NULL UNIQUE,
            Bezeichnung TEXT NOT NULL,
            Beschreibung TEXT,
            Aktiv INTEGER NOT NULL DEFAULT 1
        )
    ''')
    
    # Index für Schluessel
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_berechtigung_schluessel 
        ON Berechtigung(Schluessel)
    ''')
    
    # Index für Aktiv
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_berechtigung_aktiv 
        ON Berechtigung(Aktiv)
    ''')
    
    # 2. Tabelle MitarbeiterBerechtigung erstellen
    print("  - Erstelle Tabelle 'MitarbeiterBerechtigung'...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS MitarbeiterBerechtigung (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            MitarbeiterID INTEGER NOT NULL,
            BerechtigungID INTEGER NOT NULL,
            FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
            FOREIGN KEY (BerechtigungID) REFERENCES Berechtigung(ID) ON DELETE CASCADE,
            UNIQUE(MitarbeiterID, BerechtigungID)
        )
    ''')
    
    # Indizes für MitarbeiterBerechtigung
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_mitarbeiter_berechtigung_ma 
        ON MitarbeiterBerechtigung(MitarbeiterID)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_mitarbeiter_berechtigung_ber 
        ON MitarbeiterBerechtigung(BerechtigungID)
    ''')
    
    # 3. Standard-Berechtigungen einfügen
    print("  - Füge Standard-Berechtigungen ein...")
    
    berechtigungen = [
        ('admin', 'Admin', 'Vollzugriff auf alle Admin-Funktionen'),
        ('artikel_buchen', 'Darf Artikel buchen', 'Erlaubt Lagerbuchungen von Ersatzteilen'),
        ('bestellungen_erstellen', 'Darf Bestellungen erstellen', 'Erlaubt das Erstellen von Bestellungen/Angebotsanfragen'),
        ('bestellungen_freigeben', 'Darf Bestellungen freigeben', 'Erlaubt die Freigabe von Bestellungen')
    ]
    
    for schluessel, bezeichnung, beschreibung in berechtigungen:
        cursor.execute('''
            INSERT OR IGNORE INTO Berechtigung (Schluessel, Bezeichnung, Beschreibung, Aktiv)
            VALUES (?, ?, ?, 1)
        ''', (schluessel, bezeichnung, beschreibung))
        print(f"    - {bezeichnung} ({schluessel})")
    
    # 4. BIS-Admin Mitarbeitern automatisch Admin-Berechtigung geben
    print("  - Gebe BIS-Admin Mitarbeitern Admin-Berechtigung...")
    
    # Hole Admin-Berechtigung ID
    admin_berechtigung = cursor.execute(
        "SELECT ID FROM Berechtigung WHERE Schluessel = 'admin'"
    ).fetchone()
    
    if admin_berechtigung:
        admin_ber_id = admin_berechtigung[0]
        
        # Hole alle Mitarbeiter in BIS-Admin Abteilung
        bis_admin_abteilung = cursor.execute(
            "SELECT ID FROM Abteilung WHERE Bezeichnung = 'BIS-Admin'"
        ).fetchone()
        
        if bis_admin_abteilung:
            bis_admin_abt_id = bis_admin_abteilung[0]
            
            # Primärabteilung BIS-Admin
            mitarbeiter = cursor.execute('''
                SELECT ID, Vorname, Nachname FROM Mitarbeiter 
                WHERE PrimaerAbteilungID = ?
            ''', (bis_admin_abt_id,)).fetchall()
            
            for ma in mitarbeiter:
                cursor.execute('''
                    INSERT OR IGNORE INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID)
                    VALUES (?, ?)
                ''', (ma[0], admin_ber_id))
                print(f"    - {ma[1]} {ma[2]} (ID: {ma[0]})")
            
            # Zusätzliche Abteilung BIS-Admin
            mitarbeiter_zusatz = cursor.execute('''
                SELECT DISTINCT m.ID, m.Vorname, m.Nachname 
                FROM Mitarbeiter m
                JOIN MitarbeiterAbteilung ma ON m.ID = ma.MitarbeiterID
                WHERE ma.AbteilungID = ?
            ''', (bis_admin_abt_id,)).fetchall()
            
            for ma in mitarbeiter_zusatz:
                cursor.execute('''
                    INSERT OR IGNORE INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID)
                    VALUES (?, ?)
                ''', (ma[0], admin_ber_id))
                print(f"    - {ma[1]} {ma[2]} (ID: {ma[0]}) [Zusatzabteilung]")
    
    conn.commit()
    print("Migration erfolgreich abgeschlossen!")
    return True


if __name__ == '__main__':
    # Datenbankpfad
    db_path = os.path.join(os.path.dirname(__file__), '..', 'database_main.db')
    
    if not os.path.exists(db_path):
        print(f"Fehler: Datenbank nicht gefunden: {db_path}")
        sys.exit(1)
    
    try:
        conn = sqlite3.connect(db_path)
        success = run_migration(conn)
        conn.close()
        
        if success:
            print("\n✓ Migration erfolgreich durchgeführt!")
            sys.exit(0)
        else:
            print("\n✗ Migration fehlgeschlagen!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ Fehler bei der Migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

