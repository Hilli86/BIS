-- Testdaten für Abteilungssystem
-- Datum: 2025-11-03

BEGIN;

-- ========== Abteilungen anlegen (hierarchisch) ==========

-- Hauptabteilungen
INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) 
VALUES 
    ('Produktion', NULL, 1, 10),
    ('Verwaltung', NULL, 1, 20),
    ('Technik', NULL, 1, 30);

-- Unterabteilungen der Produktion
INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) 
VALUES 
    ('Montage', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Produktion'), 1, 11),
    ('Qualitätskontrolle', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Produktion'), 1, 12),
    ('Lager', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Produktion'), 1, 13);

-- Unterabteilungen der Verwaltung
INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) 
VALUES 
    ('Buchhaltung', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Verwaltung'), 1, 21),
    ('Personalwesen', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Verwaltung'), 1, 22);

-- Unterabteilungen der Technik
INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) 
VALUES 
    ('Elektrik', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Technik'), 1, 31),
    ('Mechanik', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Technik'), 1, 32),
    ('IT', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Technik'), 1, 33);

-- Noch eine Ebene tiefer (Sub-Unterabteilung)
INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) 
VALUES 
    ('Netzwerk', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'IT'), 1, 331),
    ('Software', (SELECT ID FROM Abteilung WHERE Bezeichnung = 'IT'), 1, 332);

-- ========== Mitarbeiter mit Abteilungen ==========

-- Mitarbeiter anlegen (falls noch nicht vorhanden)
-- Admin/Manager (Produktion - Hauptabteilung)
INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
VALUES (
    '1001',
    'Max',
    'Mustermann',
    1,
    'scrypt:32768:8:1$BVZ5rGz6FP7xHG2w$c8b5e5c0d9e4f3b2a1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1',  -- Passwort: test123
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Produktion')
);

-- Montage-Mitarbeiter
INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
VALUES (
    '1002',
    'Anna',
    'Schmidt',
    1,
    'scrypt:32768:8:1$BVZ5rGz6FP7xHG2w$c8b5e5c0d9e4f3b2a1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1',
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Montage')
);

-- QK-Mitarbeiter
INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
VALUES (
    '1003',
    'Thomas',
    'Weber',
    1,
    'scrypt:32768:8:1$BVZ5rGz6FP7xHG2w$c8b5e5c0d9e4f3b2a1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1',
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Qualitätskontrolle')
);

-- Technik-Mitarbeiter (Elektrik)
INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
VALUES (
    '2001',
    'Sabine',
    'Müller',
    1,
    'scrypt:32768:8:1$BVZ5rGz6FP7xHG2w$c8b5e5c0d9e4f3b2a1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1',
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Elektrik')
);

-- IT-Mitarbeiter (Netzwerk)
INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
VALUES (
    '2002',
    'Michael',
    'Fischer',
    1,
    'scrypt:32768:8:1$BVZ5rGz6FP7xHG2w$c8b5e5c0d9e4f3b2a1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1',
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Netzwerk')
);

-- Verwaltungs-Mitarbeiter
INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
VALUES (
    '3001',
    'Julia',
    'Becker',
    1,
    'scrypt:32768:8:1$BVZ5rGz6FP7xHG2w$c8b5e5c0d9e4f3b2a1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1',
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Buchhaltung')
);

-- ========== Zusätzliche Abteilungszuordnungen ==========

-- Max Mustermann (Produktionsleiter) hat auch Zugriff auf Technik
INSERT OR IGNORE INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID)
VALUES (
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '1001'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Technik')
);

-- Anna Schmidt (Montage) hilft auch im Lager aus
INSERT OR IGNORE INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID)
VALUES (
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '1002'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Lager')
);

-- Michael Fischer (IT-Netzwerk) hat auch Zugriff auf Software
INSERT OR IGNORE INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID)
VALUES (
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '2002'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Software')
);

-- ========== Themen mit Abteilungszuordnung erstellen ==========

-- Prüfen ob nötige Stammdaten vorhanden sind
-- Falls nicht, diese anlegen

-- Beispiel-Bereich und Gewerk (falls nicht vorhanden)
INSERT OR IGNORE INTO Bereich (Bezeichnung, Aktiv) VALUES ('Fertigung', 1);
INSERT OR IGNORE INTO Bereich (Bezeichnung, Aktiv) VALUES ('Infrastruktur', 1);

INSERT OR IGNORE INTO Gewerke (Bezeichnung, BereichID, Aktiv) 
VALUES (
    'Maschinen',
    (SELECT ID FROM Bereich WHERE Bezeichnung = 'Fertigung'),
    1
);

INSERT OR IGNORE INTO Gewerke (Bezeichnung, BereichID, Aktiv) 
VALUES (
    'Elektroinstallation',
    (SELECT ID FROM Bereich WHERE Bezeichnung = 'Infrastruktur'),
    1
);

INSERT OR IGNORE INTO Gewerke (Bezeichnung, BereichID, Aktiv) 
VALUES (
    'Netzwerktechnik',
    (SELECT ID FROM Bereich WHERE Bezeichnung = 'Infrastruktur'),
    1
);

-- Beispiel-Status (falls nicht vorhanden)
INSERT OR IGNORE INTO Status (Bezeichnung, Farbe, Sortierung, Aktiv) 
VALUES ('Offen', '#dc3545', 10, 1);

INSERT OR IGNORE INTO Status (Bezeichnung, Farbe, Sortierung, Aktiv) 
VALUES ('In Bearbeitung', '#ffc107', 20, 1);

INSERT OR IGNORE INTO Status (Bezeichnung, Farbe, Sortierung, Aktiv) 
VALUES ('Erledigt', '#28a745', 30, 1);

-- Beispiel-Tätigkeiten (falls nicht vorhanden)
INSERT OR IGNORE INTO Taetigkeit (Bezeichnung, Sortierung, Aktiv) 
VALUES ('Problem gemeldet', 10, 1);

INSERT OR IGNORE INTO Taetigkeit (Bezeichnung, Sortierung, Aktiv) 
VALUES ('Reparatur', 20, 1);

INSERT OR IGNORE INTO Taetigkeit (Bezeichnung, Sortierung, Aktiv) 
VALUES ('Kontrolle', 30, 1);

-- ========== Themen erstellen ==========

-- Thema 1: Montage-Thema (Anna Schmidt)
INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht)
VALUES (
    (SELECT ID FROM Gewerke WHERE Bezeichnung = 'Maschinen'),
    (SELECT ID FROM Status WHERE Bezeichnung = 'Offen'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Montage'),
    0
);

INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT last_insert_rowid()),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '1002'),
    datetime('now', '-2 days'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Problem gemeldet'),
    'Maschine 5 macht ungewöhnliche Geräusche. Vibrationen bei hoher Drehzahl.',
    0
);

