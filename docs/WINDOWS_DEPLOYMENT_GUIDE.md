# BIS - Deployment Guide für Windows Desktop mit selbstsigniertem SSL

Vollständige Anleitung zur Einrichtung des Betriebsinformationssystems (BIS) auf einem Windows Desktop/Workstation mit Nginx als Reverse Proxy und selbstsigniertem SSL-Zertifikat.

## Inhaltsverzeichnis
1. [Voraussetzungen](#1-voraussetzungen)
2. [Python und Abhängigkeiten installieren](#2-python-und-abhängigkeiten-installieren)
3. [Anwendung einrichten](#3-anwendung-einrichten)
4. [Waitress WSGI-Server installieren und konfigurieren](#4-waitress-wsgi-server-installieren-und-konfigurieren)
5. [Nginx für Windows installieren](#5-nginx-für-windows-installieren)
6. [Selbstsigniertes SSL-Zertifikat erstellen](#6-selbstsigniertes-ssl-zertifikat-erstellen)
7. [Nginx konfigurieren](#7-nginx-konfigurieren)
8. [Windows Service einrichten](#8-windows-service-einrichten)
9. [Windows Firewall konfigurieren](#9-windows-firewall-konfigurieren)
10. [Backup-Strategie](#10-backup-strategie)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Voraussetzungen

### Systemanforderungen
- **Windows 10/11** oder **Windows Server 2016+**
- **Administratorrechte** für Installation und Konfiguration
- **Internetverbindung** für Downloads
- **Mindestens 2 GB freier Speicherplatz**

### Benötigte Software
- Python 3.8 oder höher
- Nginx für Windows
- OpenSSL für Windows (für SSL-Zertifikate)
- NSSM (Non-Sucking Service Manager) - für Windows Services

---

## 2. Python und Abhängigkeiten installieren

### Schritt 1: Python installieren

1. **Python herunterladen:**
   - Besuchen Sie [python.org/downloads](https://www.python.org/downloads/)
   - Laden Sie Python 3.11 oder höher herunter
   - **Wichtig:** Aktivieren Sie beim Installieren "Add Python to PATH"

2. **Installation prüfen:**
   ```powershell
   python --version
   pip --version
   ```

### Schritt 2: Projektverzeichnis erstellen

```powershell
# PowerShell als Administrator öffnen
# Projektverzeichnis erstellen
New-Item -ItemType Directory -Path "C:\BIS" -Force
cd C:\BIS
```

### Schritt 3: Code übertragen

**Option 1: Git Clone (empfohlen)**
```powershell
# Git installieren (falls nicht vorhanden): https://git-scm.com/download/win
git clone https://github.com/IhrUsername/BIS.git .
```

**Option 2: Manuelles Kopieren**
- Kopieren Sie alle Projektdateien nach `C:\BIS`

### Schritt 4: Virtuelle Umgebung erstellen

```powershell
cd C:\BIS

# Virtuelle Umgebung erstellen
python -m venv venv

# Virtuelle Umgebung aktivieren
.\venv\Scripts\Activate.ps1

# Falls ExecutionPolicy-Fehler: Temporär erlauben
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

### Schritt 5: Abhängigkeiten installieren

```powershell
# Pip aktualisieren
python -m pip install --upgrade pip

# Projektabhängigkeiten installieren
pip install -r requirements.txt

# Waitress für Produktion installieren
pip install waitress
```

---

## 3. Anwendung einrichten

### Schritt 1: Umgebungsvariablen konfigurieren

```powershell
cd C:\BIS

# .env-Datei erstellen (basierend auf env_example.txt)
Copy-Item env_example.txt .env

# .env-Datei bearbeiten
notepad .env
```

**Inhalt der `.env`-Datei anpassen:**

```env
# Flask-Konfiguration
FLASK_ENV=production
FLASK_DEBUG=False

# Sicherheit - WICHTIG: Generieren Sie einen sicheren Schlüssel!
# Nutzen Sie: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=HIER_IHREN_GENERIERTEN_GEHEIMEN_SCHLÜSSEL_EINFÜGEN

# Datenbank
DATABASE_URL=C:\BIS\database_main.db

# Upload-Ordner
UPLOAD_BASE_FOLDER=C:\BIS\Daten

# SQL-Tracing (in Produktion aus)
SQL_TRACING=False
```

### Schritt 2: Secret Key generieren

```powershell
# In PowerShell (mit aktivierter venv)
python -c "import secrets; print(secrets.token_hex(32))"
```

Kopieren Sie die Ausgabe und fügen Sie sie als `SECRET_KEY` in die `.env`-Datei ein.

### Schritt 3: Datenverzeichnis erstellen

```powershell
# Datenverzeichnis erstellen
New-Item -ItemType Directory -Path "C:\BIS\Daten" -Force
New-Item -ItemType Directory -Path "C:\BIS\Daten\Schichtbuch\Themen" -Force
New-Item -ItemType Directory -Path "C:\BIS\Daten\Ersatzteile" -Force
New-Item -ItemType Directory -Path "C:\BIS\Daten\Angebote" -Force
New-Item -ItemType Directory -Path "C:\BIS\Daten\Import" -Force

# Log-Verzeichnis erstellen
New-Item -ItemType Directory -Path "C:\BIS\logs" -Force
```

### Schritt 4: Test-Start

```powershell
cd C:\BIS
.\venv\Scripts\Activate.ps1

# Test-Start mit Flask Development Server
python app.py
```

Die Anwendung sollte auf `http://localhost:5000` erreichbar sein. Mit `Ctrl+C` beenden.

---

## 4. Waitress WSGI-Server installieren und konfigurieren

### Schritt 1: Waitress-Konfiguration erstellen

Erstellen Sie die Datei `C:\BIS\waitress_config.py`:

```python
# Waitress-Konfiguration für BIS
import multiprocessing

# Bind-Adresse (nur localhost, Nginx wird als Reverse Proxy verwendet)
bind = "127.0.0.1:8000"

# Worker-Threads
# Regel: (2 x CPU-Kerne) + 1, mindestens 4
threads = max(4, multiprocessing.cpu_count() * 2 + 1)

# Connection-Limit
connection_limit = 1000

# Channel-Timeout
channel_timeout = 120

# Logging
# Logs werden in C:\BIS\logs\ geschrieben
```

### Schritt 2: Start-Script erstellen

Die Datei `deployment\start_waitress.py` ist bereits vorhanden. Kopieren Sie sie nach `C:\BIS\start_waitress.py`:

```powershell
Copy-Item deployment\start_waitress.py start_waitress.py
```

Oder erstellen Sie die Datei manuell `C:\BIS\start_waitress.py`:

```python
#!/usr/bin/env python
"""Startet die BIS-Anwendung mit Waitress"""
import os
import sys

# Projektverzeichnis zum Python-Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Umgebungsvariablen aus .env laden
from dotenv import load_dotenv
load_dotenv()

# Waitress importieren und starten
from waitress import serve
from app import app

if __name__ == '__main__':
    # Log-Verzeichnis erstellen
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Waitress starten
    serve(
        app,
        host='127.0.0.1',
        port=8000,
        threads=4,
        channel_timeout=120
    )
```

**Hinweis:** Falls `python-dotenv` nicht installiert ist:
```powershell
pip install python-dotenv
```

### Schritt 3: Manueller Test

```powershell
cd C:\BIS
.\venv\Scripts\Activate.ps1
python start_waitress.py
```

Die Anwendung sollte auf `http://127.0.0.1:8000` erreichbar sein. Mit `Ctrl+C` beenden.

---

## 5. Nginx für Windows installieren

### Schritt 1: Nginx herunterladen

1. **Nginx für Windows herunterladen:**
   - Besuchen Sie [nginx.org/en/download.html](http://nginx.org/en/download.html)
   - Laden Sie die **Windows-Version** (z.B. `nginx/Windows-1.25.x`) herunter
   - Entpacken Sie die ZIP-Datei nach `C:\nginx`

### Schritt 2: Nginx-Verzeichnisstruktur

```
C:\nginx\
├── conf\
│   ├── nginx.conf
│   └── sites-available\  (selbst erstellen)
│   └── sites-enabled\   (selbst erstellen)
├── logs\
├── html\
└── nginx.exe
```

### Schritt 3: Verzeichnisse erstellen

```powershell
# PowerShell als Administrator
cd C:\nginx

# Verzeichnisse für Site-Konfigurationen erstellen
New-Item -ItemType Directory -Path "conf\sites-available" -Force
New-Item -ItemType Directory -Path "conf\sites-enabled" -Force
New-Item -ItemType Directory -Path "conf\ssl\bis" -Force
```

### Schritt 4: Nginx testen

```powershell
cd C:\nginx

# Nginx starten (im Vordergrund zum Testen)
.\nginx.exe

# Im Browser öffnen: http://localhost
# Sollte "Welcome to nginx!" anzeigen

# Nginx stoppen
.\nginx.exe -s stop
```

---

## 6. Selbstsigniertes SSL-Zertifikat erstellen

### Option 1: PowerShell-Script (empfohlen)

**Voraussetzung:** OpenSSL für Windows muss installiert sein.

1. **OpenSSL für Windows installieren:**
   - Download: [slproweb.com/products/Win32OpenSSL.html](https://slproweb.com/products/Win32OpenSSL.html)
   - Oder via Chocolatey: `choco install openssl`

2. **Script ausführen:**
   ```powershell
   cd C:\BIS
   .\scripts\create_self_signed_cert_windows.ps1 -ServerName "192.168.1.100"
   # oder mit Hostname:
   .\scripts\create_self_signed_cert_windows.ps1 -ServerName "bis-server.local"
   ```

### Option 2: Python-Script

```powershell
cd C:\BIS
.\venv\Scripts\Activate.ps1
python scripts\create_self_signed_cert_windows.py 192.168.1.100
```

### Option 3: Manuell mit OpenSSL

```powershell
# PowerShell als Administrator
cd C:\nginx\conf\ssl\bis

# Zertifikat erstellen (für IP-Adresse)
openssl req -x509 -nodes -days 3650 -newkey rsa:4096 `
  -keyout bis.key `
  -out bis.crt `
  -subj "/C=DE/ST=State/L=City/O=BIS/CN=192.168.1.100" `
  -addext "subjectAltName=IP:192.168.1.100,IP:127.0.0.1,DNS:localhost"

# Berechtigungen setzen (optional, Windows hat andere Berechtigungen)
# Die Dateien sollten nur für Administratoren zugänglich sein
```

**Wichtig:** 
- Bei IP-Adressen muss `IP:` in den SANs verwendet werden, nicht `DNS:`
- Bei Hostnamen verwenden Sie `DNS:hostname`

### Schritt 4: Zertifikat prüfen

```powershell
# Zertifikat-Details anzeigen
openssl x509 -in C:\nginx\conf\ssl\bis\bis.crt -text -noout | Select-String -Pattern "Subject Alternative Name" -Context 0,5
```

---

## 7. Nginx konfigurieren

### Schritt 1: Nginx-Hauptkonfiguration anpassen

Bearbeiten Sie `C:\nginx\conf\nginx.conf`:

```nginx
# Am Ende der http-Sektion hinzufügen:
include sites-enabled/*.conf;
```

### Schritt 2: BIS-Site-Konfiguration erstellen

Kopieren Sie `deployment\nginx_windows.conf` nach `C:\nginx\conf\sites-available\bis.conf`

Oder erstellen Sie die Datei manuell:

```nginx
# HTTP -> HTTPS Redirect (optional)
server {
    listen 80;
    server_name _;
    
    # Optional: Redirect zu HTTPS
    # return 301 https://$host$request_uri;
    
    # Oder: HTTP erlauben (für Entwicklung)
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTPS Server mit Self-Signed Certificate
server {
    listen 443 ssl http2;
    server_name _;

    # Self-Signed Zertifikate (Windows-Pfade!)
    ssl_certificate C:/nginx/conf/ssl/bis/bis.crt;
    ssl_certificate_key C:/nginx/conf/ssl/bis/bis.key;
    
    # SSL-Konfiguration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    
    # SSL Session Cache
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Client-Upload-Größe
    client_max_body_size 20M;

    # Logging
    access_log C:/nginx/logs/bis_access.log;
    error_log C:/nginx/logs/bis_error.log;

    # Statische Dateien
    location /static/ {
        alias C:/BIS/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Upload-Dateien
    location /uploads/ {
        alias C:/BIS/Daten/;
        expires 1d;
        add_header Cache-Control "public";
    }

    # Proxy zu Waitress
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Sicherheits-Header
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

**Wichtig:** 
- Windows-Pfade in Nginx: Verwenden Sie `/` statt `\` und `C:/` statt `C:\`
- Keine Leerzeichen in Pfaden!

### Schritt 3: Site aktivieren

```powershell
# Symlink erstellen (PowerShell als Administrator)
cd C:\nginx\conf
New-Item -ItemType SymbolicLink -Path "sites-enabled\bis.conf" -Target "sites-available\bis.conf"
```

### Schritt 4: Nginx-Konfiguration testen

```powershell
cd C:\nginx

# Konfiguration testen
.\nginx.exe -t

# Bei Erfolg: Nginx starten
.\nginx.exe
```

### Schritt 5: Testen

Öffnen Sie im Browser:
- HTTP: `http://localhost` oder `http://192.168.1.100`
- HTTPS: `https://localhost` oder `https://192.168.1.100`

**Hinweis:** Beim ersten HTTPS-Besuch erscheint eine Sicherheitswarnung (selbstsigniertes Zertifikat). Diese muss einmalig akzeptiert werden.

---

## 8. Windows Service einrichten

### Schritt 1: NSSM installieren

1. **NSSM herunterladen:**
   - Besuchen Sie [nssm.cc/download](https://nssm.cc/download)
   - Laden Sie die neueste Version herunter (z.B. `nssm-2.24.zip`)
   - Entpacken Sie `win64\nssm.exe` nach `C:\BIS\nssm.exe`

### Schritt 2: Service für Waitress erstellen

**Option 1: PowerShell-Script (empfohlen)**

```powershell
cd C:\BIS
.\deployment\install_bis_service.ps1
```

**Option 2: Manuell mit NSSM**

```powershell
# PowerShell als Administrator
cd C:\BIS

# Service installieren
.\nssm.exe install BIS-Waitress "C:\BIS\venv\Scripts\python.exe" "C:\BIS\start_waitress.py"

# Service konfigurieren
.\nssm.exe set BIS-Waitress AppDirectory "C:\BIS"
.\nssm.exe set BIS-Waitress DisplayName "BIS Flask Application"
.\nssm.exe set BIS-Waitress Description "Betriebsinformationssystem Flask-Anwendung"
.\nssm.exe set BIS-Waitress Start SERVICE_AUTO_START
.\nssm.exe set BIS-Waitress AppStdout "C:\BIS\logs\waitress_stdout.log"
.\nssm.exe set BIS-Waitress AppStderr "C:\BIS\logs\waitress_stderr.log"

# Service starten
.\nssm.exe start BIS-Waitress

# Status prüfen
.\nssm.exe status BIS-Waitress
```

### Schritt 3: Service für Nginx erstellen

```powershell
# PowerShell als Administrator
cd C:\nginx

# Service installieren
.\nssm.exe install Nginx "C:\nginx\nginx.exe"

# Service konfigurieren
.\nssm.exe set Nginx AppDirectory "C:\nginx"
.\nssm.exe set Nginx DisplayName "Nginx Web Server"
.\nssm.exe set Nginx Description "Nginx Reverse Proxy für BIS"
.\nssm.exe set Nginx Start SERVICE_AUTO_START
.\nssm.exe set Nginx AppStdout "C:\nginx\logs\service_stdout.log"
.\nssm.exe set Nginx AppStderr "C:\nginx\logs\service_stderr.log"

# Service starten
.\nssm.exe start Nginx

# Status prüfen
.\nssm.exe status Nginx
```

### Schritt 4: Services verwalten

```powershell
# Services starten
Start-Service BIS-Waitress
Start-Service Nginx

# Services stoppen
Stop-Service BIS-Waitress
Stop-Service Nginx

# Service-Status prüfen
Get-Service BIS-Waitress
Get-Service Nginx

# Logs anzeigen
Get-Content C:\BIS\logs\waitress_stdout.log -Tail 50
Get-Content C:\nginx\logs\bis_error.log -Tail 50
```

**Alternative:** Services über `services.msc` verwalten:
- Windows-Taste + R
- `services.msc` eingeben
- Nach "BIS-Waitress" und "Nginx" suchen

---

## 9. Windows Firewall konfigurieren

### Schritt 1: Firewall-Regeln erstellen

```powershell
# PowerShell als Administrator

# HTTP (Port 80)
New-NetFirewallRule -DisplayName "BIS HTTP" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow

# HTTPS (Port 443)
New-NetFirewallRule -DisplayName "BIS HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow

# Waitress (Port 8000 - nur localhost, sollte nicht von außen erreichbar sein)
# Normalerweise nicht nötig, da nur localhost
```

### Schritt 2: Firewall-Regeln prüfen

```powershell
# Alle BIS-Regeln anzeigen
Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*BIS*"}

# Regel entfernen (falls nötig)
Remove-NetFirewallRule -DisplayName "BIS HTTP"
```

---

## 10. Backup-Strategie

### Schritt 1: Backup-Script erstellen

Erstellen Sie `C:\BIS\backup_bis.ps1`:

```powershell
# BIS Backup Script für Windows
$BackupDir = "C:\BIS\backups"
$DataDir = "C:\BIS"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupName = "bis_backup_$Timestamp"
$RetentionDays = 30

# Backup-Verzeichnis erstellen
New-Item -ItemType Directory -Path "$BackupDir\$BackupName" -Force | Out-Null

Write-Host "Sichern der Datenbank..."
# Datenbank-Backup (SQLite)
Copy-Item "$DataDir\database_main.db" "$BackupDir\$BackupName\database_main.db"

Write-Host "Sichern der Upload-Dateien..."
# Uploads-Backup
Compress-Archive -Path "$DataDir\Daten" -DestinationPath "$BackupDir\$BackupName\uploads.zip" -Force

# Backup komprimieren
Write-Host "Komprimieren des Backups..."
Compress-Archive -Path "$BackupDir\$BackupName" -DestinationPath "$BackupDir\$BackupName.zip" -Force

# Temporäres Verzeichnis löschen
Remove-Item "$BackupDir\$BackupName" -Recurse -Force

# Alte Backups löschen (älter als RetentionDays)
Write-Host "Lösche Backups älter als $RetentionDays Tage..."
Get-ChildItem "$BackupDir\bis_backup_*.zip" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays)
} | Remove-Item -Force

Write-Host "Backup abgeschlossen: $BackupName.zip"
```

### Schritt 2: Automatisches Backup einrichten

**Option 1: Windows Task Scheduler**

1. **Task Scheduler öffnen:**
   - Windows-Taste + R
   - `taskschd.msc` eingeben

2. **Neuen Task erstellen:**
   - "Create Basic Task" wählen
   - Name: "BIS Daily Backup"
   - Trigger: Täglich um 2:00 Uhr
   - Action: Programm starten
   - Programm: `powershell.exe`
   - Argumente: `-ExecutionPolicy Bypass -File "C:\BIS\backup_bis.ps1"`

**Option 2: PowerShell-Script für Task-Erstellung**

```powershell
# PowerShell als Administrator
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"C:\BIS\backup_bis.ps1`""
$Trigger = New-ScheduledTaskTrigger -Daily -At 2am
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest
Register-ScheduledTask -TaskName "BIS Daily Backup" -Action $Action -Trigger $Trigger -Principal $Principal -Description "Tägliches Backup des BIS-Systems"
```

### Schritt 3: Backup wiederherstellen

```powershell
# Service stoppen
Stop-Service BIS-Waitress

# Backup entpacken
Expand-Archive -Path "C:\BIS\backups\bis_backup_YYYYMMDD_HHMMSS.zip" -DestinationPath "C:\BIS\restore" -Force

# Datenbank wiederherstellen
Copy-Item "C:\BIS\restore\bis_backup_YYYYMMDD_HHMMSS\database_main.db" "C:\BIS\database_main.db" -Force

# Uploads wiederherstellen
Expand-Archive -Path "C:\BIS\restore\bis_backup_YYYYMMDD_HHMMSS\uploads.zip" -DestinationPath "C:\BIS\Daten" -Force

# Service starten
Start-Service BIS-Waitress
```

---

## 11. Troubleshooting

### Problem: Waitress startet nicht

**Lösung:**
```powershell
# Logs prüfen
Get-Content C:\BIS\logs\waitress_stdout.log -Tail 50
Get-Content C:\BIS\logs\waitress_stderr.log -Tail 50

# Manuell testen
cd C:\BIS
.\venv\Scripts\Activate.ps1
python start_waitress.py

# Port prüfen
netstat -ano | findstr :8000
```

### Problem: Nginx zeigt 502 Bad Gateway

**Lösung:**
```powershell
# Prüfen ob Waitress läuft
Get-Service BIS-Waitress
netstat -ano | findstr :8000

# Nginx-Logs prüfen
Get-Content C:\nginx\logs\bis_error.log -Tail 50

# Nginx-Konfiguration testen
cd C:\nginx
.\nginx.exe -t
```

### Problem: SSL-Zertifikat wird nicht akzeptiert

**Lösung:**
- Zertifikat auf Client installieren (siehe unten)
- Browser-Cache leeren
- Zertifikat prüfen: `openssl x509 -in C:\nginx\conf\ssl\bis\bis.crt -text -noout`

### Problem: Port bereits belegt

**Lösung:**
```powershell
# Prozess auf Port finden
netstat -ano | findstr :8000
netstat -ano | findstr :443

# Prozess beenden (PID aus obiger Ausgabe)
taskkill /PID <PID> /F
```

### Problem: Service startet nicht automatisch

**Lösung:**
```powershell
# Service-Konfiguration prüfen
.\nssm.exe status BIS-Waitress

# Service auf Auto-Start setzen
.\nssm.exe set BIS-Waitress Start SERVICE_AUTO_START

# Service neu starten
Restart-Service BIS-Waitress
```

### Problem: Datenbank-Fehler

**Lösung:**
```powershell
# Berechtigungen prüfen
Get-Acl C:\BIS\database_main.db

# Datenbank-Integrität prüfen (SQLite)
cd C:\BIS
.\venv\Scripts\Activate.ps1
python -c "import sqlite3; conn = sqlite3.connect('database_main.db'); print(conn.execute('PRAGMA integrity_check;').fetchone()); conn.close()"
```

---

## Zertifikat auf Clients installieren (optional)

Um die Browser-Warnung zu vermeiden, können Sie das Zertifikat auf den Clients installieren.

### Windows Client

1. **Zertifikat herunterladen:**
   - Von `C:\nginx\conf\ssl\bis\bis.crt` auf den Client kopieren

2. **Zertifikat installieren:**
   - Doppelklick auf `bis.crt`
   - "Zertifikat installieren" klicken
   - "Aktuellen Benutzer" wählen
   - "Weiter" klicken
   - "Alle Zertifikate in folgendem Speicher speichern" wählen
   - "Durchsuchen" → "Vertrauenswürdige Stammzertifizierungsstellen" wählen
   - "Weiter" → "Fertig"

3. **Browser neu starten**

### Android Client

1. Zertifikat auf Gerät kopieren
2. Einstellungen → Sicherheit → Verschlüsselung & Anmeldedaten
3. "Zertifikat aus Speicher installieren"
4. `bis.crt` auswählen
5. Name vergeben (z.B. "BIS Server")
6. "VPN und Apps" oder "Alle" wählen

### iOS Client

1. Zertifikat per E-Mail oder Web-Download auf Gerät übertragen
2. Einstellungen → Allgemein → VPN & Geräteverwaltung
3. Zertifikat auswählen und installieren
4. Vertrauen aktivieren

---

## Nützliche Befehle

### Service-Management

```powershell
# Services starten
Start-Service BIS-Waitress
Start-Service Nginx

# Services stoppen
Stop-Service BIS-Waitress
Stop-Service Nginx

# Services neu starten
Restart-Service BIS-Waitress
Restart-Service Nginx

# Service-Status
Get-Service BIS-Waitress
Get-Service Nginx
```

### Nginx-Management

```powershell
cd C:\nginx

# Nginx starten
.\nginx.exe

# Nginx stoppen
.\nginx.exe -s stop

# Nginx neu laden (ohne Downtime)
.\nginx.exe -s reload

# Nginx-Konfiguration testen
.\nginx.exe -t
```

### Logs anzeigen

```powershell
# Waitress-Logs
Get-Content C:\BIS\logs\waitress_stdout.log -Tail 50 -Wait
Get-Content C:\BIS\logs\waitress_stderr.log -Tail 50

# Nginx-Logs
Get-Content C:\nginx\logs\bis_access.log -Tail 50
Get-Content C:\nginx\logs\bis_error.log -Tail 50
```

### Ports prüfen

```powershell
# Alle aktiven Ports anzeigen
netstat -ano | findstr LISTENING

# Spezifische Ports prüfen
netstat -ano | findstr :8000
netstat -ano | findstr :443
```

---

## Sicherheits-Checkliste

- [ ] Starkes SECRET_KEY in `.env` gesetzt
- [ ] SSL-Zertifikat erstellt und konfiguriert
- [ ] Windows Firewall-Regeln eingerichtet
- [ ] Services auf Auto-Start konfiguriert
- [ ] Automatische Backups eingerichtet
- [ ] Log-Verzeichnisse erstellt
- [ ] Nginx nur auf notwendigen Ports erreichbar
- [ ] Waitress nur auf localhost (127.0.0.1) gebunden
- [ ] Regelmäßige Updates eingeplant
- [ ] Zertifikat auf Clients installiert (optional)

---

## Updates durchführen

### App-Update

```powershell
# Services stoppen
Stop-Service BIS-Waitress

# Backup erstellen
.\backup_bis.ps1

# Code aktualisieren (bei Git)
cd C:\BIS
git pull

# Oder neue Dateien manuell kopieren

# Dependencies aktualisieren
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --upgrade

# Services starten
Start-Service BIS-Waitress
```

### Nginx-Update

1. Nginx herunterladen und entpacken
2. Alte Konfigurationen sichern
3. Neue Version installieren
4. Konfigurationen wiederherstellen
5. Service neu starten

---

## Weitere Ressourcen

- [Flask Dokumentation](https://flask.palletsprojects.com/)
- [Waitress Dokumentation](https://docs.pylonsproject.org/projects/waitress/)
- [Nginx für Windows](http://nginx.org/en/docs/windows.html)
- [NSSM Dokumentation](https://nssm.cc/usage)

---

**Viel Erfolg mit Ihrem BIS-Deployment auf Windows! 🚀**

