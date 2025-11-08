-- Migration 009: Preis und Währung in Lagerbuchung speichern
-- Datum: 2025-02-23
-- Beschreibung: Speichert den aktuellen Artikelpreis und die Währung zum Zeitpunkt der Buchung

BEGIN TRANSACTION;

-- ========== 1. Preis hinzufügen ==========
ALTER TABLE Lagerbuchung ADD COLUMN Preis REAL NULL;

-- ========== 2. Währung hinzufügen ==========
ALTER TABLE Lagerbuchung ADD COLUMN Waehrung TEXT NULL;

-- Indices sind nicht nötig für diese Felder

COMMIT;

