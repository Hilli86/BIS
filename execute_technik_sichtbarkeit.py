import sqlite3

DATABASE_FILE = 'database_main.db'

# Verbinde mit Datenbank
conn = sqlite3.connect(DATABASE_FILE)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Abteilung "Technik" hat die ID 3
technik_id = 3

# Zähle vorher
vorher = cursor.execute("""
    SELECT COUNT(*) as cnt 
    FROM ErsatzteilAbteilungZugriff 
    WHERE AbteilungID = ?
""", (technik_id,)).fetchone()

print(f"Vorher vorhandene Zugriffe für Technik: {vorher['cnt']}")

# SQL-Befehl ausführen
cursor.execute("""
    INSERT INTO ErsatzteilAbteilungZugriff (ErsatzteilID, AbteilungID)
    SELECT e.ID, ?
    FROM Ersatzteil e
    WHERE e.Gelöscht = 0
      AND NOT EXISTS (
          SELECT 1 FROM ErsatzteilAbteilungZugriff ez
          WHERE ez.ErsatzteilID = e.ID 
          AND ez.AbteilungID = ?
      )
""", (technik_id, technik_id))

conn.commit()
anzahl_hinzugefuegt = cursor.rowcount

# Zähle nachher
nachher = cursor.execute("""
    SELECT COUNT(*) as cnt 
    FROM ErsatzteilAbteilungZugriff 
    WHERE AbteilungID = ?
""", (technik_id,)).fetchone()

print(f"✓ Erfolgreich! {anzahl_hinzugefuegt} Zugriffe hinzugefügt.")
print(f"Gesamt Zugriffe für Technik jetzt: {nachher['cnt']}")

conn.close()

