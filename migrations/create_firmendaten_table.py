"""
Migration: Firmendaten-Tabelle erstellen
Erstellt Tabelle für Firmendaten (Logo, Adresse, etc.)
"""

import sqlite3
import os

DB_PATH = 'database_main.db'

def table_exists(conn, table_name):
    """Prüft, ob eine Tabelle existiert"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None

def migrate():
    """Erstellt die Firmendaten-Tabelle"""
    if not os.path.exists(DB_PATH):
        print(f"Fehler: Datenbank {DB_PATH} nicht gefunden!")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Firmendaten-Tabelle erstellen
        if not table_exists(conn, 'Firmendaten'):
            conn.execute('''
                CREATE TABLE Firmendaten (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Firmenname TEXT NOT NULL,
                    Strasse TEXT NULL,
                    PLZ TEXT NULL,
                    Ort TEXT NULL,
                    Telefon TEXT NULL,
                    Fax TEXT NULL,
                    Email TEXT NULL,
                    Website TEXT NULL,
                    Steuernummer TEXT NULL,
                    UStIdNr TEXT NULL,
                    Geschaeftsfuehrer TEXT NULL,
                    LogoPfad TEXT NULL,
                    BankName TEXT NULL,
                    IBAN TEXT NULL,
                    BIC TEXT NULL,
                    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
                    GeaendertAm DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Standard-Datensatz einfügen (leer)
            conn.execute('''
                INSERT INTO Firmendaten (Firmenname)
                VALUES ('Ihre Firma GmbH')
            ''')
            
            print("Firmendaten-Tabelle erfolgreich erstellt.")
        else:
            print("Firmendaten-Tabelle existiert bereits.")
        
        conn.commit()
        print("Migration erfolgreich abgeschlossen.")
        return True
        
    except Exception as e:
        print(f"Fehler beim Erstellen der Tabelle: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

