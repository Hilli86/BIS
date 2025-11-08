-- Migration 004: Ersatzteilverwaltung Phase 1
-- Datum: 2025-02-23
-- Beschreibung: Ersatzteilverwaltung mit Lieferanten, Lagerbuchungen und Verknüpfungen zu Schichtbuch-Themen
-- Hinweis: Bestellungen werden in Phase 2 implementiert

BEGIN TRANSACTION;

-- ========== 1. Tabelle: ErsatzteilKategorie ==========
CREATE TABLE IF NOT EXISTS ErsatzteilKategorie (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Bezeichnung TEXT NOT NULL,
    Beschreibung TEXT,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Sortierung INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ersatzteil_kategorie_aktiv ON ErsatzteilKategorie(Aktiv);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_kategorie_sortierung ON ErsatzteilKategorie(Sortierung);

-- ========== 2. Tabelle: Kostenstelle ==========
CREATE TABLE IF NOT EXISTS Kostenstelle (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Bezeichnung TEXT NOT NULL,
    Beschreibung TEXT,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Sortierung INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_kostenstelle_aktiv ON Kostenstelle(Aktiv);
CREATE INDEX IF NOT EXISTS idx_kostenstelle_sortierung ON Kostenstelle(Sortierung);

-- ========== 3. Tabelle: Lieferant ==========
CREATE TABLE IF NOT EXISTS Lieferant (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    Kontaktperson TEXT,
    Telefon TEXT,
    Email TEXT,
    Strasse TEXT,
    PLZ TEXT,
    Ort TEXT,
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Gelöscht INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_lieferant_aktiv ON Lieferant(Aktiv);
CREATE INDEX IF NOT EXISTS idx_lieferant_geloescht ON Lieferant(Gelöscht);

-- ========== 4. Tabelle: Ersatzteil ==========
CREATE TABLE IF NOT EXISTS Ersatzteil (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Artikelnummer TEXT NOT NULL UNIQUE,
    Bezeichnung TEXT NOT NULL,
    Beschreibung TEXT,
    KategorieID INTEGER,
    Hersteller TEXT,
    LieferantID INTEGER,
    Preis REAL,
    Waehrung TEXT DEFAULT 'EUR',
    Lagerort TEXT,
    Mindestbestand INTEGER DEFAULT 0,
    AktuellerBestand INTEGER DEFAULT 0,
    Einheit TEXT DEFAULT 'Stück',
    Aktiv INTEGER NOT NULL DEFAULT 1,
    Gelöscht INTEGER NOT NULL DEFAULT 0,
    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    ErstelltVonID INTEGER,
    FOREIGN KEY (KategorieID) REFERENCES ErsatzteilKategorie(ID),
    FOREIGN KEY (LieferantID) REFERENCES Lieferant(ID),
    FOREIGN KEY (ErstelltVonID) REFERENCES Mitarbeiter(ID)
);

CREATE INDEX IF NOT EXISTS idx_ersatzteil_artikelnummer ON Ersatzteil(Artikelnummer);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_kategorie ON Ersatzteil(KategorieID);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_lieferant ON Ersatzteil(LieferantID);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_aktiv ON Ersatzteil(Aktiv);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_geloescht ON Ersatzteil(Gelöscht);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_bestand ON Ersatzteil(AktuellerBestand);

-- ========== 5. Tabelle: ErsatzteilBild ==========
CREATE TABLE IF NOT EXISTS ErsatzteilBild (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ErsatzteilID INTEGER NOT NULL,
    Dateiname TEXT NOT NULL,
    Dateipfad TEXT NOT NULL,
    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ersatzteil_bild_ersatzteil ON ErsatzteilBild(ErsatzteilID);

-- ========== 6. Tabelle: ErsatzteilDokument ==========
CREATE TABLE IF NOT EXISTS ErsatzteilDokument (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ErsatzteilID INTEGER NOT NULL,
    Dateiname TEXT NOT NULL,
    Dateipfad TEXT NOT NULL,
    Typ TEXT,
    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ersatzteil_dokument_ersatzteil ON ErsatzteilDokument(ErsatzteilID);

-- ========== 7. Tabelle: Lagerbuchung ==========
-- Wichtig: Lagerbuchungen können NICHT gelöscht werden (kein Gelöscht-Flag)
CREATE TABLE IF NOT EXISTS Lagerbuchung (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ErsatzteilID INTEGER NOT NULL,
    Typ TEXT NOT NULL, -- 'Eingang' oder 'Ausgang'
    Menge INTEGER NOT NULL,
    Grund TEXT, -- 'Manuell', 'Thema', 'Lieferung', etc.
    ThemaID INTEGER NULL,
    KostenstelleID INTEGER,
    VerwendetVonID INTEGER NOT NULL,
    Buchungsdatum DATETIME DEFAULT CURRENT_TIMESTAMP,
    Bemerkung TEXT,
    ErstelltAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID),
    FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID),
    FOREIGN KEY (KostenstelleID) REFERENCES Kostenstelle(ID),
    FOREIGN KEY (VerwendetVonID) REFERENCES Mitarbeiter(ID)
);

CREATE INDEX IF NOT EXISTS idx_lagerbuchung_ersatzteil ON Lagerbuchung(ErsatzteilID);
CREATE INDEX IF NOT EXISTS idx_lagerbuchung_thema ON Lagerbuchung(ThemaID);
CREATE INDEX IF NOT EXISTS idx_lagerbuchung_kostenstelle ON Lagerbuchung(KostenstelleID);
CREATE INDEX IF NOT EXISTS idx_lagerbuchung_verwendet_von ON Lagerbuchung(VerwendetVonID);
CREATE INDEX IF NOT EXISTS idx_lagerbuchung_buchungsdatum ON Lagerbuchung(Buchungsdatum);

-- ========== 8. Tabelle: ErsatzteilThemaVerknuepfung ==========
CREATE TABLE IF NOT EXISTS ErsatzteilThemaVerknuepfung (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ErsatzteilID INTEGER NOT NULL,
    ThemaID INTEGER NOT NULL,
    Menge INTEGER NOT NULL,
    VerwendetVonID INTEGER NOT NULL,
    VerwendetAm DATETIME DEFAULT CURRENT_TIMESTAMP,
    Bemerkung TEXT,
    FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID),
    FOREIGN KEY (ThemaID) REFERENCES SchichtbuchThema(ID) ON DELETE CASCADE,
    FOREIGN KEY (VerwendetVonID) REFERENCES Mitarbeiter(ID)
);

CREATE INDEX IF NOT EXISTS idx_ersatzteil_thema_ersatzteil ON ErsatzteilThemaVerknuepfung(ErsatzteilID);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_thema_thema ON ErsatzteilThemaVerknuepfung(ThemaID);

-- ========== 9. Tabelle: ErsatzteilAbteilungZugriff ==========
CREATE TABLE IF NOT EXISTS ErsatzteilAbteilungZugriff (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ErsatzteilID INTEGER NOT NULL,
    AbteilungID INTEGER NOT NULL,
    FOREIGN KEY (ErsatzteilID) REFERENCES Ersatzteil(ID) ON DELETE CASCADE,
    FOREIGN KEY (AbteilungID) REFERENCES Abteilung(ID) ON DELETE CASCADE,
    UNIQUE(ErsatzteilID, AbteilungID)
);

CREATE INDEX IF NOT EXISTS idx_ersatzteil_abteilung_ersatzteil ON ErsatzteilAbteilungZugriff(ErsatzteilID);
CREATE INDEX IF NOT EXISTS idx_ersatzteil_abteilung_abteilung ON ErsatzteilAbteilungZugriff(AbteilungID);

COMMIT;

