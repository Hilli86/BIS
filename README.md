# BIS - Betriebsinformationssystem

Ein Flask-basiertes Schichtbuch-System für die Verwaltung von Arbeitsaufträgen und Bemerkungen.

## 🚀 Schnellstart

### Voraussetzungen
- Python 3.8+
- pip

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
```bash
python app.py
```

Die Anwendung ist dann unter `http://localhost:5000` erreichbar.

## 🔐 Standard-Login

- **Personalnummer:** 1001
- **Passwort:** pass123

oder

- **Personalnummer:** 1002  
- **Passwort:** pass123

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

### Ersatzteile-Verwaltung
- **Ersatzteil-Liste** mit umfangreichen Filtern:
  - Kategorie, Lieferant, Bestandswarnung
  - Textsuche (Artikelnummer, Bezeichnung, Beschreibung)
  - Sortierung nach verschiedenen Kriterien (ID, Artikelnummer, Kategorie, Bezeichnung, Lieferant, Bestand, Lagerort, Lagerplatz)
- **Ersatzteil-Detailansicht**:
  - Vollständige Informationen (Artikelnummer, Bezeichnung, Hersteller, Preis, Währung, Lagerort, Lagerplatz)
  - Bestandsanzeige mit Mindestbestand und Warnung
  - End-of-Life und Nachfolgeartikel-Verwaltung
  - Kennzeichen (A-Z) für Kategorisierung
  - Bilder und Dokumente hochladen/verwalten
  - Abteilungsbasierte Zugriffsrechte
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
- **Mitarbeiter-Verwaltung** - Anlegen, Bearbeiten, Passwort zurücksetzen
- **Abteilungs-Verwaltung** - Hierarchische Struktur
- **Stammdaten-Verwaltung** - Bereiche, Gewerke, Status, Tätigkeiten
- **Ersatzteil-Stammdaten** - Kategorien, Kostenstellen, Lagerorte, Lagerplätze, Lieferanten
- **Datenbank-Check** - Überprüfung und Reparatur der Datenbankstruktur

### Technische Features
- **AJAX-Unterstützung** für dynamische Updates
- **Responsive Design** - Mobile Navigation mit Hamburger-Menü
- **PWA-Unterstützung** - Installierbar als Web-App

## 🛠️ Entwicklung

### Debug-Modus aktivieren
- Windows (PowerShell):
```powershell
$env:FLASK_DEBUG="True"
python app.py
```
- Windows (CMD):
```cmd
set FLASK_DEBUG=True
python app.py
```
- Linux/Mac:
```bash
export FLASK_DEBUG=True
python app.py
```

### SQL-Tracing aktivieren
- Windows (PowerShell):
```powershell
$env:SQL_TRACING="True"
python app.py
```
- Windows (CMD):
```cmd
set SQL_TRACING=True
python app.py
```
- Linux/Mac:
```bash
export SQL_TRACING=True
python app.py
```

## 📝 Changelog

### Version 1.3 (Aktuell)
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

- Datenbank-Schema muss bei Updates manuell migriert werden (siehe SQL-Datei `sql_befehle`)
- Keine automatischen Tests implementiert

## 📞 Support

Bei Problemen oder Fragen wenden Sie sich an das Entwicklungsteam.

