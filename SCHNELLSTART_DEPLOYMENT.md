# 🚀 BIS - Schnellstart Deployment-Anleitung

Schritt-für-Schritt-Anleitung für das Deployment Ihrer BIS-Anwendung auf einem Proxmox LXC-Container.

## ⏱ Zeitaufwand
- **Erstmalige Installation:** ca. 30-45 Minuten
- **Updates:** ca. 5 Minuten

---

## 📋 Voraussetzungen

- [ ] Proxmox-Server mit Zugriff auf die Web-Oberfläche
- [ ] Ubuntu 24.04 oder Debian 12 Template in Proxmox
- [ ] Domain-Name (optional, für SSL)
- [ ] SSH-Client (Windows: PowerShell, PuTTY, oder Windows Terminal)

---

## 🔥 Schnellstart (3 Schritte)

### Schritt 1: LXC-Container in Proxmox erstellen

**In der Proxmox Web-Oberfläche:**

1. Klicken Sie auf **"Create CT"**
2. **General:**
   - Hostname: `bis-prod`
   - Password: [Sicheres Passwort setzen]
3. **Template:**
   - Ubuntu 24.04 Standard
4. **Disks:**
   - Disk size: `20 GB`
5. **CPU:**
   - Cores: `2`
6. **Memory:**
   - Memory: `2048 MB`
   - Swap: `512 MB`
7. **Network:**
   - IPv4: `DHCP` oder statische IP (z.B. `192.168.1.100/24`)
8. Klicken Sie auf **"Finish"** und starten Sie den Container

---

### Schritt 2: Server einrichten und Code hochladen

**A) Von Windows per PowerShell:**

```powershell
# 1. Mit Server verbinden
ssh root@192.168.1.100
# (Ersetzen Sie 192.168.1.100 mit Ihrer Container-IP)

# 2. System aktualisieren
apt update && apt upgrade -y

# 3. Basis-Pakete installieren
apt install -y git python3 python3-pip python3-venv nginx curl

# 4. Verzeichnisse erstellen
mkdir -p /opt/bis /var/www/bis-data /var/log/bis
useradd -m -s /bin/bash bis
chown -R bis:bis /opt/bis /var/www/bis-data /var/log/bis

# 5. Firewall einrichten
apt install -y ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 6. Abmelden (gleich wieder einloggen als bis)
exit
```

**B) Code vom Windows-PC hochladen:**

```powershell
# In neuer PowerShell auf Ihrem Windows-PC
cd C:\Projekte\BIS

# Code per SCP hochladen
scp -r * bis@192.168.1.100:/opt/bis/

# ODER: Nutzen Sie WinSCP oder FileZilla für grafische Übertragung
```

**Alternative: Direct Upload Script (Windows PowerShell):**

Speichern Sie dieses Script als `upload_to_server.ps1` in `C:\Projekte\BIS\`:

```powershell
# BIS Upload Script
$SERVER_IP = "192.168.1.100"  # ANPASSEN!
$SERVER_USER = "bis"
$SOURCE_DIR = "C:\Projekte\BIS"
$TARGET_DIR = "/opt/bis"

# Dateien hochladen
scp -r "${SOURCE_DIR}\*" "${SERVER_USER}@${SERVER_IP}:${TARGET_DIR}/"

Write-Host "Upload abgeschlossen!" -ForegroundColor Green
```

Dann ausführen:
```powershell
.\upload_to_server.ps1
```

---

### Schritt 3: App deployen und starten

**Auf dem Server (als bis-Benutzer):**

```bash
# Als bis einloggen
ssh bis@192.168.1.100

# Zum App-Verzeichnis wechseln
cd /opt/bis

