-- Migration 007: Erweiterung Ersatzteil-Tabelle
-- Datum: 2025-02-23
-- Beschreibung: Hinzufügen von EndOfLife, NachfolgeartikelID, Kennzeichen und ArtikelnummerHersteller

BEGIN TRANSACTION;

-- ========== 1. EndOfLife (Boolean) ==========
ALTER TABLE Ersatzteil ADD COLUMN EndOfLife INTEGER NOT NULL DEFAULT 0;

-- ========== 2. NachfolgeartikelID (Foreign Key zu Ersatzteil.ID) ==========
ALTER TABLE Ersatzteil ADD COLUMN NachfolgeartikelID INTEGER NULL;
CREATE INDEX IF NOT EXISTS idx_ersatzteil_nachfolgeartikel ON Ersatzteil(NachfolgeartikelID);

-- ========== 3. Kennzeichen (A-Z, ein Zeichen) ==========
ALTER TABLE Ersatzteil ADD COLUMN Kennzeichen TEXT NULL;
CREATE INDEX IF NOT EXISTS idx_ersatzteil_kennzeichen ON Ersatzteil(Kennzeichen);

-- ========== 4. ArtikelnummerHersteller (Text) ==========
ALTER TABLE Ersatzteil ADD COLUMN ArtikelnummerHersteller TEXT NULL;
CREATE INDEX IF NOT EXISTS idx_ersatzteil_artikelnummer_hersteller ON Ersatzteil(ArtikelnummerHersteller);

-- Foreign Key Constraint für NachfolgeartikelID hinzufügen
-- SQLite unterstützt keine ALTER TABLE für Foreign Keys, daher wird dies beim INSERT/UPDATE geprüft

COMMIT;

