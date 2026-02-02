# BIS – Docker-Anleitung für Windows 11

Anleitung, um das Betriebsinformationssystem (BIS) in einem Docker-Container unter **Windows 11** zu betreiben. Docker Desktop nutzt dabei WSL2 und führt Linux-Container aus.

## Inhaltsverzeichnis

1. [Voraussetzungen](#1-voraussetzungen)
2. [Docker Desktop installieren](#2-docker-desktop-installieren)
3. [Projekt vorbereiten](#3-projekt-vorbereiten)
4. [Container starten](#4-container-starten)
5. [Erster Zugriff und Admin-Login](#5-erster-zugriff-und-admin-login)
6. [Konfiguration (Umgebungsvariablen)](#6-konfiguration-umgebungsvariablen)
7. [Daten persistent speichern (Windows-Ordner)](#7-daten-persistent-speichern-windows-ordner)
8. [Alltägliche Befehle](#8-alltägliche-befehle)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Voraussetzungen

- **Windows 11** (64 Bit)
- **WSL2** (wird von Docker Desktop automatisch eingerichtet)
- **Administratorrechte** für die Installation von Docker Desktop
- **Internetverbindung** für den ersten Image-Build

### Hardware

- Mindestens **4 GB RAM** (8 GB empfohlen)
- Etwa **2 GB freier Speicherplatz** für Images und Volumes

---

## 2. Docker Desktop installieren

### Schritt 1: Docker Desktop herunterladen

1. Öffnen Sie [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/).
2. Laden Sie **Docker Desktop for Windows** herunter.
3. Führen Sie den Installer aus und folgen Sie den Anweisungen.
4. Starten Sie den PC bei Aufforderung neu.

### Schritt 2: WSL2 als Backend (Standard unter Windows 11)

- Bei der Installation wird in der Regel **WSL 2** als Backend verwendet.
- Falls Sie gefragt werden: Wählen Sie **WSL 2** statt Hyper-V.

### Schritt 3: Installation prüfen

1. **Docker Desktop** starten und warten, bis es vollständig hochgefahren ist (Whale-Symbol in der Taskleiste).
2. **PowerShell** oder **Eingabeaufforderung** öffnen und ausführen:

   ```powershell
   docker --version
   docker compose version
   ```

   Es sollten Versionsnummern ausgegeben werden (z. B. `Docker version 24.x` und `Docker Compose version v2.x`).

---

## 3. Projekt vorbereiten

### Projektordner öffnen

Im Projektordner von BIS (dort, wo `app.py`, `Dockerfile` und `docker-compose.yml` liegen):

```powershell
cd C:\Projekte\BIS\BIS
```

*(Pfad ggf. an Ihren Workspace anpassen.)*

### Optionale Umgebungsdatei `.env`

Für Produktion sollten Sie mindestens einen eigenen **SECRET_KEY** setzen. Dafür legen Sie im Projektordner eine Datei `.env` an:

1. Kopieren Sie `env_example.txt` nach `.env`:

   ```powershell
   Copy-Item env_example.txt .env
   ```

2. Öffnen Sie `.env` und passen Sie an:

   ```env
   SECRET_KEY=ihr-langer-zufaelliger-geheimer-schluessel
   FLASK_ENV=production
   ```

Ohne `.env` verwendet `docker-compose` den Platzhalter-SECRET_KEY aus der `docker-compose.yml` (nur für Tests geeignet).

---

## 4. Container starten

### Einmalig: Image bauen und starten

Im Projektordner (dort, wo `docker-compose.yml` liegt):

```powershell
docker compose up -d --build
```

- `--build` baut das Image beim ersten Mal (und bei Änderungen am Dockerfile/Code).
- `-d` startet die Container im Hintergrund.

Beim ersten Mal kann der Build einige Minuten dauern (Python, Abhängigkeiten, LibreOffice).

### Prüfen, ob der Container läuft

```powershell
docker compose ps
```

Der Service `bis` sollte mit Status **running** und Port **5000** angezeigt werden.

---

## 5. Erster Zugriff und Admin-Login

1. **Browser** öffnen und aufrufen: **http://localhost:5000**
2. Beim **ersten Start** legt die App automatisch die Datenbank und einen Admin-Benutzer an.
3. **Standard-Login** (nur beim ersten Mal bzw. wenn Sie die DB nicht manuell geändert haben):
   - **Personalnummer:** `99999`
   - **Passwort:** `a`
4. **Wichtig:** Ändern Sie das Passwort nach der ersten Anmeldung (z. B. unter Profil / Passwort ändern).

---

## 6. Konfiguration (Umgebungsvariablen)

Die wichtigsten Einstellungen werden über **Umgebungsvariablen** gesteuert. Sie können sie in der `docker-compose.yml` unter `environment:` setzen oder in einer `.env`-Datei im gleichen Ordner wie `docker-compose.yml` definieren.

### In `docker-compose.yml` (Beispiel)

```yaml
environment:
  FLASK_ENV: production
  SECRET_KEY: ${SECRET_KEY:-bitte-in-.env-aendern}
  DATABASE_URL: /data/database_main.db
  UPLOAD_BASE_FOLDER: /data/Daten
  # Zugriff über Hostname/IP (z. B. im Intranet)
  WEBAUTHN_ORIGIN: http://mein-pc:5000
  WEBAUTHN_RP_ID: mein-pc
```

### In `.env` (empfohlen für SECRET_KEY)

```env
SECRET_KEY=ihr-sicherer-geheimer-schluessel
```

Weitere Optionen (z. B. E-Mail, Benachrichtigungen) entnehmen Sie `config.py` und `env_example.txt`.

---

## 7. Daten persistent speichern (Windows-Ordner)

Standardmäßig speichert `docker-compose` Datenbank und Uploads in einem **Docker-Volume** (`bis-data`). So bleiben die Daten beim Neustart der Container erhalten.

Wenn Sie die Daten in einem **bestimmten Windows-Ordner** haben möchten (z. B. für Backups), können Sie ein **Bind-Mount** verwenden.

### Beispiel: Daten unter `C:\BIS-Daten`

1. Ordner anlegen:

   ```powershell
   New-Item -ItemType Directory -Path "C:\BIS-Daten" -Force
   ```

2. In `docker-compose.yml` den Volume-Eintrag des Services `bis` anpassen:

   **Vorher (Volume):**
   ```yaml
   volumes:
     bis-data:/data
   ```

   **Nachher (Bind-Mount unter Windows):**
   ```yaml
   volumes:
     C:\BIS-Daten:/data
   ```

3. Den Abschnitt `volumes: bis-data:` am Ende der Datei **entfernen** oder auskommentieren, wenn Sie kein named Volume mehr nutzen.

4. Container neu starten:

   ```powershell
   docker compose down
   docker compose up -d
   ```

Datenbank und Upload-Ordner liegen dann unter `C:\BIS-Daten` (im Container als `/data` gemountet).

---

## 8. Alltägliche Befehle

| Aktion              | Befehl |
|---------------------|--------|
| Container starten   | `docker compose up -d` |
| Container stoppen   | `docker compose down` |
| Logs anzeigen       | `docker compose logs -f bis` |
| Status prüfen       | `docker compose ps` |
| Neu bauen + starten | `docker compose up -d --build` |
| In Container shell  | `docker compose exec bis bash` |

### Beispiel: Logs live verfolgen

```powershell
docker compose logs -f bis
```

Beenden mit **Strg+C**.

### Beispiel: Shell im Container (z. B. für DB-Check)

```powershell
docker compose exec bis bash
# Im Container z. B.:
# ls -la /data
# exit
```

---

## 9. Troubleshooting

### „Docker läuft nicht“ / „Cannot connect to the Docker daemon“

- **Docker Desktop** starten und warten, bis es vollständig geladen ist.
- Prüfen: **Einstellungen → Resources → WSL Integration** – Integration für Ihre WSL-Distribution aktivieren, falls Sie aus WSL heraus arbeiten.

### Port 5000 bereits belegt

Wenn ein anderer Dienst Port 5000 nutzt, in `docker-compose.yml` einen anderen Host-Port verwenden:

```yaml
ports:
  - "8080:5000"
```

Dann BIS unter **http://localhost:8080** aufrufen.

### Container startet nicht (Exit-Code)

Logs prüfen:

```powershell
docker compose logs bis
```

Häufige Ursachen:

- Fehlende oder falsche Umgebungsvariablen (z. B. `DATABASE_URL`, `UPLOAD_BASE_FOLDER`).
- Zu wenig Speicher für Docker: unter **Docker Desktop → Settings → Resources** RAM/Platte erhöhen.

### PDF-Export (Berichte) funktioniert nicht

Im Image ist **LibreOffice** für die DOCX→PDF-Konvertierung enthalten. Wenn PDF-Export trotzdem fehlschlägt:

- Logs prüfen: `docker compose logs bis`
- Sicherstellen, dass der Container genug Speicher hat und keine temporären Schreibfehler auftreten.

### Datenbank zurücksetzen

**Achtung:** Alle Daten in der Datenbank gehen verloren.

1. Container stoppen: `docker compose down`
2. Volume löschen: `docker volume rm bis_bis-data` (Name ggf. mit `docker volume ls` prüfen)
3. Neu starten: `docker compose up -d`

Beim nächsten Start legt die App wieder eine leere DB und den Admin-Benutzer (99999 / a) an.

### Hilfe zu Docker-Befehlen

- [Docker Docs – Get started](https://docs.docker.com/get-started/)
- [Docker Compose – Dokumentation](https://docs.docker.com/compose/)

---

## Kurzreferenz

```powershell
# In den Projektordner wechseln
cd C:\Projekte\BIS\BIS

# .env anlegen (einmalig, für SECRET_KEY)
Copy-Item env_example.txt .env
# .env bearbeiten: SECRET_KEY setzen

# Container bauen und starten
docker compose up -d --build

# Im Browser öffnen
start http://localhost:5000

# Login (Standard nach Erststart): 99999 / a
```

Nach dem ersten Start können Sie BIS wie gewohnt im Browser unter **http://localhost:5000** nutzen.
