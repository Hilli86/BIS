# BIS - Betriebsinformationssystem

Modulare Flask-Anwendung mit Blueprints für Schichtbuch, Ersatzteile/Bestellwesen,
Wartungen, Produktion und administrative Aufgaben. Optimiert für den Einsatz in
einem Werkstatt-/Produktionsumfeld inkl. Etikettendruck (Zebra), PDF/DOCX-Berichten
und Web-Push-Benachrichtigungen.

## 🚀 Schnellstart

### Voraussetzungen
- Python 3.11+
- pip
- **LibreOffice** (für DOCX→PDF-Konvertierung von Bestellungen, Angebotsanfragen, Berichten)
  - Linux: `sudo apt-get install libreoffice-writer libreoffice-common`
  - Windows: Download von [libreoffice.org](https://www.libreoffice.org/download/) – alternativ wird unter Windows auch MS Word über `docx2pdf` genutzt
  - macOS: `brew install --cask libreoffice`

### Installation

1. **Repository klonen:**
```bash
git clone <repository-url>
cd BIS
```

2. **Virtuelle Umgebung erstellen und aktivieren:**
```bash
python -m venv .venv
```
- Windows (PowerShell): `./.venv/Scripts/Activate.ps1`
- Windows (CMD): `.venv\Scripts\activate`
- Linux/Mac: `source .venv/bin/activate`

3. **Abhängigkeiten installieren:**
```bash
pip install -r requirements.txt
```

4. **Umgebungsvariablen konfigurieren:**
Erstellen Sie eine `.env` basierend auf `env_example.txt` und passen Sie
mindestens `SECRET_KEY`, `DATABASE_URL` und `UPLOAD_BASE_FOLDER` an.
Für **Docker Compose** eignet sich `env_docker_example.txt` als Vorlage (u.a. Hinweise zu `SECRET_KEY`, WebAuthn hinter Nginx und optional Mail/VAPID).

5. **Datenbank:**
- Standard-Datei ist `database_main.db` (Pfad konfigurierbar über `DATABASE_URL`).
- Beim ersten App-Start werden fehlende Tabellen, Spalten und Indizes
  automatisch angelegt (siehe `utils/database_check.py`).
- Optional kann die Datenbank vorab mit `python scripts/init_database.py`
  initialisiert werden – siehe Abschnitt **Initial-Admin** unten.

6. **Anwendung starten:**

Lokale Entwicklung (Flask-Dev-Server):
```bash
flask --app app run
```
- Debug-Modus optional über `FLASK_DEBUG=True` aktivieren.
- Host/Port lassen sich per `--host 0.0.0.0 --port 5000` setzen oder über
  die Umgebungsvariablen `BIS_DEV_HOST`/`BIS_DEV_PORT` beim direkten
  `python app.py`-Start.

Produktion (Gunicorn hinter Reverse-Proxy, z. B. nginx):
```bash
gunicorn -c gunicorn_config.py app:app
```
- Worker/Threads konfigurierbar per `GUNICORN_WORKERS` (Default 2) und
  `GUNICORN_THREADS` (Default 4). Die mitgelieferte `gunicorn_config.py`
  nutzt `preload_app=True`, damit Startup-Tasks (Alembic-Migration,
  Benachrichtigungs-Cleanup, Nachversand) nur einmal im Master laufen.
- Bei mehreren Workern zwingend einen geteilten Rate-Limiter-Store setzen:
  `RATELIMIT_STORAGE_URI=redis://<host>:6379/0`. Im Docker-Compose-Stack
  ist ein `Redis-Service` bereits enthalten.
- `python app.py` bzw. Debug-Modus sind **nicht** für den produktiven
  Betrieb gedacht.
- Siehe `deployment/bis.service`, `docker/bis.Dockerfile` und `docker-compose.yml` für fertige Setups.

Die Anwendung ist dann unter `http://localhost:5000` (Dev) bzw. der vom
Reverse-Proxy bereitgestellten URL erreichbar.

## 🔐 Initial-Admin

Bei einer **leeren Datenbank** (kein Mitarbeiter vorhanden) wird einmalig
ein Admin-Benutzer angelegt:

- **Personalnummer:** `99999`
- **Name:** BIS-Admin (Primär-Abteilung „BIS-Admin", erhält automatisch die
  Berechtigung `admin`).
- **Passwort:** wird **zufällig** mit `secrets.token_urlsafe(18)` erzeugt
  und einmalig ausgegeben:
  - beim Aufruf von `python scripts/init_database.py` direkt im Terminal in einer
    auffälligen Banner-Box (`stdout`),
  - beim normalen App-Start zusätzlich als `WARNING`-Eintrag des Loggers
    `bis.init` (in der Konsole bzw. im Service-Log).
- **Wechsel-Zwang:** Beim ersten Login wird der Admin zur Passwort-Änderung
  geführt (`PasswortWechselErforderlich = 1`); ein Weiterarbeiten ist erst
  nach dem Setzen eines neuen Passworts möglich.

> **Wichtig:** Das Initial-Passwort wird **nicht** persistent gespeichert oder
> erneut ausgegeben. Geht es verloren, muss das Passwort direkt in der
> Datenbank (Tabelle `Mitarbeiter`, Spalte `Passwort` via
> `werkzeug.security.generate_password_hash`) zurückgesetzt werden – oder ein
> vorhandener Admin setzt es über die Admin-Oberfläche neu.

Wenn bereits Mitarbeiter existieren, wird **kein** zusätzlicher Admin
automatisch angelegt. Admin-Rechte können nachträglich über die
Admin-Seite vergeben werden.

## ⚙️ Konfiguration

### Umgebungsvariablen (`.env`)

```env
# Pflicht
FLASK_ENV=development           # development | production
SECRET_KEY=<mind. 32 Zeichen, kein Platzhalter>
DATABASE_URL=database_main.db

# Optional / empfohlen
UPLOAD_BASE_FOLDER=C:\Pfad\zu\Daten   # Basisordner für Uploads
SQL_TRACING=False                     # SQL-Statements im Log mitschreiben
SESSION_COOKIE_SECURE=true            # bei HTTPS-Betrieb auf true
REMEMBER_COOKIE_SECURE=true

# Web-Push (VAPID)
# Erzeugen: flask --app app vapid-generate
# Prüfen:    flask --app app vapid-verify
VAPID_PRIVATE_KEY=C:\Pfad\BIS\instance\vapid_private.pem
VAPID_PUBLIC_KEY=<base64 url-safe>
VAPID_EMAIL=admin@example.com
```

In **Produktion** (`FLASK_ENV=production`) verweigert die App den Start, wenn
kein ausreichend starker `SECRET_KEY` gesetzt ist (siehe `app.py`,
`_validate_secret_key`).

### Produktions-Deployment

Vorbereitete Setups und Anleitungen liegen unter `deployment/` und `docs/`:

- `docker-compose.yml` und Ordner `docker/` (`bis.Dockerfile`, `nginx.Dockerfile`, `nginx.docker.conf`) – Container-Setup mit Gunicorn + LibreOffice und TLS-Proxy (Nginx)
- `deployment/bis.service` – systemd-Unit für Linux
- `deployment/install_server.sh`, `deployment/update_app.sh`, `deployment/backup_bis.sh`
- `deployment/nginx_bis*.conf` – nginx-Konfigurationen (HTTP / HTTPS / Self-Signed)
- `docs/DEPLOYMENT_GUIDE.md`, `docs/SCHNELLSTART_DEPLOYMENT.md`, `docs/HOSTING_OPTIONEN.md`,
  `docs/DEPLOYMENT_ÜBERSICHT.md`, `docs/PROXMOX_EINRICHTUNG.md`

## 📁 Projektstruktur

```
BIS/
├── app.py                    # Flask-App, Blueprint-Registrierung, CLI-Befehle
├── config.py                 # Konfigurations-Klassen (development/production)
├── requirements.txt
├── docker-compose.yml
├── docker/                   # bis.Dockerfile, nginx.Dockerfile, nginx.docker.conf (Compose; ausserhalb deployment/)
├── modules/                  # Blueprints
│   ├── auth/                 # Login, Profil, Passwort, WebAuthn
│   ├── dashboard/            # Startseite mit KPIs
│   ├── schichtbuch/          # Themen, Bemerkungen, Aufgabenlisten
│   ├── ersatzteile/          # Artikel, Lager, Bestellwesen, Auswertungen
│   ├── wartungen/            # Wartungspläne, Durchführungen, Jahresübersicht
│   ├── produktion/           # Etikettierung, Etiketten drucken
│   ├── diverses/             # Zebra-Drucker, Dokumente erfassen
│   ├── search/               # Globale Suche
│   ├── import/               # CSV-/Daten-Import
│   ├── admin/                # Stammdaten, Berechtigungen, Login-Logs
│   └── errors/               # 4xx/5xx-Handler
├── utils/                    # Querschnitts-Utilities
│   ├── database*.py          # Verbindungs-Pool, Schema-Init, Health-Check
│   ├── security*.py          # CSRF, Talisman/CSP, Rate-Limiting, Header
│   ├── reports/              # PDF-/DOCX-Erzeugung (docxtpl + LibreOffice)
│   ├── benachrichtigungen*.py# E-Mail/Push/Toast-Pipeline
│   ├── vapid_setup.py        # VAPID-Schlüssel-Erzeugung/-Prüfung
│   └── ...
├── templates/                # Globale Layouts und Fehlerseiten
├── static/                   # CSS/JS/Icons, Service Worker
├── deployment/               # systemd/nginx/Skripte fuer Server-Deployments
├── docs/                     # Tiefer gehende Anleitungen
└── scripts/                  # Hilfsskripte (z. B. init_database.py)
```

## 🔧 Funktionen

### Benutzer & Konto
- Login per Personalnummer + Passwort, optional **WebAuthn/Passkeys** (FIDO2)
- **Profil** mit Kontaktdaten (E-Mail, Handynummer)
- Selbst-Service: Passwort ändern, Push-Subscription verwalten
- **Erzwungene Passwort-Änderung** beim ersten Login (Initial-Admin oder Reset)
- Dashboard mit Statistiken, KPIs (inkl. Wartungsfälligkeiten) und Modul-Karten

### Schichtbuch
- **Themenliste** mit Infinite Scroll, einklappbarem Filter (Bereich, Gewerk,
  Status-Mehrfachauswahl, Volltextsuche)
- Themen mit optionalen **Zusatz-Gewerken** und Sichtbarkeits-Steuerung pro Abteilung
- **Thema-Detail**: Bemerkungen mit Tätigkeit, Inline-Bearbeitung eigener
  Einträge, Datei-Upload, QR-Code-Generierung, **PDF-Export inkl. Foto-Anhängen**
- **Aufgabenlisten**: gruppieren mehrere Themen für definierte Mitarbeiter/
  Abteilungen, mit Sortierung, Archivierung, Duplizieren und gezielter Sichtbarkeit
- Status-Tracking (Offen / In Arbeit / Abgeschlossen) und Tätigkeiten pro Bemerkung
- Optionale **Lager-Rückbuchung** beim Löschen eines Themas

### Bestellwesen
- **Angebotsanfragen** an Lieferanten mit mehreren Positionen, Status-Workflow
  (Offen → Versendet → Angebot erhalten → Abgeschlossen)
  - Smart-Add: prüft auf bestehende offene Anfragen pro Lieferant
  - PDF-Upload erhaltener Angebote, Preisübernahme mit automatischer Preisstand-Aktualisierung
  - Inline-Bearbeitung von Positionen, Anlegen neuer Artikel direkt aus einer Position
  - **PDF-Export** im Geschäftsdokument-Stil (LibreOffice oder MS Word) +
    **DOCX-Export** als Alternative
- **Bestellungen** mit Freigabe-Workflow, PDF-/DOCX-Export und Druckbericht
- **Wareneingang buchen**: bestellungs- bzw. positionsweises Einbuchen mit
  automatischer Lagerbuchung
- **Auswertungen** über Zeiträume, Lieferanten und Abteilungs-Hierarchien
  (rekursive Aggregation über Unter-Abteilungen)

### Ersatzteile / Lager
- **Artikelliste** mit Filtern (Kategorie, Lieferant, Bestandswarnung), Suche
  und konfigurierbarer Sortierung; mobiles Card-Layout mit Artikelfoto
- **Artikel-Detail**: Stammdaten (inkl. Preis/Preisstand/Währung), Lagerort/-platz,
  Mindestbestand, End-of-Life + Nachfolgeartikel, Kennzeichen, Bilder/Dokumente
- **Suche Artikel**: schneller Zugriff über Bestellnummer/Bezeichnung/Hersteller
- **Lieferanten-Verwaltung** inkl. Detailseite mit zugeordneten Artikeln
- **Lagerbuchungen** (Eingang, Ausgang, Inventur) mit Filtern, Schnellbuchung
  per Artikel-ID und Verknüpfung zu Schichtbuch-/Wartungs-Vorgängen
- **Inventurliste** mit eigenem Filter (Lagerort/Lagerplatz)
- **Etiketten drucken** für Artikel (Zebra-ZPL, Vorschau, Vorlagen-Auswahl)

### Wartungen
- **Wartungs-Stammsätze** je Bereich/Gewerk mit Berechtigungs-Steuerung
- **Wartungspläne** mit festem Intervall (oder ohne Fälligkeit bei Intervall 0)
  und Anzeige der letzten Durchführung
- **Durchführungen** einzeln oder als **Mehrfach-Protokoll** für mehrere Pläne
  in einem Vorgang, inkl. verbrauchter Artikel und Service-Berichten
- **Angebote/Kosten** pro Durchführung verknüpfbar
- **Jahresübersicht** mit Fälligkeits-Ampel und direkter Protokollierung
- **Chronologische Protokoll-Liste**, sortierbar
- Datei-Upload zu Wartungen und Durchführungen (Service-Berichte etc.)

### Produktion / Diverses
- **Etikettierung**: Übersicht der Artikeleinstellungen je Linie aus
  Ordner-Struktur, mit Bildern
- **Etiketten drucken**: konfigurierbare Vorlagen, Platzhalter, Druck-Konfigs
- **Zebra-Drucker**: zentrale Druckerliste, Kalibrieren, Testdruck
- **Dokumente erfassen**: Aufnahme per Kamera + Zuschneiden, Ablage im Import-Ordner

### Benachrichtigungen
- **In-App-Toasts** und Badge in der Navigation für ungelesene Nachrichten
- **Web-Push** über Service Worker + VAPID
  (CLI: `flask --app app vapid-generate`, `vapid-verify`, `push-test`)
- E-Mail-Pipeline für Schichtbuch-Themen (mit konfigurierbarer Empfängerlogik)
- Automatische Bereinigung alter Benachrichtigungen beim App-Start

### Globale Suche & Navigation
- **Globale Suche** über Themen, Artikel, Bestellungen, Wartungen u. a.
- **Navigationsverlauf** in der Session: Breadcrumb + Zurück-Button
  (Endpoint `/bis/nav/zurueck`)
- Sidebar mit modulbasierter Sichtbarkeitssteuerung pro Mitarbeiter

### Admin-Bereich
- **Mitarbeiter-Verwaltung** (Anlegen, Bearbeiten, Deaktivieren,
  Passwort zurücksetzen, E-Mail/Handynummer)
- **Berechtigungs-Verwaltung** (Tabellen-basiert, beliebig erweiterbar):
  Admin, Artikel buchen, Bestellungen erstellen/freigeben, Wartung anlegen,
  Gewerk am Thema ändern, Zebra-Drucker u. a.
- **Abteilungen** (hierarchisch) und Mitarbeiter-Abteilungs-Zuordnung
- **Stammdaten**: Bereiche, Gewerke, Status, Tätigkeiten, Kategorien,
  Kostenstellen, Lagerorte, Lagerplätze, Lieferanten
- **Firmendaten** für Berichte (Adresse, Lieferanschrift, Kontakt, Logo, Bankverbindung)
- **Zebra**: Drucker-Liste, Etikettenformate, Druckkonfigurationen, Testdruck
- **Login-Logs** mit Filterung
- **Datenbank-Check** über UI

## 🔐 Sicherheits-Härtung

Die App ist auf direkten Online-Betrieb hinter Reverse-Proxy ausgelegt:

- **CSRF-Schutz** für alle State-Changing-Requests (Flask-WTF, globaler `csrf`)
- **Content-Security-Policy** + weitere Header über **Flask-Talisman**
  (`utils/security_headers.py`); HSTS automatisch in Produktion
- **Rate-Limiting** über `flask-limiter` (konkrete Limits per Dekorator,
  z. B. Login)
- **ProxyFix** für korrekte Erkennung von HTTPS, Host und Client-IP hinter nginx
- **Session-Cookies** `HttpOnly`, `Secure` (wenn HTTPS), `SameSite`
- **Passwort-Hashing** über Werkzeug; **Initial-Admin** ohne Default-Passwort
- **WebAuthn/Passkeys** als zweiter/erster Faktor möglich (`fido2`)
- **Path-Traversal-Schutz** beim Datei-Download (Wartungen, Berichte, Uploads)
- **CSS-Color-Sanitizing** für Templates (`safe_color`-Filter)
- **SECRET_KEY-Validierung**: kein Start in Produktion mit Default/Platzhalter

## 🛠️ Entwicklung

### Debug-Modus aktivieren
- Windows (PowerShell): `$env:FLASK_DEBUG="True"; flask --app app run`
- Windows (CMD): `set FLASK_DEBUG=True && flask --app app run`
- Linux/Mac: `FLASK_DEBUG=True flask --app app run`

> Debug-Modus ist **ausschließlich** für die lokale Entwicklung bestimmt.
> In Produktion (`FLASK_ENV=production`) darf er nicht aktiviert werden.

### SQL-Tracing aktivieren
- Variable `SQL_TRACING=True` setzen, App neu starten.

### Tests ausführen
```bash
pytest
```

### Nützliche CLI-Befehle (Flask)
```bash
flask --app app vapid-generate            # VAPID-Schlüssel für Web-Push erzeugen
flask --app app vapid-verify              # VAPID-Schlüssel-Paar prüfen
flask --app app push-test <mitarbeiter_id># Test-Push an Mitarbeiter senden
```

## 🐛 Bekannte Einschränkungen

- Tests decken bisher nur einzelne Bereiche ab; Flächendeckung wird ausgebaut.
- DOCX→PDF benötigt LibreOffice (Linux/Docker/macOS) oder MS Word (Windows via `docx2pdf`).

## 📞 Support

Bei Problemen oder Fragen wenden Sie sich an das Entwicklungsteam.
