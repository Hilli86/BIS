-- Migration: Benachrichtigungssystem Erweiterung
-- Datum: 2025-01-XX
-- Beschreibung: Erweitert das Benachrichtigungssystem um individuelle Einstellungen, Kanäle und Versand-Tracking

BEGIN;

-- Erweitere Benachrichtigungstabelle
ALTER TABLE Benachrichtigung ADD COLUMN Modul TEXT NULL;
ALTER TABLE Benachrichtigung ADD COLUMN Aktion TEXT NULL;
ALTER TABLE Benachrichtigung ADD COLUMN AbteilungID INTEGER NULL;
ALTER TABLE Benachrichtigung ADD COLUMN Zusatzdaten TEXT NULL;

-- Migration: Setze Modul und Aktion für bestehende Benachrichtigungen
UPDATE Benachrichtigung 
SET Modul = 'schichtbuch', 
    Aktion = Typ
WHERE Modul IS NULL AND Typ IN ('neues_thema', 'neue_bemerkung');

-- Erstelle neue Tabellen
CREATE TABLE IF NOT EXISTS BenachrichtigungEinstellung (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    MitarbeiterID INTEGER NOT NULL,
    Modul TEXT NOT NULL,
    Aktion TEXT NOT NULL,
    AbteilungID INTEGER NULL,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
    FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
    UNIQUE(MitarbeiterID, Modul, Aktion, AbteilungID)
);

CREATE TABLE IF NOT EXISTS BenachrichtigungKanal (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    MitarbeiterID INTEGER NOT NULL,
    KanalTyp TEXT NOT NULL,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Konfiguration TEXT NULL,
    FOREIGN KEY (MitarbeiterID) REFERENCES Mitarbeiter(ID) ON DELETE CASCADE,
    UNIQUE(MitarbeiterID, KanalTyp)
);

CREATE TABLE IF NOT EXISTS BenachrichtigungVersand (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    BenachrichtigungID INTEGER NOT NULL,
    KanalTyp TEXT NOT NULL,
    Status TEXT NOT NULL DEFAULT 'pending',
    VersandAm DATETIME NULL,
    Fehlermeldung TEXT NULL,
    FOREIGN KEY (BenachrichtigungID) REFERENCES Benachrichtigung(ID) ON DELETE CASCADE
);

-- Erstelle Indexes
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_modul ON Benachrichtigung(Modul);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_aktion ON Benachrichtigung(Aktion);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_abteilung ON Benachrichtigung(AbteilungID);

CREATE INDEX IF NOT EXISTS idx_benachrichtigung_einstellung_mitarbeiter ON BenachrichtigungEinstellung(MitarbeiterID);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_einstellung_modul ON BenachrichtigungEinstellung(Modul);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_einstellung_aktion ON BenachrichtigungEinstellung(Aktion);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_einstellung_abteilung ON BenachrichtigungEinstellung(AbteilungID);

CREATE INDEX IF NOT EXISTS idx_benachrichtigung_kanal_mitarbeiter ON BenachrichtigungKanal(MitarbeiterID);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_kanal_typ ON BenachrichtigungKanal(KanalTyp);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_kanal_aktiv ON BenachrichtigungKanal(Aktiv);

CREATE INDEX IF NOT EXISTS idx_benachrichtigung_versand_benachrichtigung ON BenachrichtigungVersand(BenachrichtigungID);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_versand_kanal ON BenachrichtigungVersand(KanalTyp);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_versand_status ON BenachrichtigungVersand(Status);
CREATE INDEX IF NOT EXISTS idx_benachrichtigung_versand_versand_am ON BenachrichtigungVersand(VersandAm);

-- Standard-Einstellungen: Alle Benachrichtigungen für alle bestehenden Benutzer aktivieren
-- (Wird automatisch durch die Logik gehandhabt - wenn keine Einstellung vorhanden, ist Benachrichtigung aktiv)

COMMIT;

