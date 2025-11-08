-- Migration 003: Benachrichtigungssystem
-- Datum: 2025-02-23
-- Beschreibung: Ermöglicht Benachrichtigungen für Benutzer bei neuen Bemerkungen zu ihren Themen

-- Neue Tabelle für Benachrichtigungen
CREATE TABLE IF NOT EXISTS Benachrichtigung (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    MitarbeiterID INTEGER NOT NULL,
    ThemaID INTEGER NOT NULL,
    BemerkungID INTEGER,
    Typ TEXT NOT NULL DEFAULT 'neue_bemerkung',  -- 'neue_bemerkung', 'neues_thema', 'status_geaendert'
    Titel TEXT NOT NULL,
    Nachricht TEXT,
    Gelesen INTEGER NOT NULL DEFAULT 0,
    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
    FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
    FOREIGN KEY (BemerkungID) REFERENCES SchichtbuchBemerkungen(ID) ON DELETE CASCADE
);

-- Indices für Performance
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_mitarbeiter ON Benachrichtigung(MitarbeiterID);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_gelesen ON Benachrichtigung(Gelesen);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_thema ON Benachrichtigung(ThemaID);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_erstellt ON Benachrichtigung(ErstelltAm);

