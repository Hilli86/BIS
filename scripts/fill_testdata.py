"""
Testdaten-Generator für BIS
Füllt alle Tabellen mit realistischen Beispieldaten für Tests.

Aufruf: py fill_testdata.py
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = 'database_main.db'

# Beispieldaten
VORNAMEN = ['Max', 'Anna', 'Thomas', 'Maria', 'Peter', 'Lisa', 'Michael', 'Sabine', 'Andreas', 'Julia',
            'Stefan', 'Nicole', 'Christian', 'Katrin', 'Daniel', 'Sarah', 'Martin', 'Jennifer', 'Markus', 'Melanie']
NACHNAMEN = ['Müller', 'Schmidt', 'Schneider', 'Fischer', 'Weber', 'Meyer', 'Wagner', 'Becker', 'Schulz', 'Hoffmann',
             'Schäfer', 'Koch', 'Bauer', 'Richter', 'Klein', 'Wolf', 'Schröder', 'Neumann', 'Schwarz', 'Zimmermann']
ABTEILUNGEN = [
    ('Produktion', None),
    ('Wartung', 'Produktion'),
    ('Instandhaltung', 'Produktion'),
    ('Qualitätssicherung', None),
    ('Einkauf', None),
    ('Lager', 'Einkauf'),
    ('Verwaltung', None),
    ('IT', 'Verwaltung'),
]
BEREICHE = ['Elektrik', 'Mechanik', 'Hydraulik', 'Pneumatik', 'Steuerungstechnik']
GEWERKE = {
    'Elektrik': ['Elektromotoren', 'Schaltanlagen', 'Kabel & Leitungen', 'Sensoren', 'Beleuchtung'],
    'Mechanik': ['Getriebe', 'Lager', 'Dichtungen', 'Antriebe', 'Wellen'],
    'Hydraulik': ['Pumpen', 'Ventile', 'Zylinder', 'Schläuche', 'Dichtungen'],
    'Pneumatik': ['Kompressoren', 'Ventile', 'Zylinder', 'Schläuche', 'Fittinge'],
    'Steuerungstechnik': ['SPS', 'HMI', 'Frequenzumrichter', 'Sensoren', 'Aktoren']
}
STATUS = [
    ('Offen', '#FF0000', 1),
    ('In Bearbeitung', '#FFA500', 2),
    ('Wartend', '#FFFF00', 3),
    ('Erledigt', '#00FF00', 4),
    ('Geschlossen', '#808080', 5)
]
TAETIGKEITEN = ['Reparatur', 'Wartung', 'Inspektion', 'Montage', 'Demontage', 'Reinigung', 'Kalibrierung', 'Prüfung']
KATEGORIEN = ['Elektronik', 'Mechanik', 'Hydraulik', 'Pneumatik', 'Werkzeuge', 'Verbrauchsmaterial', 'Schutzausrüstung']
KOSTENSTELLEN = ['Produktion A', 'Produktion B', 'Wartung', 'Instandhaltung', 'Lager', 'Verwaltung']
LIEFERANTEN = [
    ('Bosch Rexroth', 'Max Mustermann', '+49 123 456789', 'info@bosch-rexroth.de', 'Musterstraße 1', '12345', 'Musterstadt'),
    ('Siemens', 'Anna Schmidt', '+49 987 654321', 'info@siemens.de', 'Industriestraße 5', '54321', 'Industriestadt'),
    ('Festo', 'Thomas Weber', '+49 555 123456', 'info@festo.de', 'Technikweg 10', '67890', 'Technikstadt'),
    ('Phoenix Contact', 'Maria Fischer', '+49 111 222333', 'info@phoenixcontact.de', 'Elektroweg 3', '11111', 'Elektrostadt'),
    ('Würth', 'Peter Klein', '+49 444 555666', 'info@wuerth.de', 'Handwerkerstraße 7', '22222', 'Handwerkerstadt'),
]
LAGERORTE = ['Hauptlager', 'Produktionslager', 'Wartungslager', 'Außenlager']
LAGERPLAETZE = ['Regal A1', 'Regal A2', 'Regal B1', 'Regal B2', 'Regal C1', 'Regal C2', 'Kühlraum', 'Sicherheitslager']
EINHEITEN = ['Stück', 'Meter', 'Kilogramm', 'Liter', 'Packung', 'Karton']
WAHRUNGEN = ['EUR', 'USD', 'CHF']

# Ersatzteil-Bezeichnungen
ERSATZTEIL_BEZEICHNUNGEN = [
    'Elektromotor 0,75kW', 'Elektromotor 1,5kW', 'Elektromotor 3kW', 'Elektromotor 5,5kW',
    'Frequenzumrichter 0,75kW', 'Frequenzumrichter 1,5kW', 'Frequenzumrichter 3kW',
    'Hydraulikpumpe 10l/min', 'Hydraulikpumpe 20l/min', 'Hydraulikpumpe 40l/min',
    'Hydraulikzylinder 50mm', 'Hydraulikzylinder 100mm', 'Hydraulikzylinder 200mm',
    'Pneumatikzylinder 32mm', 'Pneumatikzylinder 50mm', 'Pneumatikzylinder 80mm',
    'Ventil 1/2"', 'Ventil 3/4"', 'Ventil 1"', 'Ventil 1 1/4"',
    'Schlauch DN10', 'Schlauch DN16', 'Schlauch DN25', 'Schlauch DN32',
    'Dichtung O-Ring 10mm', 'Dichtung O-Ring 20mm', 'Dichtung O-Ring 30mm',
    'Lager 6205', 'Lager 6206', 'Lager 6207', 'Lager 6305', 'Lager 6306',
    'Getriebe 1:10', 'Getriebe 1:20', 'Getriebe 1:50', 'Getriebe 1:100',
    'Kabel NYY 3x1,5mm²', 'Kabel NYY 3x2,5mm²', 'Kabel NYY 3x4mm²', 'Kabel NYY 3x6mm²',
    'Sicherung 10A', 'Sicherung 16A', 'Sicherung 20A', 'Sicherung 25A',
    'Schalter Taster', 'Schalter Endschalter', 'Schalter Not-Aus',
    'Sensor Näherungsschalter', 'Sensor Lichtschranke', 'Sensor Temperatur',
    'Beleuchtung LED 12V', 'Beleuchtung LED 24V', 'Beleuchtung LED 230V',
    'Werkzeug Schraubendreher', 'Werkzeug Schraubenschlüssel', 'Werkzeug Zange',
    'Schutzbrille', 'Schutzhandschuhe', 'Gehörschutz', 'Sicherheitsschuhe',
    'Reinigungsmittel', 'Schmierfett', 'Hydrauliköl', 'Kühlschmierstoff',
    'Schraube M6x20', 'Schraube M8x25', 'Schraube M10x30', 'Schraube M12x40',
    'Mutter M6', 'Mutter M8', 'Mutter M10', 'Mutter M12',
    'Scheibe 6mm', 'Scheibe 8mm', 'Scheibe 10mm', 'Scheibe 12mm',
    'Kabelbinder 2,5mm', 'Kabelbinder 4mm', 'Kabelbinder 7mm',
    'Klebestreifen', 'Isolierband', 'Klebeband',
    'Filter Luftfilter', 'Filter Ölfilter', 'Filter Wasserfilter',
    'Führungsschiene', 'Linearführung', 'Kugellagerführung',
    'Kupplung elastisch', 'Kupplung starr', 'Kupplung klauen',
    'Riemen Zahnriemen', 'Riemen Keilriemen', 'Riemen Flachriemen',
    'Kette Rollenkette', 'Kette Gelenkkette',
    'Zahnrad Modul 1', 'Zahnrad Modul 2', 'Zahnrad Modul 3',
    'Welle Durchmesser 20mm', 'Welle Durchmesser 30mm', 'Welle Durchmesser 40mm',
    'Kupplungsscheibe', 'Scheibenkupplung', 'Membrankupplung',
    'Dämpfer Stoßdämpfer', 'Dämpfer Schwingungsdämpfer',
    'Feder Druckfeder', 'Feder Zugfeder', 'Feder Torsionsfeder',
    'Magnet Permanentmagnet', 'Magnet Elektromagnet',
    'Relais 24V', 'Relais 230V', 'Kontaktor 24V', 'Kontaktor 230V',
    'Transformator 230/24V', 'Transformator 400/230V',
    'Kondensator 10µF', 'Kondensator 100µF', 'Kondensator 1000µF',
    'Widerstand 1kΩ', 'Widerstand 10kΩ', 'Widerstand 100kΩ',
    'Diode LED rot', 'Diode LED grün', 'Diode LED blau',
    'Transistor NPN', 'Transistor PNP',
    'IC Mikrocontroller', 'IC Operationsverstärker',
    'Stecker Steckverbinder', 'Stecker Kupplung', 'Stecker T-Stück',
    'Kabelkanal 20x20', 'Kabelkanal 40x40', 'Kabelkanal 60x60',
    'Kabeltülle', 'Aderendhülse', 'Kabelschuh',
    'Klemmleiste 12polig', 'Klemmleiste 24polig', 'Klemmleiste 48polig',
    'Schaltkasten', 'Verteilerkasten', 'Steuerungskasten',
    'HMI Touchpanel 7"', 'HMI Touchpanel 10"', 'HMI Touchpanel 15"',
    'SPS CPU', 'SPS E/A-Modul', 'SPS Kommunikationsmodul',
    'Netzteil 24V 5A', 'Netzteil 24V 10A', 'Netzteil 24V 20A',
    'Batterie 12V', 'Batterie 24V', 'Akkumulator',
    'Lüfter 12V', 'Lüfter 24V', 'Lüfter 230V',
    'Wärmetauscher', 'Kühler', 'Heizung',
    'Manometer', 'Druckmesser', 'Temperaturmesser',
    'Durchflussmesser', 'Füllstandsmesser', 'Drehzahlmesser',
]


def get_random_date(days_back=365):
    """Gibt ein zufälliges Datum der letzten N Tage zurück"""
    days = random.randint(0, days_back)
    return datetime.now() - timedelta(days=days)


def fill_abteilungen(conn):
    """Füllt Abteilungen"""
    print("Fülle Abteilungen...")
    cursor = conn.cursor()
    
    abteilung_ids = {}
    for bezeichnung, parent_name in ABTEILUNGEN:
        parent_id = abteilung_ids.get(parent_name) if parent_name else None
        cursor.execute('''
            INSERT OR IGNORE INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung)
            VALUES (?, ?, 1, ?)
        ''', (bezeichnung, parent_id, len(abteilung_ids)))
        abteilung_ids[bezeichnung] = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Abteilung WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
    
    print(f"  ✓ {len(ABTEILUNGEN)} Abteilungen erstellt")
    return abteilung_ids


def fill_mitarbeiter(conn, abteilung_ids):
    """Füllt Mitarbeiter"""
    print("Fülle Mitarbeiter...")
    cursor = conn.cursor()
    
    # Prüfe ob BIS-Admin existiert
    admin = cursor.execute("SELECT ID FROM Mitarbeiter WHERE Personalnummer = '99999'").fetchone()
    if admin:
        admin_id = admin[0]
    else:
        admin_id = None
    
    mitarbeiter_ids = []
    abteilungen_list = list(abteilung_ids.values())
    
    for i in range(30):
        vorname = random.choice(VORNAMEN)
        nachname = random.choice(NACHNAMEN)
        personalnummer = f"{10000 + i:05d}"
        
        # Überspringe Admin-Personalnummer
        if personalnummer == '99999':
            continue
        
        primaer_abteilung_id = random.choice(abteilungen_list)
        passwort_hash = generate_password_hash('test123')
        
        cursor.execute('''
            INSERT OR IGNORE INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort, PrimaerAbteilungID)
            VALUES (?, ?, ?, 1, ?, ?)
        ''', (personalnummer, vorname, nachname, passwort_hash, primaer_abteilung_id))
        
        mitarbeiter_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Mitarbeiter WHERE Personalnummer = ?', (personalnummer,)
        ).fetchone()[0]
        
        mitarbeiter_ids.append(mitarbeiter_id)
        
        # Zusätzliche Abteilungen (30% Chance)
        if random.random() < 0.3:
            zusatz_abteilung = random.choice([a for a in abteilungen_list if a != primaer_abteilung_id])
            cursor.execute('''
                INSERT OR IGNORE INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID)
                VALUES (?, ?)
            ''', (mitarbeiter_id, zusatz_abteilung))
    
    print(f"  ✓ {len(mitarbeiter_ids)} Mitarbeiter erstellt")
    return mitarbeiter_ids


def fill_bereiche_gewerke(conn):
    """Füllt Bereiche und Gewerke"""
    print("Fülle Bereiche und Gewerke...")
    cursor = conn.cursor()
    
    bereich_ids = {}
    gewerk_ids = []
    
    for bereich_name in BEREICHE:
        cursor.execute('''
            INSERT OR IGNORE INTO Bereich (Bezeichnung, Aktiv)
            VALUES (?, 1)
        ''', (bereich_name,))
        bereich_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Bereich WHERE Bezeichnung = ?', (bereich_name,)
        ).fetchone()[0]
        bereich_ids[bereich_name] = bereich_id
        
        for gewerk_name in GEWERKE[bereich_name]:
            cursor.execute('''
                INSERT OR IGNORE INTO Gewerke (Bezeichnung, BereichID, Aktiv)
                VALUES (?, ?, 1)
            ''', (gewerk_name, bereich_id))
            gewerk_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
                'SELECT ID FROM Gewerke WHERE Bezeichnung = ? AND BereichID = ?', (gewerk_name, bereich_id)
            ).fetchone()[0]
            gewerk_ids.append(gewerk_id)
    
    print(f"  ✓ {len(BEREICHE)} Bereiche und {len(gewerk_ids)} Gewerke erstellt")
    return bereich_ids, gewerk_ids


def fill_status(conn):
    """Füllt Status"""
    print("Fülle Status...")
    cursor = conn.cursor()
    
    status_ids = []
    for bezeichnung, farbe, sortierung in STATUS:
        cursor.execute('''
            INSERT OR IGNORE INTO Status (Bezeichnung, Farbe, Sortierung, Aktiv)
            VALUES (?, ?, ?, 1)
        ''', (bezeichnung, farbe, sortierung))
        status_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Status WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
        status_ids.append(status_id)
    
    print(f"  ✓ {len(STATUS)} Status erstellt")
    return status_ids


def fill_taetigkeiten(conn):
    """Füllt Tätigkeiten"""
    print("Fülle Tätigkeiten...")
    cursor = conn.cursor()
    
    taetigkeit_ids = []
    for i, bezeichnung in enumerate(TAETIGKEITEN):
        cursor.execute('''
            INSERT OR IGNORE INTO Taetigkeit (Bezeichnung, Sortierung, Aktiv)
            VALUES (?, ?, 1)
        ''', (bezeichnung, i + 1))
        taetigkeit_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Taetigkeit WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
        taetigkeit_ids.append(taetigkeit_id)
    
    print(f"  ✓ {len(TAETIGKEITEN)} Tätigkeiten erstellt")
    return taetigkeit_ids


def fill_kategorien(conn):
    """Füllt Ersatzteil-Kategorien"""
    print("Fülle Ersatzteil-Kategorien...")
    cursor = conn.cursor()
    
    kategorie_ids = []
    for i, bezeichnung in enumerate(KATEGORIEN):
        cursor.execute('''
            INSERT OR IGNORE INTO ErsatzteilKategorie (Bezeichnung, Sortierung, Aktiv)
            VALUES (?, ?, 1)
        ''', (bezeichnung, i + 1))
        kategorie_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM ErsatzteilKategorie WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
        kategorie_ids.append(kategorie_id)
    
    print(f"  ✓ {len(KATEGORIEN)} Kategorien erstellt")
    return kategorie_ids


def fill_kostenstellen(conn):
    """Füllt Kostenstellen"""
    print("Fülle Kostenstellen...")
    cursor = conn.cursor()
    
    kostenstelle_ids = []
    for i, bezeichnung in enumerate(KOSTENSTELLEN):
        cursor.execute('''
            INSERT OR IGNORE INTO Kostenstelle (Bezeichnung, Sortierung, Aktiv)
            VALUES (?, ?, 1)
        ''', (bezeichnung, i + 1))
        kostenstelle_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Kostenstelle WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
        kostenstelle_ids.append(kostenstelle_id)
    
    print(f"  ✓ {len(KOSTENSTELLEN)} Kostenstellen erstellt")
    return kostenstelle_ids


def fill_lieferanten(conn):
    """Füllt Lieferanten"""
    print("Fülle Lieferanten...")
    cursor = conn.cursor()
    
    lieferant_ids = []
    for name, kontaktperson, telefon, email, strasse, plz, ort in LIEFERANTEN:
        cursor.execute('''
            INSERT OR IGNORE INTO Lieferant (Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Aktiv, Gelöscht)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
        ''', (name, kontaktperson, telefon, email, strasse, plz, ort))
        lieferant_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Lieferant WHERE Name = ?', (name,)
        ).fetchone()[0]
        lieferant_ids.append(lieferant_id)
    
    print(f"  ✓ {len(LIEFERANTEN)} Lieferanten erstellt")
    return lieferant_ids


def fill_lagerorte_plaetze(conn):
    """Füllt Lagerorte und Lagerplätze"""
    print("Fülle Lagerorte und Lagerplätze...")
    cursor = conn.cursor()
    
    lagerort_ids = []
    for i, bezeichnung in enumerate(LAGERORTE):
        cursor.execute('''
            INSERT OR IGNORE INTO Lagerort (Bezeichnung, Sortierung, Aktiv)
            VALUES (?, ?, 1)
        ''', (bezeichnung, i + 1))
        lagerort_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Lagerort WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
        lagerort_ids.append(lagerort_id)
    
    lagerplatz_ids = []
    for i, bezeichnung in enumerate(LAGERPLAETZE):
        cursor.execute('''
            INSERT OR IGNORE INTO Lagerplatz (Bezeichnung, Sortierung, Aktiv)
            VALUES (?, ?, 1)
        ''', (bezeichnung, i + 1))
        lagerplatz_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Lagerplatz WHERE Bezeichnung = ?', (bezeichnung,)
        ).fetchone()[0]
        lagerplatz_ids.append(lagerplatz_id)
    
    print(f"  ✓ {len(LAGERORTE)} Lagerorte und {len(LAGERPLAETZE)} Lagerplätze erstellt")
    return lagerort_ids, lagerplatz_ids


def fill_ersatzteile(conn, kategorie_ids, lieferant_ids, lagerort_ids, lagerplatz_ids, mitarbeiter_ids):
    """Füllt Ersatzteile (mindestens 100)"""
    print("Fülle Ersatzteile...")
    cursor = conn.cursor()
    
    ersatzteil_ids = []
    num_ersatzteile = max(100, len(ERSATZTEIL_BEZEICHNUNGEN))
    
    for i in range(num_ersatzteile):
        bestellnummer = f"ET-{1000 + i:05d}"
        bezeichnung = ERSATZTEIL_BEZEICHNUNGEN[i % len(ERSATZTEIL_BEZEICHNUNGEN)]
        if i >= len(ERSATZTEIL_BEZEICHNUNGEN):
            bezeichnung = f"{bezeichnung} Variante {i // len(ERSATZTEIL_BEZEICHNUNGEN) + 1}"
        
        beschreibung = f"Beschreibung für {bezeichnung}"
        kategorie_id = random.choice(kategorie_ids) if kategorie_ids else None
        hersteller = random.choice(['Bosch', 'Siemens', 'Festo', 'Phoenix Contact', 'Würth', 'ABB', 'Schneider Electric'])
        lieferant_id = random.choice(lieferant_ids) if lieferant_ids else None
        preis = round(random.uniform(5.0, 5000.0), 2)
        waehrung = random.choice(WAHRUNGEN)
        lagerort_id = random.choice(lagerort_ids) if lagerort_ids else None
        lagerplatz_id = random.choice(lagerplatz_ids) if lagerplatz_ids else None
        mindestbestand = random.randint(0, 50)
        aktueller_bestand = random.randint(0, 200)
        einheit = random.choice(EINHEITEN)
        end_of_life = 1 if random.random() < 0.05 else 0  # 5% End of Life
        nachfolgeartikel_id = None
        kennzeichen = random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') if random.random() < 0.3 else None
        artikelnummer_hersteller = f"HER-{random.randint(1000, 9999)}" if random.random() < 0.7 else None
        aktiv = 1 if random.random() < 0.95 else 0  # 95% aktiv
        erstellt_von_id = random.choice(mitarbeiter_ids) if mitarbeiter_ids else None
        
        cursor.execute('''
            INSERT OR IGNORE INTO Ersatzteil (
                Bestellnummer, Bezeichnung, Beschreibung, KategorieID, Hersteller,
                LieferantID, Preis, Waehrung, LagerortID, LagerplatzID, Mindestbestand,
                AktuellerBestand, Einheit, EndOfLife, NachfolgeartikelID, Kennzeichen,
                ArtikelnummerHersteller, Aktiv, Gelöscht, ErstelltVonID
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ''', (bestellnummer, bezeichnung, beschreibung, kategorie_id, hersteller,
              lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand,
              aktueller_bestand, einheit, end_of_life, nachfolgeartikel_id, kennzeichen,
              artikelnummer_hersteller, aktiv, erstellt_von_id))
        
        ersatzteil_id = cursor.lastrowid if cursor.lastrowid else cursor.execute(
            'SELECT ID FROM Ersatzteil WHERE Bestellnummer = ?', (bestellnummer,)
        ).fetchone()[0]
        ersatzteil_ids.append(ersatzteil_id)
        
        # Nachfolgeartikel setzen (bei End of Life)
        if end_of_life and len(ersatzteil_ids) > 1:
            nachfolge_id = random.choice(ersatzteil_ids[:-1])
            cursor.execute('UPDATE Ersatzteil SET NachfolgeartikelID = ? WHERE ID = ?', (nachfolge_id, ersatzteil_id))
        
        # Abteilungszugriff (jedes Ersatzteil für 1-3 Abteilungen)
        abteilungen = cursor.execute('SELECT ID FROM Abteilung WHERE Aktiv = 1 LIMIT ?', (random.randint(1, 3),)).fetchall()
        for abt in abteilungen:
            cursor.execute('''
                INSERT OR IGNORE INTO ErsatzteilAbteilungZugriff (ErsatzteilID, AbteilungID)
                VALUES (?, ?)
            ''', (ersatzteil_id, abt[0]))
    
    print(f"  ✓ {len(ersatzteil_ids)} Ersatzteile erstellt")
    return ersatzteil_ids


def fill_themen(conn, gewerk_ids, status_ids, abteilung_ids, mitarbeiter_ids):
    """Füllt Schichtbuch-Themen"""
    print("Fülle Schichtbuch-Themen...")
    cursor = conn.cursor()
    
    thema_ids = []
    num_themen = 50
    
    for i in range(num_themen):
        gewerk_id = random.choice(gewerk_ids) if gewerk_ids else None
        status_id = random.choice(status_ids) if status_ids else None
        ersteller_abteilung_id = random.choice(list(abteilung_ids.values())) if abteilung_ids else None
        
        cursor.execute('''
            INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID, Gelöscht, ErstelltAm)
            VALUES (?, ?, ?, 0, ?)
        ''', (gewerk_id, status_id, ersteller_abteilung_id, get_random_date(180)))
        
        thema_id = cursor.lastrowid
        thema_ids.append(thema_id)
        
        # Sichtbarkeit für 1-3 Abteilungen
        sichtbare_abteilungen = random.sample(list(abteilung_ids.values()), min(3, len(abteilung_ids)))
        for abt_id in sichtbare_abteilungen:
            cursor.execute('''
                INSERT OR IGNORE INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
                VALUES (?, ?)
            ''', (thema_id, abt_id))
    
    print(f"  ✓ {len(thema_ids)} Themen erstellt")
    return thema_ids


def fill_bemerkungen(conn, thema_ids, mitarbeiter_ids, taetigkeit_ids):
    """Füllt Schichtbuch-Bemerkungen"""
    print("Fülle Schichtbuch-Bemerkungen...")
    cursor = conn.cursor()
    
    bemerkungen = [
        "Reparatur durchgeführt, Maschine läuft wieder",
        "Wartung gemäß Plan durchgeführt",
        "Inspektion abgeschlossen, keine Mängel festgestellt",
        "Teil ausgetauscht, Funktionstest erfolgreich",
        "Reinigung durchgeführt",
        "Kalibrierung vorgenommen",
        "Prüfung erfolgreich abgeschlossen",
        "Montage abgeschlossen",
        "Demontage durchgeführt",
        "Wartungsplan aktualisiert",
        "Ersatzteil bestellt",
        "Lieferant kontaktiert",
        "Dokumentation aktualisiert",
        "Schulung durchgeführt",
        "Problem behoben",
    ]
    
    num_bemerkungen = 0
    for thema_id in thema_ids:
        # 1-5 Bemerkungen pro Thema
        num_bem = random.randint(1, 5)
        for i in range(num_bem):
            mitarbeiter_id = random.choice(mitarbeiter_ids) if mitarbeiter_ids else None
            taetigkeit_id = random.choice(taetigkeit_ids) if taetigkeit_ids else None
            bemerkung = random.choice(bemerkungen)
            datum = get_random_date(180)
            
            cursor.execute('''
                INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung, Gelöscht)
                VALUES (?, ?, ?, ?, ?, 0)
            ''', (thema_id, mitarbeiter_id, datum, taetigkeit_id, bemerkung))
            num_bemerkungen += 1
    
    print(f"  ✓ {num_bemerkungen} Bemerkungen erstellt")
    return num_bemerkungen


def fill_lagerbuchungen(conn, ersatzteil_ids, mitarbeiter_ids, kostenstelle_ids, thema_ids):
    """Füllt Lagerbuchungen"""
    print("Fülle Lagerbuchungen...")
    cursor = conn.cursor()
    
    typen = ['Eingang', 'Ausgang', 'Inventur']
    gruende = ['Einkauf', 'Verbrauch', 'Thema', 'Inventur', 'Umlagerung', 'Ausschuss']
    
    num_buchungen = 0
    for ersatzteil_id in ersatzteil_ids[:50]:  # Nur für erste 50 Ersatzteile
        # 2-10 Buchungen pro Ersatzteil
        num_buch = random.randint(2, 10)
        for i in range(num_buch):
            typ = random.choice(typen)
            menge = random.randint(1, 50)
            grund = random.choice(gruende)
            thema_id = random.choice(thema_ids) if thema_ids and random.random() < 0.3 else None
            kostenstelle_id = random.choice(kostenstelle_ids) if kostenstelle_ids else None
            verwendet_von_id = random.choice(mitarbeiter_ids) if mitarbeiter_ids else None
            bemerkung = f"Buchung: {grund}"
            preis = round(random.uniform(5.0, 5000.0), 2)
            waehrung = random.choice(WAHRUNGEN)
            buchungsdatum = get_random_date(180)
            
            cursor.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ersatzteil_id, typ, menge, grund, thema_id, kostenstelle_id,
                  verwendet_von_id, bemerkung, preis, waehrung, buchungsdatum))
            num_buchungen += 1
    
    print(f"  ✓ {num_buchungen} Lagerbuchungen erstellt")
    return num_buchungen


def main():
    """Hauptfunktion"""
    print("=" * 70)
    print("  BIS - Testdaten-Generator")
    print("=" * 70)
    print()
    
    if not os.path.exists(DB_PATH):
        print(f"[FEHLER] Datenbank '{DB_PATH}' nicht gefunden!")
        print("Bitte führen Sie zuerst 'py init_database.py' aus.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Abteilungen
        abteilung_ids = fill_abteilungen(conn)
        conn.commit()
        
        # Mitarbeiter
        mitarbeiter_ids = fill_mitarbeiter(conn, abteilung_ids)
        conn.commit()
        
        # Bereiche und Gewerke
        bereich_ids, gewerk_ids = fill_bereiche_gewerke(conn)
        conn.commit()
        
        # Status
        status_ids = fill_status(conn)
        conn.commit()
        
        # Tätigkeiten
        taetigkeit_ids = fill_taetigkeiten(conn)
        conn.commit()
        
        # Kategorien
        kategorie_ids = fill_kategorien(conn)
        conn.commit()
        
        # Kostenstellen
        kostenstelle_ids = fill_kostenstellen(conn)
        conn.commit()
        
        # Lieferanten
        lieferant_ids = fill_lieferanten(conn)
        conn.commit()
        
        # Lagerorte und Lagerplätze
        lagerort_ids, lagerplatz_ids = fill_lagerorte_plaetze(conn)
        conn.commit()
        
        # Ersatzteile
        ersatzteil_ids = fill_ersatzteile(conn, kategorie_ids, lieferant_ids, lagerort_ids, lagerplatz_ids, mitarbeiter_ids)
        conn.commit()
        
        # Themen
        thema_ids = fill_themen(conn, gewerk_ids, status_ids, abteilung_ids, mitarbeiter_ids)
        conn.commit()
        
        # Bemerkungen
        num_bemerkungen = fill_bemerkungen(conn, thema_ids, mitarbeiter_ids, taetigkeit_ids)
        conn.commit()
        
        # Lagerbuchungen
        num_buchungen = fill_lagerbuchungen(conn, ersatzteil_ids, mitarbeiter_ids, kostenstelle_ids, thema_ids)
        conn.commit()
        
        print()
        print("=" * 70)
        print("  [ERFOLG] Testdaten erfolgreich erstellt!")
        print("=" * 70)
        print()
        print("Zusammenfassung:")
        print(f"  - Abteilungen: {len(abteilung_ids)}")
        print(f"  - Mitarbeiter: {len(mitarbeiter_ids)}")
        print(f"  - Bereiche: {len(bereich_ids)}")
        print(f"  - Gewerke: {len(gewerk_ids)}")
        print(f"  - Status: {len(status_ids)}")
        print(f"  - Tätigkeiten: {len(taetigkeit_ids)}")
        print(f"  - Ersatzteil-Kategorien: {len(kategorie_ids)}")
        print(f"  - Kostenstellen: {len(kostenstelle_ids)}")
        print(f"  - Lieferanten: {len(lieferant_ids)}")
        print(f"  - Lagerorte: {len(lagerort_ids)}")
        print(f"  - Lagerplätze: {len(lagerplatz_ids)}")
        print(f"  - Ersatzteile: {len(ersatzteil_ids)}")
        print(f"  - Themen: {len(thema_ids)}")
        print(f"  - Bemerkungen: {num_bemerkungen}")
        print(f"  - Lagerbuchungen: {num_buchungen}")
        print()
        
    except Exception as e:
        print(f"\n[FEHLER] Fehler beim Erstellen der Testdaten: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    main()