-- Thema 2: QK-Thema (Thomas Weber)
INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht)
VALUES (
    (SELECT ID FROM Gewerke WHERE Bezeichnung = 'Maschinen'),
    (SELECT ID FROM Status WHERE Bezeichnung = 'In Bearbeitung'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Qualitätskontrolle'),
    0
);

INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT last_insert_rowid()),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '1003'),
    datetime('now', '-1 day'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Kontrolle'),
    'Qualitätsprüfung Charge 2345: 3 Teile außerhalb der Toleranz. Nacharbeit erforderlich.',
    0
);

-- Thema 3: Elektrik-Thema (Sabine Müller)
INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht)
VALUES (
    (SELECT ID FROM Gewerke WHERE Bezeichnung = 'Elektroinstallation'),
    (SELECT ID FROM Status WHERE Bezeichnung = 'Offen'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Elektrik'),
    0
);

INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT last_insert_rowid()),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '2001'),
    datetime('now', '-3 hours'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Problem gemeldet'),
    'Sicherung in Halle 2 löst wiederholt aus. Ursache noch unklar.',
    0
);

-- Thema 4: IT-Netzwerk-Thema (Michael Fischer)
INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht)
VALUES (
    (SELECT ID FROM Gewerke WHERE Bezeichnung = 'Netzwerktechnik'),
    (SELECT ID FROM Status WHERE Bezeichnung = 'Erledigt'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Netzwerk'),
    0
);

INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT last_insert_rowid()),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '2002'),
    datetime('now', '-1 day'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Problem gemeldet'),
    'Switch in Raum B12 offline. Keine Netzwerkverbindung.',
    0
);

-- Antwort auf Thema 4
INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT ID FROM SchichtbuchThema ORDER BY ID DESC LIMIT 1),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '2002'),
    datetime('now', '-2 hours'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Reparatur'),
    'Switch ausgetauscht. Netzwerk wieder erreichbar. Problem gelöst.',
    0
);

-- Thema 5: Produktions-Hauptabteilung (Max Mustermann)
INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht)
VALUES (
    (SELECT ID FROM Gewerke WHERE Bezeichnung = 'Maschinen'),
    (SELECT ID FROM Status WHERE Bezeichnung = 'In Bearbeitung'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Produktion'),
    0
);

INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT last_insert_rowid()),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '1001'),
    datetime('now', '-5 hours'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Problem gemeldet'),
    'Produktionsplanung für nächste Woche: Kapazitätsengpass bei Maschine 3 und 7.',
    0
);

-- Thema 6: Verwaltung (Julia Becker)
INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht)
VALUES (
    (SELECT ID FROM Gewerke WHERE Bezeichnung = 'Maschinen'),
    (SELECT ID FROM Status WHERE Bezeichnung = 'Offen'),
    (SELECT ID FROM Abteilung WHERE Bezeichnung = 'Buchhaltung'),
    0
);

INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
VALUES (
    (SELECT last_insert_rowid()),
    (SELECT ID FROM Mitarbeiter WHERE Personalnummer = '3001'),
    datetime('now', '-6 hours'),
    (SELECT ID FROM Taetigkeit WHERE Bezeichnung = 'Problem gemeldet'),
    'Wartungskosten für Q4 überprüfen - Budget überschritten.',
    0
);

COMMIT;

-- ========== Zusammenfassung ==========
-- Abteilungs-Hierarchie:
-- 
-- Produktion
--   ├── Montage (Anna Schmidt)
--   ├── Qualitätskontrolle (Thomas Weber)
--   └── Lager
-- 
-- Verwaltung
--   ├── Buchhaltung (Julia Becker)
--   └── Personalwesen
-- 
-- Technik
--   ├── Elektrik (Sabine Müller)
--   ├── Mechanik
--   └── IT
--       ├── Netzwerk (Michael Fischer)
--       └── Software
-- 
-- Standard (aus Migration)
--
-- Mitarbeiter-Logins (alle mit Passwort: test123):
-- 1001 - Max Mustermann (Produktion + Technik)
-- 1002 - Anna Schmidt (Montage + Lager)
-- 1003 - Thomas Weber (Qualitätskontrolle)
-- 2001 - Sabine Müller (Elektrik)
-- 2002 - Michael Fischer (Netzwerk + Software)
-- 3001 - Julia Becker (Buchhaltung)

