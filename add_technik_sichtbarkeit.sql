-- SQL-Befehl: Füge für alle Ersatzteile die Sichtbarkeit 'Technik' hinzu
-- Abteilung 'Technik' hat die ID: 3
-- (nur wenn noch nicht vorhanden - verhindert Duplikate)

INSERT INTO ErsatzteilAbteilungZugriff (ErsatzteilID, AbteilungID)
SELECT e.ID, 3
FROM Ersatzteil e
WHERE e.Gelöscht = 0
  AND NOT EXISTS (
      SELECT 1 FROM ErsatzteilAbteilungZugriff ez
      WHERE ez.ErsatzteilID = e.ID 
      AND ez.AbteilungID = 3
  );

-- Statistik nach Ausführung:
-- SELECT COUNT(*) FROM ErsatzteilAbteilungZugriff WHERE AbteilungID = 3;

