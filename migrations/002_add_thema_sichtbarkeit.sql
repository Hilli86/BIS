-- Migration 002: Sichtbarkeitsverwaltung für Schichtbuch-Themen
-- Datum: 2025-11-05
-- Beschreibung: Ermöglicht feingranulare Kontrolle darüber, welche Abteilungen ein Thema sehen können

-- Neue Tabelle für Thema-Sichtbarkeit
CREATE TABLE IF NOT EXISTS SchichtbuchThemaSichtbarkeit (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ThemaID INTEGER NOT NULL,
    AbteilungID INTEGER NOT NULL,
    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
    FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
    UNIQUE(ThemaID, AbteilungID)
);

-- Index für schnellere Abfragen
CREATE INDEX IF NOT EXISTS idx_sichtbarkeit_thema ON SchichtbuchThemaSichtbarkeit(ThemaID);
CREATE INDEX IF NOT EXISTS idx_sichtbarkeit_abteilung ON SchichtbuchThemaSichtbarkeit(AbteilungID);

-- Bestehende Themen mit Sichtbarkeit für ihre Ersteller-Abteilung versehen
INSERT INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
SELECT ID, ErstellerAbteilungID
FROM SchichtbuchThema
WHERE ErstellerAbteilungID IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM SchichtbuchThemaSichtbarkeit 
    WHERE ThemaID = SchichtbuchThema.ID 
    AND AbteilungID = SchichtbuchThema.ErstellerAbteilungID
);

