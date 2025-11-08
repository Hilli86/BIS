-- Migration 006: Lagerort und Lagerplatz als separate Tabellen
-- Datum: 2025-02-23
-- Beschreibung: Ersetzt Lagerort TEXT durch LagerortID und LagerplatzID (Foreign Keys)

BEGIN TRANSACTION;

-- ========== 1. Tabelle: Lagerort ==========
CREATE TABLE IF NOT EXISTS Lagerort (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Bezeichnung TEXT NOT NULL,
    Beschreibung TEXT,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Sortierung INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_lagerort_aktiv ON Lagerort(Aktiv);
CREATE INDEX IF NOT EXISTS idx_lagerort_sortierung ON Lagerort(Sortierung);

-- ========== 2. Tabelle: Lagerplatz ==========
CREATE TABLE IF NOT EXISTS Lagerplatz (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Bezeichnung TEXT NOT NULL,
    Beschreibung TEXT,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Sortierung INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_lagerplatz_aktiv ON Lagerplatz(Aktiv);
CREATE INDEX IF NOT EXISTS idx_lagerplatz_sortierung ON Lagerplatz(Sortierung);

-- ========== 3. Ersatzteil-Tabelle erweitern ==========
-- Neue Spalten hinzufügen
ALTER TABLE Ersatzteil ADD COLUMN LagerortID INTEGER;
ALTER TABLE Ersatzteil ADD COLUMN LagerplatzID INTEGER;

-- Foreign Keys hinzufügen
-- SQLite unterstützt kein ALTER TABLE ADD FOREIGN KEY, daher werden die Constraints
-- nur bei neuen Installationen erstellt. Für bestehende Datenbanken werden die
-- Spalten ohne Foreign Key Constraints hinzugefügt.

-- Index für bessere Performance
CREATE INDEX IF NOT EXISTS idx_ersatzteil_lagerort ON Ersatzteil(LagerortID);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_lagerplatz ON Ersatzteil(LagerplatzID);

-- Optional: Daten migrieren (falls Lagerort TEXT bereits Daten enthält)
-- Dies sollte manuell erfolgen, da eine automatische Zuordnung nicht möglich ist

COMMIT;

