# Migrations-Ordner

Dieser Ordner enthält historische Migrationsskripte, die bereits in `utils/database_check.py` integriert wurden.

## ⚠️ Wichtiger Hinweis

**Alle Migrationen werden jetzt automatisch beim App-Start durch `database_check.py` ausgeführt.**  
Die einzelnen Migrationsskripte in diesem Ordner sind nicht mehr erforderlich und dienen nur noch zur Dokumentation.

## Integrierte Migrationen

Alle folgenden Migrationen sind in `utils/database_check.py` integriert:

### Tabellenerstellung
- ✅ `create_angebotsanfrage_tables.py` - Angebotsanfrage und AngebotsanfragePosition Tabellen
- ✅ `create_bestellung_tables.py` - Bestellung, BestellungPosition, BestellungSichtbarkeit Tabellen
- ✅ `create_berechtigungen_system.py` - Berechtigung und MitarbeiterBerechtigung Tabellen
- ✅ `create_firmendaten_table.py` - Firmendaten Tabelle
- ✅ `create_login_log_table.py` - LoginLog Tabelle

### Spalten-Erweiterungen
- ✅ `add_email_handy_to_mitarbeiter.py` - Email und Handynummer zu Mitarbeiter
- ✅ `add_abteilung_to_angebotsanfrage.py` - ErstellerAbteilungID zu Angebotsanfrage
- ✅ `add_bestellnummer_bezeichnung_to_angebotsanfrage_position.py` - Bestellnummer und Bezeichnung zu AngebotsanfragePosition
- ✅ `add_freigabebemerkung_to_bestellung.py` - FreigabeBemerkung zu Bestellung
- ✅ `add_unterschrift_to_bestellung.py` - Unterschrift zu Bestellung
- ✅ `add_lieferanschrift_to_firmendaten.py` - Lieferanschrift-Felder zu Firmendaten

### Spalten-Umbenennungen
- ✅ `rename_artikelnummer_to_bestellnummer.py` - Artikelnummer → Bestellnummer in Ersatzteil

### Struktur-Änderungen
- ✅ `make_ersatzteilid_optional_in_angebotsanfrage_position.py` - ErsatzteilID optional in AngebotsanfragePosition

### Weitere Änderungen in database_check.py
- ✅ BestellungID zu Lagerbuchung (für Wareneingang)
- ✅ Preisstand zu Ersatzteil
- ✅ ErhalteneMenge zu BestellungPosition
- ✅ ErstelltAm zu SchichtbuchThema, SchichtbuchThemaSichtbarkeit, BestellungSichtbarkeit, Benachrichtigung

## Verwendung

**Keine manuelle Ausführung der Migrationsskripte erforderlich!**

Die Datenbank-Struktur wird automatisch beim App-Start geprüft und fehlende Elemente (Tabellen, Spalten, Indexes) werden automatisch erstellt.

Siehe: `utils/database_check.py` → `initialize_database_on_startup()`

## Zusätzliche Dateien

- `sql_befehle` - Manuelle SQL-Befehle für spezielle Anpassungen
- `testdaten_abteilungen.sql` - SQL für Testdaten

Diese Dateien bleiben erhalten, falls sie manuell verwendet werden sollen.