# Deployment-Scripts ausführbar machen
chmod +x deployment/*.sh

# App deployen
./deployment/deploy_app.sh

# Zurück zu root wechseln (neue SSH-Session oder su)
exit
```

**Als root:**

```bash
ssh root@192.168.1.100

# Systemd Service einrichten
cp /opt/bis/deployment/bis.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable bis.service
systemctl start bis.service

# Status prüfen
systemctl status bis.service

# Nginx einrichten
cp /opt/bis/deployment/nginx_bis.conf /etc/nginx/sites-available/bis
ln -s /etc/nginx/sites-available/bis /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# Backups einrichten
chmod +x /opt/bis/deployment/backup_bis.sh
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/bis/deployment/backup_bis.sh >> /var/log/bis/backup.log 2>&1") | crontab -

# Health-Checks einrichten
chmod +x /opt/bis/deployment/healthcheck.sh
(crontab -l 2>/dev/null; echo "0 * * * * /opt/bis/deployment/healthcheck.sh >> /var/log/bis/healthcheck.log 2>&1") | crontab -
```

**Fertig! 🎉**

Ihre App läuft jetzt auf:
- `http://192.168.1.100` (oder Ihre Server-IP)

---

## 🔒 SSL/TLS einrichten (optional, empfohlen)

**Voraussetzung:** Domain zeigt auf Ihre Server-IP

```bash
# Als root
apt install -y certbot python3-certbot-nginx

# Zertifikat erstellen (DOMAIN ANPASSEN!)
certbot --nginx -d bis.ihre-domain.de

# Fertig! Ihre App läuft jetzt mit HTTPS
```

---

## 📊 Wichtige Befehle

### Status prüfen

```bash
# Service-Status
systemctl status bis.service

# Logs anzeigen
journalctl -u bis.service -f

# Health-Check
/opt/bis/deployment/healthcheck.sh

# Nginx-Logs
tail -f /var/log/nginx/bis_access.log
```

### Service neu starten

```bash
# App neu starten
systemctl restart bis.service

# Nginx neu laden
systemctl reload nginx
```

### Backup erstellen

```bash
# Manuelles Backup
/opt/bis/deployment/backup_bis.sh

# Backups anzeigen
ls -lh /opt/backups/
```

---

## 🔄 App aktualisieren

**Von Ihrem Windows-PC:**

```powershell
# Code hochladen
cd C:\Projekte\BIS
scp -r * bis@192.168.1.100:/opt/bis/
```

**Auf dem Server:**

```bash
# Als root
systemctl stop bis.service

# Als bis-Benutzer
su - bis
cd /opt/bis
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Zurück zu root
exit

# Service starten
systemctl start bis.service
systemctl status bis.service
```

---

## 🐛 Problemlösung

### App startet nicht

```bash
# Logs prüfen
journalctl -u bis.service -n 50

# Manuell testen
su - bis
cd /opt/bis
source venv/bin/activate
python app.py
```

### Nginx zeigt 502 Error

```bash
# Prüfen ob Gunicorn läuft
systemctl status bis.service

# Neustart
systemctl restart bis.service
systemctl restart nginx
```

### Berechtigungsprobleme

```bash
# Als root
chown -R bis:bis /opt/bis
chown -R bis:bis /var/www/bis-data
chmod -R 755 /var/www/bis-data
```

### Kann keine Dateien hochladen

```bash
# Upload-Verzeichnis prüfen
ls -la /var/www/bis-data/Daten/Schichtbuch/Themen/
chown -R bis:bis /var/www/bis-data/Daten
chmod -R 755 /var/www/bis-data/Daten
```

---

## 📁 Verzeichnisstruktur auf dem Server

```
/opt/bis/                    # App-Code
  ├── app.py
  ├── config.py
  ├── .env                   # Umgebungsvariablen (wird automatisch erstellt)
  ├── venv/                  # Python Virtual Environment
  ├── deployment/            # Deployment-Scripts und Configs
  └── ...

/var/www/bis-data/          # Daten (Datenbank + Uploads)
  ├── database_main.db      # SQLite-Datenbank
  └── Daten/                # Upload-Dateien
      └── Schichtbuch/
          └── Themen/

/var/log/bis/               # Log-Dateien
  ├── access.log
  ├── error.log
  ├── backup.log
  └── healthcheck.log

/opt/backups/               # Backups
  └── bis_backup_*.tar.gz
```

---

## 🔐 Sicherheits-Checkliste

Nach der Installation:

- [ ] Firewall aktiviert (`ufw status`)
- [ ] Starke Passwörter gesetzt
- [ ] SSL/TLS konfiguriert (für Produktion)
- [ ] SECRET_KEY in `/opt/bis/.env` geändert
- [ ] Backups laufen automatisch
- [ ] Health-Checks aktiv
- [ ] Nur notwendige Ports offen (22, 80, 443)

---

## 💡 Tipps

### Monitoring

```bash
# Ressourcen-Nutzung
htop

# Disk-Space
df -h

# Größte Dateien finden
du -h /var/www/bis-data/ | sort -rh | head -10
```

### Logs durchsuchen

```bash
# Fehler in App-Logs suchen
grep -i error /var/log/bis/error.log

# Zugriffe heute
grep "$(date +%d/%b/%Y)" /var/log/nginx/bis_access.log | wc -l
```

### Performance

```bash
# Worker-Prozesse prüfen
ps aux | grep gunicorn

# Nginx-Connections
ss -tun | grep :80 | wc -l
```

---

## 📚 Weitere Dokumentation

- **DEPLOYMENT_GUIDE.md** - Vollständige Deployment-Dokumentation
- **deployment/README.md** - Deployment-Scripts Dokumentation

---

## ✅ Nächste Schritte

Nach erfolgreicher Installation:

1. **Testen Sie die App** in Ihrem Browser
2. **Erstellen Sie ein manuelles Backup** zum Testen
3. **Führen Sie einen Health-Check aus**
4. **Konfigurieren Sie SSL/TLS** (für Produktion)
5. **Dokumentieren Sie Ihre spezifischen Einstellungen** (IP, Domain, etc.)

---

**Viel Erfolg! Bei Fragen konsultieren Sie DEPLOYMENT_GUIDE.md** 🚀

