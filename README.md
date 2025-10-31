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

## 📁 Projektstruktur

```
BIS/
├── app.py                 # Hauptanwendung
├── config.py              # Konfiguration
├── templates/             # HTML-Templates
│   ├── layout/
│   ├── mitarbeiter/
│   ├── schichtbuch/
│   └── errors/
├── static/                # CSS/JS Dateien
├── env_example.txt        # Beispiel-Env
├── requirements.txt       # Python-Abhängigkeiten
└── database_main.db       # SQLite-Datenbank (Standard)
```

## 🔧 Funktionen

- **Benutzerauthentifizierung** mit Personalnummer
- **Schichtbuch-Verwaltung** mit Themen und Bemerkungen
- **Status-Tracking** (Offen, In Arbeit, Abgeschlossen)
- **Liste Details (sbListeDetails)**
  - Infinite Scroll: Laden in Seiten à 50 Einträgen
  - Filter (einklappbar):
    - Bereich und Gewerk (Gewerk dynamisch nach Bereich)
    - Status-Mehrfachauswahl
    - Textsuche in Bemerkungen
  - Bemerkungen werden nur für die angezeigten Themen geladen
- **Thema-Details**
  - Tätigkeit wird pro Bemerkung angezeigt
  - Eigene Bemerkungen können inline bearbeitet werden (Text und Tätigkeit)
- **AJAX-Unterstützung** für dynamische Updates

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

### Version 1.2 (Aktuell)
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

