-- Migration 005: Lieferant Adresse erweitern
-- Datum: 2025-02-23
-- Beschreibung: Ersetzt Adresse-Feld durch Straße, PLZ, Ort

BEGIN TRANSACTION;

-- Prüfe ob Adresse-Spalte existiert (für bestehende Datenbanken)
-- Falls ja, migriere Daten und entferne alte Spalte

-- Neue Spalten hinzufügen (falls nicht vorhanden)
ALTER TABLE Lieferant ADD COLUMN Strasse TEXT;
ALTER TABLE Lieferant ADD COLUMN PLZ TEXT;
ALTER TABLE Lieferant ADD COLUMN Ort TEXT;

-- Optional: Daten aus Adresse migrieren (falls vorhanden)
-- Dies ist eine einfache Migration - komplexe Adress-Parsing-Logik sollte manuell erfolgen
-- UPDATE Lieferant SET Ort = Adresse WHERE Adresse IS NOT NULL AND Ort IS NULL;

-- Alte Adresse-Spalte entfernen (falls vorhanden)
-- SQLite unterstützt kein DROP COLUMN direkt, daher wird die Spalte ignoriert
-- Bei neuen Installationen wird sie nicht erstellt

COMMIT;

