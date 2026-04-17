# BIS - Betriebsinformationssystem

Ein Flask-basiertes Schichtbuch-System für die Verwaltung von Arbeitsaufträgen und Bemerkungen.

## 🚀 Schnellstart

### Voraussetzungen
- Python 3.8+
- pip
- **LibreOffice** (für PDF-Export von Bestellungen und Angebotsanfragen)
  - Linux: `sudo apt-get install libreoffice` oder `sudo yum install libreoffice`
  - Windows: Download von [libreoffice.org](https://www.libreoffice.org/download/)
  - macOS: `brew install --cask libreoffice`

### Installation

1. **Repository klonen:**
```bash
git clone <repository-url>
cd BIS
```

2. **Virtuelle Umgebung erstellen:**
```bash
python -m venv venv
```

3. **Virtuelle Umgebung aktivieren:**
- Windows (PowerShell):
```powershell
./venv/Scripts/Activate.ps1
```
- Windows (CMD):
```cmd
venv\Scripts\activate
```
- Linux/Mac:
```bash
source venv/bin/activate
```

4. **Abhängigkeiten installieren:**
```bash
pip install -r requirements.txt
```

5. **Umgebungsvariablen konfigurieren:**
Erstellen Sie eine `.env` basierend auf `env_example.txt`:
- Windows (PowerShell):
```powershell
Copy-Item env_example.txt .env
```
- Windows (CMD):
```cmd
copy env_example.txt .env
```
- Linux/Mac:
```bash
cp env_example.txt .env
```

6. **Datenbank:**
- Standard-Datei ist `database_main.db` (bereits im Repo enthalten).
- Pfad kann über `DATABASE_URL` in `.env` geändert werden.

7. **Anwendung starten:**

Lokale Entwicklung (Flask-Dev-Server):
```bash
flask --app app run
```
- Debug-Modus optional über `FLASK_DEBUG=True` aktivieren (siehe unten).
- Host/Port lassen sich per `--host 0.0.0.0 --port 5000` setzen oder über
  die Umgebungsvariablen `BIS_DEV_HOST`/`BIS_DEV_PORT` beim direkten
  `python app.py`-Start.

Produktion (Gunicorn hinter Reverse-Proxy, z. B. nginx):
```bash
gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```
- `python app.py` bzw. Debug-Modus sind **nicht** für den produktiven
  Betrieb gedacht.
- Siehe `deployment/bis.service` und `Dockerfile` für fertige Setups.

Die Anwendung ist dann unter `http://localhost:5000` (Dev) bzw. der vom
Reverse-Proxy bereitgestellten URL erreichbar.

## 🔐 Initial-Admin

Bei einer **leeren Datenbank** (kein Mitarbeiter vorhanden) wird einmalig
ein Admin-Benutzer angelegt:

- **Personalnummer:** 99999
- **Passwort:** wird zufällig erzeugt und **einmalig** beim Start in die
  Anwendungslogs geschrieben (Logger `bis.init`, Level `WARNING`).
- **Name:** BIS-Admin
- **Wechsel-Zwang:** Beim ersten Login wird der Admin zur Passwort-Änderung
  geführt (`PasswortWechselErforderlich = 1`), ein Weiterarbeiten ist erst
  nach dem Setzen eines neuen Passworts möglich.

Wenn bereits Mitarbeiter existieren, wird **kein** zusätzlicher Admin
automatisch angelegt. Admin-Rechte können nachträglich über die
Admin-Seite vergeben werden.


## ⚙️ Konfiguration

### Umgebungsvariablen

Erstellen Sie eine `.env` Datei basierend auf `env_example.txt`:

```env
FLASK_ENV=development
SECRET_KEY=ihr-super-geheimer-schluessel
DATABASE_URL=database_main.db
SQL_TRACING=True
```

### Produktionsumgebung

Für die Produktion setzen Sie:
```env
FLASK_ENV=production
SECRET_KEY=<starker-zufaelliger-schluessel>
SQL_TRACING=False
```

**📦 Produktionsserver-Deployment:**

Für die Einrichtung eines produktiven Servers:

- **💰 Hosting-Optionen:** [HOSTING_OPTIONEN.md](HOSTING_OPTIONEN.md) - Günstige Hosting-Anbieter für Tests & Start
- **⭐ Schnellstart:** [SCHNELLSTART_DEPLOYMENT.md](SCHNELLSTART_DEPLOYMENT.md) - Setup in 30 Min
- **📖 Vollständiger Guide:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Alle Details
- **📋 Übersicht:** [DEPLOYMENT_ÜBERSICHT.md](DEPLOYMENT_ÜBERSICHT.md) - Alle Optionen

Automatische Deployment-Scripts finden Sie im Ordner `deployment/`.

## 📁 Projektstruktur

```
BIS/
├── app.py                 # Hauptanwendung
├── config.py              # Konfiguration
├── init_database.py       # Datenbank-Initialisierung
├── modules/               # Modulare Blueprints
│   ├── auth/             # Authentifizierung
│   ├── schichtbuch/      # Schichtbuch-Funktionen
│   ├── ersatzteile/     # Ersatzteile-Verwaltung
│   └── admin/            # Admin-Bereich
├── utils/                 # Hilfsfunktionen
├── migrations/            # Datenbank-Migrationen
├── templates/             # HTML-Templates
│   ├── layout/
│   ├── dashboard/
│   ├── auth/
│   └── errors/
├── static/                # CSS/JS/Icons
├── env_example.txt        # Beispiel-Env
├── requirements.txt       # Python-Abhängigkeiten
└── database_main.db       # SQLite-Datenbank (Standard)
```

## 🔧 Funktionen

### Benutzerverwaltung
- **Benutzerauthentifizierung** mit Personalnummer
- **Benutzerprofil** - Anzeige und Bearbeitung persönlicher Daten
- **Passwort ändern** - Selbstständige Passwortänderung
- **Dashboard** - Übersicht mit Statistiken und Aktivitäten

### Schichtbuch-Verwaltung
- **Themenliste** mit Infinite Scroll (Laden in Seiten à 50 Einträgen)
- **Filter** (einklappbar):
  - Bereich und Gewerk (Gewerk dynamisch nach Bereich)
  - Status-Mehrfachauswahl
  - Textsuche in Bemerkungen
- **Thema-Details**
  - Tätigkeit wird pro Bemerkung angezeigt
  - Eigene Bemerkungen können inline bearbeitet werden (Text und Tätigkeit)
  - **PDF-Export** - Themen als PDF exportieren
  - Datei-Upload und QR-Code-Generierung
- **Status-Tracking** (Offen, In Arbeit, Abgeschlossen)
- **Sichtbarkeitssteuerung** - Themen für bestimmte Abteilungen sichtbar machen

### Benachrichtigungen
- **Toast-Benachrichtigungen** bei neuen Bemerkungen auf eigenen Themen
- **Badge-Anzeige** in der Navigation für ungelesene Nachrichten
- Automatische Aktualisierung alle 30 Sekunden

### Bestellwesen
- **Angebotsanfragen**:
  - Anfragen an Lieferanten mit mehreren Positionen
  - Status-Verwaltung (Offen, Versendet, Angebot erhalten, Abgeschlossen)
  - Smart-Add-Funktion: Prüft auf bestehende offene Anfragen beim Lieferanten
  - **PDF-Export** im professionellen Geschäftsdokument-Stil (benötigt LibreOffice)
  - Positionen bearbeitbar per Klick (bei offenen Anfragen)
  - Artikel direkt aus Position erstellen (wenn noch nicht vorhanden)
  - PDF-Upload für erhaltene Angebote
  - Preisübernahme aus Angebot mit automatischer Preisstand-Aktualisierung
- **Bestellungen**:
  - **PDF-Export** für Bestellungen (benötigt LibreOffice)
  - Falls LibreOffice nicht verfügbar ist, wird automatisch DOCX zurückgegeben
- **Modal-Auswahl**:
  - Ersatzteile vom Lieferanten per Modal auswählbar
  - Automatisches Befüllen von Bestellnummer und Bezeichnung

### Ersatzteile-Verwaltung
- **Ersatzteil-Liste** mit umfangreichen Filtern:
  - Kategorie, Lieferant, Bestandswarnung
  - Textsuche (Bestellnummer, Bezeichnung, Beschreibung)
  - Sortierung nach verschiedenen Kriterien (ID, Bestellnummer, Kategorie, Bezeichnung, Lieferant, Bestand, Lagerort, Lagerplatz)
  - Direkt zu Angebotsanfrage hinzufügen (Button in Liste)
- **Ersatzteil-Detailansicht**:
  - Vollständige Informationen (Bestellnummer editierbar, Bezeichnung, Hersteller, Preis mit Preisstand, Währung, Lagerort, Lagerplatz)
  - Bestandsanzeige mit Mindestbestand und Warnung
  - End-of-Life und Nachfolgeartikel-Verwaltung
  - Kennzeichen (A-Z) für Kategorisierung
  - Bilder und Dokumente hochladen/verwalten
  - Abteilungsbasierte Zugriffsrechte
  - Smart-Add zu Angebotsanfrage mit Toast-Benachrichtigung
- **Lagerbuchungen**:
  - Übersicht aller Lagerbuchungen mit Filtern (Ersatzteil, Typ, Kostenstelle, Datum)
  - Eingang, Ausgang und Inventur
  - Automatische Bestandsaktualisierung
  - Preis- und Währungserfassung pro Buchung
  - Verknüpfung mit Schichtbuch-Themen
  - Schnellbuchung durch Eingabe der Ersatzteil-ID
- **Thema-Verknüpfung**:
  - Ersatzteile direkt mit Schichtbuch-Themen verknüpfen
  - Automatische Lagerbuchung (Ausgang) bei Verknüpfung
- **Lieferanten-Verwaltung**:
  - Lieferanten-Liste mit Kontaktdaten
  - Detailansicht mit zugehörigen Ersatzteilen
  - Adressverwaltung (Straße, PLZ, Ort)
- **Berechtigungen**:
  - Abteilungsbasierte Zugriffsrechte für Ersatzteile
  - Administratoren haben vollen Zugriff
  - Nur Administratoren können Ersatzteile anlegen/bearbeiten/löschen

### Admin-Bereich
- **Mitarbeiter-Verwaltung** - Anlegen, Bearbeiten, Passwort zurücksetzen, Email und Handynummer
- **Berechtigungs-Verwaltung** - Flexible Rechtevergabe pro Mitarbeiter
  - Admin, Artikel buchen, Bestellungen erstellen/freigeben
  - Checkboxen für schnelle Zuweisung
  - Erweiterbar für zukünftige Berechtigungen
- **Abteilungs-Verwaltung** - Hierarchische Struktur
- **Stammdaten-Verwaltung** - Bereiche, Gewerke, Status, Tätigkeiten
- **Ersatzteil-Stammdaten** - Kategorien, Kostenstellen, Lagerorte, Lagerplätze, Lieferanten
- **Firmendaten** - Verwaltung von Firmendaten für PDF-Export (Adresse, Lieferanschrift, Kontakt, Logo, Bankverbindung)
- **Datenbank-Check** - Überprüfung und Reparatur der Datenbankstruktur
- **Login-Logs** - Übersicht aller Login-Versuche mit Filterung

### Technische Features
- **AJAX-Unterstützung** für dynamische Updates
- **Responsive Design** - Mobile Navigation mit Hamburger-Menü
- **PWA-Unterstützung** - Installierbar als Web-App

## 🛠️ Entwicklung

### Debug-Modus aktivieren
- Windows (PowerShell):
```powershell
$env:FLASK_DEBUG="True"
flask --app app run
```
- Windows (CMD):
```cmd
set FLASK_DEBUG=True
flask --app app run
```
- Linux/Mac:
```bash
export FLASK_DEBUG=True
flask --app app run
```

Hinweis: Debug-Modus ist **ausschließlich** für die lokale Entwicklung
bestimmt. In Produktion (`FLASK_ENV=production`) darf er nicht aktiviert
werden.

### SQL-Tracing aktivieren
- Windows (PowerShell):
```powershell
$env:SQL_TRACING="True"
flask --app app run
```
- Windows (CMD):
```cmd
set SQL_TRACING=True
flask --app app run
```
- Linux/Mac:
```bash
export SQL_TRACING=True
flask --app app run
```

## 📝 Changelog

### Version 1.6 (Aktuell)
- ✅ **UI-Verbesserungen Tabellen** - Einheitliches Design für alle Tabellen
  - Themen-Tabelle: Card-Wrapper, table-responsive, table-hover hinzugefügt
  - Hover-Effekt bei Bemerkungszeilen entfernt
  - Themenzeile klickbar gemacht
- ✅ **Auge-Button entfernt** - Redundante "Details anzeigen"-Buttons entfernt
  - Entfernt aus: Themen, Angebotsanfragen, Bestellungen, Wareneingang, Ersatzteile, Lieferanten
  - Zeilen sind jetzt klickbar und führen direkt zur Detailseite
- ✅ **Lieferanten-Verbesserungen**
  - Lieferanten-Zeilen klickbar gemacht
  - In Lieferanten-Detail: ErsatzteilID-Spalte am Anfang hinzugefügt und verlinkt
- ✅ **Inventurliste Filter** - Filter für Lagerort und Lagerplatz hinzugefügt
  - Einklappbarer Filter-Bereich
  - Kombinierbare Filter
  - Zurücksetzen-Button

### Version 1.5
- ✅ **Berechtigungssystem** - Flexibles, tabellen-basiertes Rechtesystem
  - Admin-Berechtigung für vollständigen Zugriff
  - Artikel-Buchungs-Berechtigung für Lagerbewegungen
  - Bestellungs-Berechtigungen vorbereitet (erstellen/freigeben)
  - Verwaltung direkt im Admin-Bereich
- ✅ **Artikel-Vorlage** - Neue Artikel aus bestehenden erstellen
  - Suchfeld mit Autocomplete auf "Neuer Artikel"-Seite
  - Button "Als Vorlage verwenden" auf Detail-Seite
  - Alle Daten werden automatisch übernommen
- ✅ **Admin-UI verbessert** - Übersichtliche Accordion-Struktur
  - Stammdaten, Abteilungen und Berechtigungen in ausklappbaren Bereichen
  - Nur ein Bereich gleichzeitig geöffnet
  - Redundanter "Deaktivieren"-Button entfernt
- ✅ **Code-Bereinigung** - BIS-Admin Abteilungsprüfungen durch Berechtigungen ersetzt
- ✅ **Inventurliste** - Bestand-Feld optimiert (Schrittweite 1, kein Placeholder)

### Version 1.4
- ✅ **Bestellwesen** - Neuer Navigationsbereich für Angebotsanfragen
- ✅ **Angebotsanfragen** - Vollständiges Anfragewesen mit Status-Verwaltung
- ✅ **PDF-Export Angebotsanfragen** - Professioneller Geschäftsdokument-Stil
- ✅ **Firmendaten** - Verwaltung mit Logo, Lieferanschrift und Bankverbindung
- ✅ **Smart-Add zu Angebotsanfrage** - Intelligente Zuordnung zu bestehenden Anfragen
- ✅ **Position-Editor** - Angebotspositionen per Klick bearbeitbar
- ✅ **Artikel aus Position erstellen** - Neue Ersatzteile direkt aus Angebotsposition anlegen
- ✅ **Mitarbeiter Email/Handy** - Kontaktdaten für Mitarbeiter mit Anzeige im PDF
- ✅ **Bestellnummer bearbeitbar** - Ersatzteil-Bestellnummern können geändert werden
- ✅ **Preisstand-Verwaltung** - Automatische Aktualisierung bei Preisübernahme

### Version 1.3
- ✅ **Benutzerprofil** - Anzeige und Bearbeitung persönlicher Daten
- ✅ **PDF-Export** - Themen als PDF exportieren
- ✅ **Benachrichtigungssystem** - Toast-Benachrichtigungen und Badge-Anzeige
- ✅ **Passwort ändern** - Selbstständige Passwortänderung für Benutzer
- ✅ **Dashboard** - Übersicht mit Statistiken und Aktivitäten
- ✅ **Mobile Navigation** - Responsive Design mit Hamburger-Menü
- ✅ **Admin: Passwort zurücksetzen** - Passwort auf Vorname zurücksetzen
- ✅ **UI-Verbesserungen** - Bootstrap Icons für Speichern- und Löschen-Buttons im Admin-Bereich

### Version 1.2
- ✅ sbListeDetails: Infinite Scroll, neue Filter (Bereich, Gewerk, Status-Multi, Textsuche)
- ✅ sbThemaDetail: Tätigkeit pro Bemerkung, Inline-Bearbeitung eigener Bemerkungen

### Version 1.1
- ✅ Sicherheitsverbesserungen (Secret Key, Passwort-Hashing)
- ✅ Error Handling hinzugefügt
- ✅ Konfigurationsmanagement
- ✅ Context Manager für DB-Verbindungen
- ✅ Debug-Ausgaben entfernt

### Version 1.0
- Grundfunktionalität implementiert
- Schichtbuch-System
- Benutzerauthentifizierung

## 🐛 Bekannte Probleme

- Keine automatischen Tests implementiert

## 📞 Support

Bei Problemen oder Fragen wenden Sie sich an das Entwicklungsteam.

