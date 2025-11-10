# BIS - Deployment Guide für Proxmox LXC Container

Vollständige Anleitung zur Einrichtung eines produktiven Servers für das Betriebsinformationssystem (BIS) in einem Proxmox LXC-Container.

## Inhaltsverzeichnis
1. [LXC-Container erstellen](#1-lxc-container-erstellen)
2. [Grundkonfiguration des Containers](#2-grundkonfiguration-des-containers)
3. [Systemabhängigkeiten installieren](#3-systemabhängigkeiten-installieren)
4. [Applikation einrichten](#4-applikation-einrichten)
5. [Gunicorn konfigurieren](#5-gunicorn-konfigurieren)
6. [Nginx als Reverse Proxy einrichten](#6-nginx-als-reverse-proxy-einrichten)
7. [SSL/TLS mit Let's Encrypt](#7-ssltls-mit-lets-encrypt)
8. [Automatische Backups](#8-automatische-backups)
9. [Monitoring und Logs](#9-monitoring-und-logs)
10. [Wartung und Updates](#10-wartung-und-updates)

---

## 1. LXC-Container erstellen

### In der Proxmox Web-Oberfläche:

1. **Container erstellen:**
   - Klicken Sie auf "Create CT"
   - Container ID: z.B. 100
   - Hostname: `bis-prod`
   - Password: Sicheres Root-Passwort setzen

2. **Template wählen:**
   - Empfohlen: **Ubuntu 24.04** oder **Debian 12**
   - Template herunterladen falls noch nicht vorhanden

3. **Ressourcen zuweisen:**
   - Festplatte: 20 GB (für App, Datenbank, Logs, Uploads)
   - CPU: 2 Cores
   - RAM: 2048 MB
   - Swap: 512 MB

4. **Netzwerk:**
   - IPv4: DHCP oder statische IP (z.B. 192.168.1.100/24)
   - Gateway: Ihr Netzwerk-Gateway
   - IPv6: Optional

5. **DNS:**
   - DNS Server: 8.8.8.8, 8.8.4.4 (oder Ihr eigener)

6. **Container starten** und per SSH verbinden

### Alternative: Container per CLI erstellen

```bash
# Auf dem Proxmox Host
pct create 100 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst \
  --hostname bis-prod \
  --memory 2048 \
  --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.1.100/24,gw=192.168.1.1 \
  --nameserver 8.8.8.8 \
  --password

pct start 100
```

---

## 2. Grundkonfiguration des Containers

### In den Container einloggen:

```bash
# Von Proxmox Host
pct enter 100

# Oder per SSH (empfohlen für Copy-Paste)
ssh root@192.168.1.100
```

### System aktualisieren:

```bash
apt update && apt upgrade -y
```

### Zeitzone einstellen:

```bash
timedatectl set-timezone Europe/Berlin
```

### Benutzer für die Anwendung erstellen:

```bash
# Benutzer "bis" erstellen
useradd -m -s /bin/bash bis
passwd bis  # Passwort setzen

# Benutzer zu sudo-Gruppe hinzufügen (optional)
usermod -aG sudo bis

# SSH-Zugang konfigurieren (optional)
mkdir -p /home/bis/.ssh
chmod 700 /home/bis/.ssh
chown bis:bis /home/bis/.ssh
```

### Firewall einrichten (optional aber empfohlen):

```bash
apt install -y ufw

# Basis-Regeln
ufw default deny incoming
ufw default allow outgoing

# SSH erlauben
ufw allow 22/tcp

# HTTP/HTTPS erlauben
ufw allow 80/tcp
ufw allow 443/tcp

# Firewall aktivieren
ufw enable
ufw status
```

---

## 3. Systemabhängigkeiten installieren

### Python und essenzielle Tools:

```bash
apt install -y \
  python3 \
  python3-pip \
  python3-venv \
  git \
  nginx \
  supervisor \
  sqlite3 \
  curl \
  vim \
  htop
```

### Optionale Tools:

```bash
# Für Monitoring
apt install -y fail2ban logwatch

# Für automatische Updates
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

---

## 4. Applikation einrichten

### App-Verzeichnis erstellen:

```bash
# Verzeichnisstruktur
mkdir -p /opt/bis
mkdir -p /var/log/bis
mkdir -p /var/www/bis-data

# Berechtigungen setzen
chown -R bis:bis /opt/bis
chown -R bis:bis /var/log/bis
chown -R bis:bis /var/www/bis-data
```

### Code übertragen:

#### Option 1: Git Clone (empfohlen)

```bash
# Als bis-Benutzer
su - bis
cd /opt/bis

# Wenn Sie ein Git-Repository haben
git clone https://github.com/IhrUsername/BIS.git .

# Oder von Ihrem lokalen Repository
# (Von Ihrem Windows-PC ausführen)
# scp -r C:\Projekte\BIS/* bis@192.168.1.100:/opt/bis/
```

#### Option 2: Manuelles Kopieren per SCP (von Windows)

```powershell
# Von Ihrem Windows-PC (PowerShell)
scp -r C:\Projekte\BIS\* bis@192.168.1.100:/opt/bis/
```

#### Option 3: SFTP mit WinSCP

Nutzen Sie WinSCP oder FileZilla, um die Dateien zu übertragen.

### Python Virtual Environment erstellen:

```bash
# Als bis-Benutzer
su - bis
cd /opt/bis

# Virtual Environment erstellen
python3 -m venv venv

# Virtual Environment aktivieren
source venv/bin/activate

# Dependencies installieren
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn  # WSGI-Server für Produktion
```

### Produktions-Umgebungsvariablen erstellen:

```bash
# Als bis-Benutzer
cd /opt/bis
nano .env
```

Inhalt der `.env`-Datei:

```bash
# Flask-Konfiguration
FLASK_ENV=production
FLASK_DEBUG=False

# Sicherheit - WICHTIG: Generieren Sie einen sicheren Schlüssel!
# Nutzen Sie: python3 -c 'import secrets; print(secrets.token_hex(32))'
SECRET_KEY=HIER_IHREN_GENERIERTEN_GEHEIMEN_SCHLÜSSEL_EINFÜGEN

# Datenbank
DATABASE_URL=/var/www/bis-data/database_main.db

# Upload-Ordner
UPLOAD_BASE_FOLDER=/var/www/bis-data/Daten

# SQL-Tracing (in Produktion aus)
SQL_TRACING=False
```

### Secret Key generieren:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Kopieren Sie die Ausgabe und fügen Sie sie als `SECRET_KEY` in die `.env`-Datei ein.

### Datenbank und Uploads vorbereiten:

```bash
# Datenbank kopieren
cp /opt/bis/database_main.db /var/www/bis-data/database_main.db

# Upload-Ordner erstellen
mkdir -p /var/www/bis-data/Daten/Schichtbuch/Themen

# Existierende Daten kopieren (falls vorhanden)
cp -r /opt/bis/Daten/* /var/www/bis-data/Daten/

# Berechtigungen setzen
chown -R bis:bis /var/www/bis-data
chmod -R 755 /var/www/bis-data
```

### Umgebungsvariablen laden:

```bash
# .env-Datei in bashrc einbinden (als bis-Benutzer)
echo 'export $(grep -v "^#" /opt/bis/.env | xargs)' >> ~/.bashrc
source ~/.bashrc
```

### Test der Anwendung:

```bash
# Als bis-Benutzer, im Virtual Environment
cd /opt/bis
source venv/bin/activate

# Test-Start
python app.py
# Sollte auf 0.0.0.0:5000 starten

# Mit Gunicorn testen
gunicorn -w 2 -b 127.0.0.1:8000 app:app

# Wenn das funktioniert, mit Ctrl+C beenden
```

---

## 5. Gunicorn konfigurieren

### Gunicorn-Konfiguration erstellen:

```bash
# Als bis-Benutzer
cd /opt/bis
nano gunicorn_config.py
```

Inhalt von `gunicorn_config.py`:

```python
import multiprocessing

# Bind-Adresse
bind = "127.0.0.1:8000"

# Worker-Prozesse
# Regel: (2 x CPU-Kerne) + 1
workers = multiprocessing.cpu_count() * 2 + 1

# Worker-Typ
worker_class = "sync"

# Timeout
timeout = 120

# Logging
accesslog = "/var/log/bis/access.log"
errorlog = "/var/log/bis/error.log"
loglevel = "info"

# Prozess-Name
proc_name = "bis-app"

# Daemon-Modus (wird von systemd verwaltet)
daemon = False

# Umgebungsvariablen
raw_env = [
    "FLASK_ENV=production",
]
```

### Systemd Service erstellen:

```bash
# Als root
exit  # Zurück zu root
nano /etc/systemd/system/bis.service
```

Inhalt von `bis.service`:

```ini
[Unit]
Description=BIS Flask Application
After=network.target

[Service]
Type=notify
User=bis
Group=bis
WorkingDirectory=/opt/bis
Environment="PATH=/opt/bis/venv/bin"
EnvironmentFile=/opt/bis/.env
ExecStart=/opt/bis/venv/bin/gunicorn -c gunicorn_config.py app:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Service aktivieren und starten:

```bash
# Service neu laden
systemctl daemon-reload

# Service aktivieren (Autostart)
systemctl enable bis.service

# Service starten
systemctl start bis.service

# Status prüfen
systemctl status bis.service

# Logs anzeigen
journalctl -u bis.service -f
```

---

## 6. Nginx als Reverse Proxy einrichten

### Nginx-Konfiguration erstellen:

```bash
nano /etc/nginx/sites-available/bis
```

Inhalt (ohne SSL, zunächst):

```nginx
server {
    listen 80;
    server_name bis.ihre-domain.de;  # Ersetzen Sie mit Ihrer Domain oder IP

    # Client-Upload-Größe
    client_max_body_size 20M;

    # Logging
    access_log /var/log/nginx/bis_access.log;
    error_log /var/log/nginx/bis_error.log;

    # Statische Dateien
    location /static/ {
        alias /opt/bis/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Upload-Dateien
    location /uploads/ {
        alias /var/www/bis-data/Daten/;
        expires 1d;
        add_header Cache-Control "public";
    }

    # Proxy zu Gunicorn
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

### Nginx-Konfiguration aktivieren:

```bash
# Symlink erstellen
ln -s /etc/nginx/sites-available/bis /etc/nginx/sites-enabled/

# Standard-Seite deaktivieren (optional)
rm /etc/nginx/sites-enabled/default

# Konfiguration testen
nginx -t

# Nginx neu starten
systemctl restart nginx

# Nginx Autostart aktivieren
systemctl enable nginx
```

### Test:

Öffnen Sie Ihren Browser und navigieren Sie zu:
```
http://192.168.1.100
# oder
http://bis.ihre-domain.de
```

---

## 7. SSL/TLS mit Let's Encrypt

### Certbot installieren:

```bash
apt install -y certbot python3-certbot-nginx
```

### SSL-Zertifikat erstellen:

```bash
# Ersetzen Sie mit Ihrer echten Domain
certbot --nginx -d bis.ihre-domain.de

# Folgen Sie den Anweisungen:
# - E-Mail-Adresse angeben
# - Nutzungsbedingungen akzeptieren
# - Redirect von HTTP zu HTTPS wählen (empfohlen)
```

### Automatische Erneuerung testen:

```bash
certbot renew --dry-run
```

Die automatische Erneuerung wird via systemd-timer durchgeführt und ist bereits eingerichtet.

### Manuelle Nginx-Konfiguration mit SSL (falls gewünscht):

```bash
nano /etc/nginx/sites-available/bis
```

Ersetzen Sie den Inhalt mit:

```nginx
# HTTP -> HTTPS Redirect
server {
    listen 80;
    server_name bis.ihre-domain.de;
    return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name bis.ihre-domain.de;

    # SSL-Zertifikate
    ssl_certificate /etc/letsencrypt/live/bis.ihre-domain.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bis.ihre-domain.de/privkey.pem;
    
    # SSL-Konfiguration (modern)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    
    # SSL Session Cache
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/bis.ihre-domain.de/chain.pem;

    # Client-Upload-Größe
    client_max_body_size 20M;

    # Logging
    access_log /var/log/nginx/bis_access.log;
    error_log /var/log/nginx/bis_error.log;

    # Statische Dateien
    location /static/ {
        alias /opt/bis/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Upload-Dateien
    location /uploads/ {
        alias /var/www/bis-data/Daten/;
        expires 1d;
        add_header Cache-Control "public";
    }

    # Proxy zu Gunicorn
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
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

```bash
# Nginx neu laden
nginx -t
systemctl reload nginx
```

---

## 8. Automatische Backups

### Backup-Script erstellen:

```bash
mkdir -p /opt/backups
nano /opt/backups/bis_backup.sh
```

Inhalt von `bis_backup.sh`:

```bash
#!/bin/bash

# BIS Backup Script
# Erstellt Backups der Datenbank und Uploads

BACKUP_DIR="/opt/backups"
DATA_DIR="/var/www/bis-data"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="bis_backup_${TIMESTAMP}"
RETENTION_DAYS=30

# Backup-Verzeichnis erstellen
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

# Datenbank-Backup
echo "Sichern der Datenbank..."
sqlite3 "${DATA_DIR}/database_main.db" ".backup '${BACKUP_DIR}/${BACKUP_NAME}/database_main.db'"

# Uploads-Backup
echo "Sichern der Upload-Dateien..."
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" -C "${DATA_DIR}" Daten/

# Backup komprimieren
echo "Komprimieren des Backups..."
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "${BACKUP_DIR}" "${BACKUP_NAME}"

# Temporäres Verzeichnis löschen
rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"

# Alte Backups löschen (älter als RETENTION_DAYS)
echo "Lösche Backups älter als ${RETENTION_DAYS} Tage..."
find "${BACKUP_DIR}" -name "bis_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete

echo "Backup abgeschlossen: ${BACKUP_NAME}.tar.gz"
```

### Script ausführbar machen:

```bash
chmod +x /opt/backups/bis_backup.sh
```

### Cronjob für automatische Backups einrichten:

```bash
crontab -e
```

Fügen Sie hinzu (tägliches Backup um 2:00 Uhr):

```cron
# BIS Daily Backup um 2:00 Uhr
0 2 * * * /opt/backups/bis_backup.sh >> /var/log/bis/backup.log 2>&1
```

### Manuelles Backup testen:

```bash
/opt/backups/bis_backup.sh
ls -lh /opt/backups/
```

### Backup-Restore (bei Bedarf):

```bash
# Service stoppen
systemctl stop bis.service

# Backup wiederherstellen
cd /opt/backups
tar -xzf bis_backup_YYYYMMDD_HHMMSS.tar.gz
sqlite3 /var/www/bis-data/database_main.db ".restore 'bis_backup_YYYYMMDD_HHMMSS/database_main.db'"
tar -xzf bis_backup_YYYYMMDD_HHMMSS/uploads.tar.gz -C /var/www/bis-data/

# Berechtigungen setzen
chown -R bis:bis /var/www/bis-data

# Service starten
systemctl start bis.service
```

---

## 9. Monitoring und Logs

### Log-Dateien:

```bash
# Gunicorn/App-Logs
tail -f /var/log/bis/error.log
tail -f /var/log/bis/access.log

# Systemd-Logs
journalctl -u bis.service -f

# Nginx-Logs
tail -f /var/log/nginx/bis_access.log
tail -f /var/log/nginx/bis_error.log
```

### Log-Rotation einrichten:

```bash
nano /etc/logrotate.d/bis
```

Inhalt:

```
/var/log/bis/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 bis bis
    sharedscripts
    postrotate
        systemctl reload bis.service > /dev/null 2>&1 || true
    endscript
}
```

### Einfaches Monitoring-Script:

```bash
nano /opt/backups/check_bis.sh
```

Inhalt:

```bash
#!/bin/bash

# BIS Health Check Script

# Service-Status prüfen
if ! systemctl is-active --quiet bis.service; then
    echo "WARNUNG: BIS Service ist nicht aktiv!"
    systemctl status bis.service
    exit 1
fi

# HTTP-Status prüfen
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
if [ "$HTTP_STATUS" != "200" ] && [ "$HTTP_STATUS" != "302" ]; then
    echo "WARNUNG: BIS antwortet nicht korrekt (HTTP $HTTP_STATUS)"
    exit 1
fi

# Disk-Space prüfen
DISK_USAGE=$(df -h /var/www/bis-data | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "WARNUNG: Disk-Space über 80% (${DISK_USAGE}%)"
    exit 1
fi

echo "BIS läuft einwandfrei"
exit 0
```

```bash
chmod +x /opt/backups/check_bis.sh

# Cronjob für stündliche Checks
crontab -e
```

Hinzufügen:

```cron
# BIS Health Check jede Stunde
0 * * * * /opt/backups/check_bis.sh >> /var/log/bis/healthcheck.log 2>&1
```

---

## 10. Wartung und Updates

### App-Update durchführen:

```bash
# Service stoppen
systemctl stop bis.service

# Als bis-Benutzer
su - bis
cd /opt/bis

# Code aktualisieren (bei Git)
git pull

# Oder neue Dateien hochladen via SCP/SFTP

# Dependencies aktualisieren
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Zurück zu root
exit

# Service starten
systemctl start bis.service

# Status prüfen
systemctl status bis.service
```

### System-Updates:

```bash
# Regelmäßige Updates
apt update && apt upgrade -y

# Container neu starten (falls Kernel-Updates)
reboot
```

### Datenbank-Migration:

```bash
# Als bis-Benutzer
su - bis
cd /opt/bis
source venv/bin/activate

# Backup erstellen
cp /var/www/bis-data/database_main.db /var/www/bis-data/database_main.db.backup

# Migration ausführen (wenn vorhanden)
python migrations/run_migration.py

# Bei Problemen: Backup wiederherstellen
# cp /var/www/bis-data/database_main.db.backup /var/www/bis-data/database_main.db
```

---

## Nützliche Befehle

### Service-Management:

```bash
# Service neu starten
systemctl restart bis.service

# Service stoppen
systemctl stop bis.service

# Service starten
systemctl start bis.service

# Service-Status
systemctl status bis.service

# Logs ansehen
journalctl -u bis.service -n 100 --no-pager
```

### Nginx:

```bash
# Nginx neu laden (ohne Downtime)
nginx -t && systemctl reload nginx

# Nginx neu starten
systemctl restart nginx
```

### Disk-Space prüfen:

```bash
df -h
du -sh /var/www/bis-data/*
du -sh /opt/backups/*
```

### Prozesse überwachen:

```bash
htop
ps aux | grep gunicorn
```

---

## Sicherheits-Checkliste

- [ ] Starkes Root-Passwort gesetzt
- [ ] Separater Benutzer für die App erstellt
- [ ] Firewall (ufw) aktiviert
- [ ] SSL/TLS-Zertifikat installiert
- [ ] SECRET_KEY in .env geändert
- [ ] Automatische Backups eingerichtet
- [ ] Fail2ban installiert (optional)
- [ ] SSH-Key-Authentifizierung statt Passwort (optional)
- [ ] Regelmäßige Updates eingeplant
- [ ] Log-Monitoring eingerichtet

---

## Troubleshooting

### App startet nicht:

```bash
# Logs prüfen
journalctl -u bis.service -n 50
tail -f /var/log/bis/error.log

# Manuell testen
su - bis
cd /opt/bis
source venv/bin/activate
gunicorn -c gunicorn_config.py app:app
```

### Nginx zeigt 502 Bad Gateway:

```bash
# Prüfen ob Gunicorn läuft
systemctl status bis.service
curl http://127.0.0.1:8000

# Nginx-Logs prüfen
tail -f /var/log/nginx/bis_error.log
```

### Datenbank-Fehler:

```bash
# Berechtigungen prüfen
ls -la /var/www/bis-data/database_main.db
chown bis:bis /var/www/bis-data/database_main.db
chmod 644 /var/www/bis-data/database_main.db

# Datenbank-Integrität prüfen
sqlite3 /var/www/bis-data/database_main.db "PRAGMA integrity_check;"
```

### Upload-Fehler:

```bash
# Berechtigungen prüfen
ls -la /var/www/bis-data/Daten
chown -R bis:bis /var/www/bis-data/Daten
chmod -R 755 /var/www/bis-data/Daten
```

---

## Performance-Optimierung

### Gunicorn Worker anpassen:

```python
# In gunicorn_config.py
workers = 4  # Anpassen je nach Last und CPU-Kerne
```

### Nginx Caching (optional):

```nginx
# In /etc/nginx/sites-available/bis
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=bis_cache:10m max_size=100m inactive=60m;

location / {
    proxy_cache bis_cache;
    proxy_cache_valid 200 10m;
    # ... restliche proxy_pass Konfiguration
}
```

---

## Support und Weitere Ressourcen

- Flask Dokumentation: https://flask.palletsprojects.com/
- Gunicorn Dokumentation: https://docs.gunicorn.org/
- Nginx Dokumentation: https://nginx.org/en/docs/
- Proxmox Dokumentation: https://pve.proxmox.com/wiki/Main_Page

---

**Viel Erfolg mit Ihrem BIS-Deployment! 🚀**

