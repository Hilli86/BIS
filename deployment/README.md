# BIS Deployment-Verzeichnis

Dieses Verzeichnis enthält alle notwendigen Dateien für das Deployment der BIS-Anwendung auf einem Produktionsserver.

## 📁 Dateien

### Installations-Scripts

- **install_server.sh** - Automatische Server-Einrichtung (als root ausführen)
- **deploy_app.sh** - App-Deployment (als bis-Benutzer ausführen)

### Konfigurationsdateien

- **bis.service** - Systemd Service-Datei für Gunicorn
- **nginx_bis.conf** - Nginx-Konfiguration (HTTP)
- **nginx_bis_ssl.conf** - Nginx-Konfiguration mit SSL/TLS

### Wartungs-Scripts

- **backup_bis.sh** - Backup-Script für Datenbank und Uploads
- **healthcheck.sh** - Health-Check Script für Monitoring

## 🚀 Schnellstart-Anleitung

### 1. Server vorbereiten (als root)

```bash
# Scripts ausführbar machen
chmod +x deployment/*.sh

# Server-Installation durchführen
./deployment/install_server.sh
```

### 2. Code hochladen

```bash
# Von Ihrem Windows-PC (PowerShell)
scp -r C:\Projekte\BIS\* bis@SERVER-IP:/opt/bis/
```

### 3. App deployen (als bis-Benutzer)

```bash
# Als bis-Benutzer einloggen
su - bis

# Deployment durchführen
cd /opt/bis
./deployment/deploy_app.sh
```

### 4. Systemd Service einrichten (als root)

```bash
# Service-Datei kopieren
cp /opt/bis/deployment/bis.service /etc/systemd/system/

# Service aktivieren und starten
systemctl daemon-reload
systemctl enable bis.service
systemctl start bis.service

# Status prüfen
systemctl status bis.service
```

### 5. Nginx einrichten (als root)

```bash
# Nginx-Konfiguration kopieren
cp /opt/bis/deployment/nginx_bis.conf /etc/nginx/sites-available/bis

# Aktivieren
ln -s /etc/nginx/sites-available/bis /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default  # Optional

# Konfiguration testen und neu laden
nginx -t
systemctl restart nginx
```

### 6. SSL/TLS einrichten (optional, als root)

```bash
# Let's Encrypt Zertifikat erstellen
certbot --nginx -d ihre-domain.de

# Oder manuelle SSL-Konfiguration
cp /opt/bis/deployment/nginx_bis_ssl.conf /etc/nginx/sites-available/bis
# Domain anpassen in der Datei!
nano /etc/nginx/sites-available/bis
nginx -t
systemctl reload nginx
```

### 7. Backups einrichten (als root)

```bash
# Backup-Script ausführbar machen
chmod +x /opt/bis/deployment/backup_bis.sh

# Backup-Ordner erstellen
mkdir -p /opt/backups

# Script nach /opt/backups kopieren (optional)
cp /opt/bis/deployment/backup_bis.sh /opt/backups/

# Cronjob für tägliche Backups (2:00 Uhr)
crontab -e
```

Fügen Sie hinzu:
```
0 2 * * * /opt/bis/deployment/backup_bis.sh >> /var/log/bis/backup.log 2>&1
```

### 8. Health-Check einrichten (als root)

```bash
# Health-Check Script ausführbar machen
chmod +x /opt/bis/deployment/healthcheck.sh

# Cronjob für stündliche Checks
crontab -e
```

Fügen Sie hinzu:
```
0 * * * * /opt/bis/deployment/healthcheck.sh >> /var/log/bis/healthcheck.log 2>&1
```

## 🔧 Manuelle Konfiguration

Falls die automatischen Scripts nicht funktionieren, folgen Sie dem vollständigen **DEPLOYMENT_GUIDE.md** im Hauptverzeichnis.

## 📋 Nützliche Befehle

### Service-Management

```bash
# Service neu starten
systemctl restart bis.service

# Service stoppen
systemctl stop bis.service

# Service-Status
systemctl status bis.service

# Logs ansehen
journalctl -u bis.service -f
```

### Nginx

```bash
# Nginx neu laden
nginx -t && systemctl reload nginx

# Nginx-Logs
tail -f /var/log/nginx/bis_access.log
tail -f /var/log/nginx/bis_error.log
```

### Backups

```bash
# Manuelles Backup erstellen
/opt/bis/deployment/backup_bis.sh

# Backups anzeigen
ls -lh /opt/backups/

# Backup wiederherstellen (Beispiel)
systemctl stop bis.service
cd /opt/backups
tar -xzf bis_backup_YYYYMMDD_HHMMSS.tar.gz
# ... weitere Schritte siehe backup_info.txt im Backup
```

### Health-Check

```bash
# Manueller Health-Check
/opt/bis/deployment/healthcheck.sh
```

## 🐛 Troubleshooting

### App startet nicht

```bash
# Logs prüfen
journalctl -u bis.service -n 50
tail -f /var/log/bis/error.log

# Als bis-Benutzer manuell testen
su - bis
cd /opt/bis
source venv/bin/activate
gunicorn -c gunicorn_config.py app:app
```

### Nginx zeigt 502 Bad Gateway

```bash
# Prüfen ob Gunicorn läuft
systemctl status bis.service
curl http://127.0.0.1:8000

# Nginx-Logs
tail -f /var/log/nginx/bis_error.log
```

### Berechtigungsprobleme

```bash
# Berechtigungen zurücksetzen
chown -R bis:bis /opt/bis
chown -R bis:bis /var/www/bis-data
chown -R bis:bis /var/log/bis
chmod -R 755 /var/www/bis-data
```

## 📚 Weitere Dokumentation

Siehe **DEPLOYMENT_GUIDE.md** im Hauptverzeichnis für die vollständige Dokumentation.

## 🔐 Sicherheits-Checkliste

- [ ] Starkes Root-Passwort
- [ ] Firewall aktiviert
- [ ] SSL/TLS konfiguriert
- [ ] SECRET_KEY geändert
- [ ] Automatische Backups eingerichtet
- [ ] Regelmäßige Updates geplant
- [ ] Log-Monitoring aktiv

## 💡 Support

Bei Problemen:
1. Logs prüfen (journalctl, /var/log/bis/)
2. Health-Check ausführen
3. DEPLOYMENT_GUIDE.md konsultieren



