-- Migration 008: Entfernung der redundanten ErsatzteilThemaVerknuepfung-Tabelle
-- Datum: 2025-02-23
-- Beschreibung: Die Tabelle ErsatzteilThemaVerknuepfung ist redundant, da alle Informationen
--               bereits in der Lagerbuchung-Tabelle mit ThemaID vorhanden sind.
--               Alle Funktionen wurden auf Lagerbuchung WHERE ThemaID umgestellt.

BEGIN TRANSACTION;

-- ========== 1. Tabelle löschen ==========
-- Hinweis: Die Tabelle wird nur gelöscht, wenn sie existiert
-- Falls noch Daten vorhanden sind, werden diese gelöscht

DROP TABLE IF EXISTS ErsatzteilThemaVerknuepfung;

-- Indices werden automatisch mit der Tabelle gelöscht

COMMIT;

