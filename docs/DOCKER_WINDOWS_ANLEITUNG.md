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
9. [App von GitHub aktualisieren](#9-app-von-github-aktualisieren)
10. [Optional: HTTPS (selbstsigniert) und Cloudflare Tunnel](#10-optional-https-selbstsigniert-und-cloudflare-tunnel)
11. [Troubleshooting](#11-troubleshooting)

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

Im Projektordner von BIS (dort, wo `app.py`, `docker-compose.yml` und `docker/bis.Dockerfile` liegen):

```powershell
cd C:\Projekte\BIS\BIS
```

*(Pfad ggf. an Ihren Workspace anpassen.)*

### Optionale Umgebungsdatei `.env`

Für Produktion sollten Sie mindestens einen eigenen **SECRET_KEY** setzen. Dafür legen Sie im Projektordner eine Datei `.env` an:

1. Kopieren Sie die Docker-Vorlage nach `.env` (empfohlen für Compose):

   ```powershell
   Copy-Item env_docker_example.txt .env
   ```

   Alternativ allgemeine Vorlage: `Copy-Item env_example.txt .env` – dann `FLASK_ENV` und Pfade aus der Datei ignorieren; im Container setzt `docker-compose.yml` bereits `FLASK_ENV=production` und die Datenpfade unter `/data`. Für Compose müssen Sie zusätzlich die **Host-Pfade** `BIS_DATA_HOST`, `BIS_BACKUP_PLAIN_HOST` und `BIS_BACKUP_ENCRYPTED_HOST` setzen (siehe Kommentare in `env_docker_example.txt`).

2. Öffnen Sie `.env` und setzen Sie mindestens einen starken **SECRET_KEY** (mind. 32 Zeichen), die **BIS_*-Hostpfade** und **BACKUP_ENCRYPTION_PASSWORD** wie in `env_docker_example.txt` beschrieben. Ohne gültigen `SECRET_KEY` bricht `docker compose` beim Start mit einer Fehlermeldung ab (`${SECRET_KEY:?}` in der Compose-Datei).

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

Der Service `Application-Service` sollte mit Status **running** und Port **5000** angezeigt werden.

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

2. In `docker-compose.yml` den Volume-Eintrag des Services `Application-Service` anpassen:

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
| Logs anzeigen (App) | `docker compose logs -f Application-Service` |
| Logs anzeigen (Nginx) | `docker compose logs -f Proxy-Service` |
| Status prüfen       | `docker compose ps` |
| Neu bauen + starten | `docker compose up -d --build` |
| App-Code von GitHub holen | siehe [Abschnitt 9](#9-app-von-github-aktualisieren) |
| In Container shell  | `docker compose exec Application-Service bash` |

### Beispiel: Logs live verfolgen

```powershell
docker compose logs -f Application-Service
```

Beenden mit **Strg+C**.

### Beispiel: Shell im Container (z. B. für DB-Check)

```powershell
docker compose exec Application-Service bash
# Im Container z. B.:
# ls -la /data
# exit
```

---

## 9. App von GitHub aktualisieren

Der Anwendungscode wird beim **Image-Build** in den Container übernommen (`COPY` in `docker/bis.Dockerfile`), nicht als Live-Ordner vom Windows-Host eingebunden. Nach einem Update des Repositories auf der Festplatte müssen Sie das Image deshalb **neu bauen** und den Container **neu starten**.

**Datenbank und Uploads** liegen im Docker-Volume `bis-data` und bleiben bei diesem Vorgang in der Regel **erhalten** (siehe auch [Abschnitt 7](#7-daten-persistent-speichern-windows-ordner)).

### Voraussetzung

- **Git für Windows** ist installiert ([Download](https://git-scm.com/download/win)) und das Projekt wurde mit `git clone` aus GitHub geholt (nicht nur als ZIP entpackt).

### Schritte (PowerShell)

1. In den **Projektordner** wechseln (gleicher Ordner wie bei [Abschnitt 3](#3-projekt-vorbereiten), dort wo `docker-compose.yml` liegt):

   ```powershell
   cd C:\Projekte\BIS\BIS
   ```

   *(Pfad an Ihren Klon anpassen.)*

2. **Optional:** Prüfen, ob lokale Änderungen im Weg sind:

   ```powershell
   git status
   ```

   Wenn Dateien geändert sind, entweder committen, verwerfen oder mit `git stash` beiseite legen, sonst kann `git pull` abbrechen oder Konflikte melden.

3. **Neuesten Stand von GitHub holen** (Standard-Branch ist meist `main`):

   ```powershell
   git pull origin main
   ```

   Ist der Upstream-Branch bereits eingerichtet, reicht oft:

   ```powershell
   git pull
   ```

4. **Image neu bauen und Container aktualisieren:**

   ```powershell
   docker compose up -d --build
   ```

   Damit wird das Image mit dem aktuellen Code neu gebaut; der laufende `Application-Service`-Container wird durch die neue Version ersetzt.

5. **Prüfen:** Browser wie gewohnt aufrufen (z. B. **http://localhost:5000**), bei Bedarf Logs ansehen: `docker compose logs -f Application-Service`.

### Kurzfassung

```powershell
cd C:\Projekte\BIS\BIS
git pull
docker compose up -d --build
```

---

## 10. Optional: HTTPS (selbstsigniert) und Cloudflare Tunnel

BIS im Docker-Container spricht standardmäßig nur **HTTP** auf Port **5000** (`http://localhost:5000`). Für **HTTPS im Browser** oder **Zugriff aus dem Internet ohne Router-Freigabe** gibt es zwei gängige Wege:

| Variante | Typisch für | Kurzbeschreibung |
|----------|-------------|------------------|
| **Selbstsigniertes SSL** | Intranet, feste IP/Hostname im LAN | **Nginx für Windows** terminiert HTTPS und leitet an `http://127.0.0.1:5000` weiter (BIS bleibt im Container). |
| **Cloudflare Tunnel** | Öffentliche Domain, kein Port an der Firewall | **cloudflared** auf Windows verbindet Ihre Domain mit dem lokalen BIS (meist `http://localhost:5000`). SSL endet bei Cloudflare. |

In beiden Fällen sollten Sie in `docker-compose.yml` bzw. `.env` **`WEBAUTHN_ORIGIN`** und **`WEBAUTHN_RP_ID`** auf die URL setzen, die Nutzer im Browser öffnen (Schema `https://`, ohne Pfad; `WEBAUTHN_RP_ID` ist der Hostname **ohne** Port). Anschließend Container neu starten: `docker compose up -d`. Details zu den Variablen: `config.py`, `env_example.txt`.

---

### 10.1 Variante A: Selbstsigniertes SSL mit Nginx (Windows)

Der Container ändert sich dabei nicht: Nginx übernimmt TLS und spricht mit BIS nur per HTTP auf dem Host-Port.

1. **Nginx für Windows** installieren und Ordner für Zertifikate anlegen (Schritte und Pfade wie in [WINDOWS_DEPLOYMENT_GUIDE.md](WINDOWS_DEPLOYMENT_GUIDE.md), Abschnitte **5** und **6**). Zielverzeichnis für Zertifikat und Key z. B. `C:\nginx\conf\ssl\bis\`.

2. **Zertifikat erzeugen** (Hostname oder Intranet-IP; das Skript setzt die SANs passend zu IP oder DNS):
   - Im **Projektordner** (Git-Klon), z. B.:

     ```powershell
     cd C:\Projekte\BIS\BIS
     .\scripts\create_self_signed_cert_windows.ps1 -ServerName "192.168.1.100"
     # oder: .\scripts\create_self_signed_cert_windows.ps1 -ServerName "bis-pc.local"
     ```

   - Das Skript legt **`bis.crt`** und **`bis.key`** unter **`C:\nginx\conf\ssl\bis`** ab (Ordner wird angelegt). OpenSSL muss installiert und im `PATH` sein; Alternativen: [WINDOWS_DEPLOYMENT_GUIDE.md](WINDOWS_DEPLOYMENT_GUIDE.md) Abschnitt **6**.

3. **Nginx-`server`-Block für BIS (Docker):** Statt Waitress auf Port 8000 leiten Sie auf den **Docker-Host-Port** von BIS weiter (**5000**, sofern Sie `ports: "5000:5000"` in `docker-compose.yml` nutzen). Statische Dateien und Uploads kommen aus dem Container; Sie müssen **nicht** die `alias`-Pfade aus der Waitress-Anleitung (`C:/BIS/static`, …) übernehmen, wenn alles über den Proxy läuft.

   Beispiel **HTTPS → BIS im Docker** (Pfade und `server_name` anpassen):

   ```nginx
   server {
       listen 443 ssl http2;
       server_name 192.168.1.100;

       ssl_certificate     C:/nginx/conf/ssl/bis/bis.crt;
       ssl_certificate_key C:/nginx/conf/ssl/bis/bis.key;

       client_max_body_size 20M;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto https;
       }
   }
   ```

4. Konfiguration testen (`nginx.exe -t`), Nginx starten. Im Browser: `https://<Ihr-Hostname-oder-IP>` – beim ersten Mal Warnung wegen selbstsigniertem Zertifikat bestätigen.

5. **`docker-compose.yml`** (oder `.env`): `WEBAUTHN_ORIGIN` und `WEBAUTHN_RP_ID` auf genau diese HTTPS-URL bzw. den Hostnamen setzen, dann `docker compose up -d`.

Hintergrund und Linux-Beispiele: [SSL_SELFSIGNED_SETUP.md](SSL_SELFSIGNED_SETUP.md). Ausführliche Windows-Waitress-Variante (andere Ports, statische Pfade): [WINDOWS_DEPLOYMENT_GUIDE.md](WINDOWS_DEPLOYMENT_GUIDE.md).

---

### 10.2 Variante B: Cloudflare Tunnel

Damit erreichen Sie BIS über eine **eigene Domain** mit gültigem Zertifikat von Cloudflare, **ohne** Portweiterleitung am Router. Voraussetzung: Domain in Cloudflare, `cloudflared` auf dem Windows-PC.

1. **BIS per Docker** wie gewohnt starten (`docker compose up -d`), prüfen: `http://localhost:5000`.

2. **cloudflared** installieren, anmelden, Tunnel anlegen – Schritt für Schritt: [CLOUDFLARE_TUNNEL_SETUP.md](CLOUDFLARE_TUNNEL_SETUP.md) (Abschnitte **5**–**7**, ggf. **8** für SSL-Modus „Full“).

3. **Origin auf Docker anbinden:** In der Tunnel-`config.yml` unter `ingress` muss der Dienst auf **HTTP** zeigen, unter dem BIS auf **diesem PC** erreichbar ist – typisch:

   ```yaml
   ingress:
     - hostname: ihre-domain.de
       service: http://localhost:5000
     - service: http_status:404
   ```

   Wenn Sie in `docker-compose.yml` einen **anderen Host-Port** nutzen (z. B. `8080:5000`), hier `http://localhost:8080` eintragen.

   Die vollständige Anleitung im Repo zeigt teils **Nginx auf 443** (`https://localhost:443`) – das ist die Variante mit lokalem HTTPS vor dem Tunnel. Für **nur Docker + HTTP lokal** reicht die direkte Weiterleitung zu `http://localhost:5000` wie oben.

4. Nach Einrichtung: **`WEBAUTHN_ORIGIN`** = öffentliche Basis-URL (z. B. `https://ihre-domain.de`), **`WEBAUTHN_RP_ID`** = Hostname ohne Schema (z. B. `ihre-domain.de`). Container neu starten.

5. Tunnel testen und optional als **Windows-Dienst** laufen lassen (siehe gleiche Doku).

---

## 11. Troubleshooting

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
docker compose logs Application-Service
```

Häufige Ursachen:

- Fehlende oder falsche Umgebungsvariablen (z. B. `DATABASE_URL`, `UPLOAD_BASE_FOLDER`).
- Zu wenig Speicher für Docker: unter **Docker Desktop → Settings → Resources** RAM/Platte erhöhen.

### PDF-Export (Berichte) funktioniert nicht

Im Image ist **LibreOffice** für die DOCX→PDF-Konvertierung enthalten. Wenn PDF-Export trotzdem fehlschlägt:

- Logs prüfen: `docker compose logs Application-Service`
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

# Nach Code-Update von GitHub (im Projektordner)
git pull
docker compose up -d --build
```

Nach dem ersten Start können Sie BIS wie gewohnt im Browser unter **http://localhost:5000** nutzen.
