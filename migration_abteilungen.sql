-- Migration: Abteilungssystem hinzufügen
-- Datum: 2025-11-03
-- 
-- Dieses Script erweitert die Datenbank um hierarchische Abteilungen
-- und verknüpft Mitarbeiter und Themen mit Abteilungen.

BEGIN TRANSACTION;

-- ========== 1. Tabelle: Abteilungen (hierarchisch) ==========

CREATE TABLE IF NOT EXISTS Abteilung (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Bezeichnung TEXT NOT NULL,
    ParentAbteilungID INTEGER NULL,  -- NULL = Hauptabteilung, sonst ID der übergeordneten Abteilung
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Sortierung INTEGER DEFAULT 0,
    FOREIGN KEY (ParentAbteilungID) REFERENCES Abteilung(ID)
);

-- Indices für Performance
CREATE INDEX IF NOT EXISTS idx_abteilung_parent ON Abteilung(ParentAbteilungID);
CREATE INDEX IF NOT EXISTS idx_abteilung_aktiv ON Abteilung(Aktiv);

-- ========== 2. Mitarbeiter-Tabelle erweitern ==========

-- Spalte für Primärabteilung hinzufügen (falls noch nicht vorhanden)
-- SQLite unterstützt nicht IF NOT EXISTS bei ALTER TABLE, daher prüfen wir manuell
-- Dies wird beim Import ignoriert, falls die Spalte bereits existiert

-- Prüfung erfolgt im Python-Script oder durch manuelles Ausführen
ALTER TABLE Mitarbeiter ADD COLUMN PrimaerAbteilungID INTEGER REFERENCES Abteilung(ID);

-- ========== 3. Tabelle: Zusätzliche Abteilungszuordnungen ==========

CREATE TABLE IF NOT EXISTS MitarbeiterAbteilung (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    MitarbeiterID INTEGER NOT NULL,
    AbteilungID INTEGER NOT NULL,
    FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
    FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
    UNIQUE(MitarbeiterID, AbteilungID)
);

-- Indices für Performance
CREATE INDEX IF NOT EXISTS idx_mitarbeiter_abteilung_ma ON MitarbeiterAbteilung(MitarbeiterID);
CREATE INDEX IF NOT EXISTS idx_mitarbeiter_abteilung_abt ON MitarbeiterAbteilung(AbteilungID);

-- ========== 4. SchichtbuchThema-Tabelle erweitern ==========

-- Spalte für Ersteller-Abteilung hinzufügen (falls noch nicht vorhanden)
ALTER TABLE SchichtbuchThema ADD COLUMN ErstellerAbteilungID INTEGER REFERENCES Abteilung(ID);

-- Index für Performance
CREATE INDEX IF NOT EXISTS idx_thema_abteilung ON SchichtbuchThema(ErstellerAbteilungID);

-- ========== 5. Standard-Abteilung anlegen ==========

-- Prüfen ob bereits Abteilungen existieren, wenn nicht Standard anlegen
INSERT OR IGNORE INTO Abteilung (ID, Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) 
VALUES (1, 'Standard', NULL, 1, 1);

COMMIT;

-- ========== Ende der Migration ==========
-- 
-- Nach erfolgreicher Migration stehen folgende Strukturen zur Verfügung:
-- 
-- 1. Tabelle "Abteilung" mit hierarchischer Struktur
-- 2. Spalte "PrimaerAbteilungID" in Tabelle "Mitarbeiter"
-- 3. Tabelle "MitarbeiterAbteilung" für zusätzliche Zuordnungen
-- 4. Spalte "ErstellerAbteilungID" in Tabelle "SchichtbuchThema"
-- 
-- Hinweis: Falls Fehlermeldungen über bereits existierende Spalten auftreten,
-- können diese ignoriert werden (Spalten existieren bereits).
