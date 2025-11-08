# SSL/TLS mit Self-Signed Certificate für BIS (Internes Netzwerk)

Diese Anleitung zeigt, wie Sie SSL/TLS für das BIS-System mit einem Self-Signed Certificate im internen Netzwerk einrichten.

## Inhaltsverzeichnis
1. [Übersicht](#übersicht)
2. [Voraussetzungen](#voraussetzungen)
3. [Zertifikat erstellen](#zertifikat-erstellen)
4. [Nginx konfigurieren](#nginx-konfigurieren)
5. [Einrichtung](#einrichtung)
6. [Zugriff](#zugriff)
7. [Zertifikat auf Clients installieren (optional)](#zertifikat-auf-clients-installieren-optional)
8. [Troubleshooting](#troubleshooting)

---

## Übersicht

Ein Self-Signed Certificate ermöglicht verschlüsselte HTTPS-Verbindungen ohne öffentliche Domain oder externe Zertifizierungsstelle. Ideal für:
- Interne Netzwerke
- Entwicklungsumgebungen
- Test-Server
- Kleine Installationen ohne Domain

**Hinweis:** Browser zeigen beim ersten Besuch eine Sicherheitswarnung an, die einmalig akzeptiert werden muss.

---

## Voraussetzungen

- Debian/Ubuntu Server
- Nginx installiert
- OpenSSL installiert (`apt install openssl`)
- Root-Zugriff auf den Server

---

## Zertifikat erstellen

### Option 1: Bash-Script (empfohlen)

Erstellen Sie die Datei `create_self_signed_cert.sh`:

```bash
#!/bin/bash
# Script zum Erstellen eines Self-Signed SSL-Zertifikats für BIS

# Verzeichnis für Zertifikate erstellen
CERT_DIR="/etc/nginx/ssl/bis"
mkdir -p $CERT_DIR

# Server-IP oder Hostname (anpassen!)
SERVER_NAME="${1:-bis-server.local}"  # Standard: bis-server.local, kann auch IP sein

echo "Erstelle Self-Signed Certificate für: $SERVER_NAME"
echo "Verzeichnis: $CERT_DIR"

# Zertifikat erstellen (gültig für 10 Jahre)
openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
  -keyout $CERT_DIR/bis.key \
  -out $CERT_DIR/bis.crt \
  -subj "/C=DE/ST=State/L=City/O=BIS/CN=$SERVER_NAME" \
  -addext "subjectAltName=DNS:$SERVER_NAME,DNS:*.$SERVER_NAME,IP:127.0.0.1"

# Berechtigungen setzen
chmod 600 $CERT_DIR/bis.key
chmod 644 $CERT_DIR/bis.crt
chown root:root $CERT_DIR/bis.key $CERT_DIR/bis.crt

echo ""
echo "✓ Zertifikat erstellt!"
echo "  Key: $CERT_DIR/bis.key"
echo "  Cert: $CERT_DIR/bis.crt"
echo ""
echo "Sie können das Zertifikat jetzt in der Nginx-Konfiguration verwenden."
```

**Verwendung:**
```bash
# Script ausführbar machen
chmod +x create_self_signed_cert.sh

# Mit Hostname
sudo bash create_self_signed_cert.sh bis-server.local

# Mit IP-Adresse
sudo bash create_self_signed_cert.sh 192.168.1.100

# Standard (bis-server.local)
sudo bash create_self_signed_cert.sh
```

### Option 2: Manuell mit OpenSSL

```bash
# Verzeichnis erstellen
sudo mkdir -p /etc/nginx/ssl/bis
cd /etc/nginx/ssl/bis

# Zertifikat erstellen (ersetzen Sie bis-server.local mit Ihrer IP oder Hostname)
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
  -keyout bis.key \
  -out bis.crt \
  -subj "/C=DE/ST=State/L=City/O=BIS/CN=bis-server.local" \
  -addext "subjectAltName=DNS:bis-server.local,DNS:*.bis-server.local,IP:127.0.0.1"

# Berechtigungen setzen
sudo chmod 600 bis.key
sudo chmod 644 bis.crt
sudo chown root:root bis.key bis.crt
```

### Option 3: Python-Script

Falls OpenSSL nicht verfügbar ist, können Sie dieses Python-Script verwenden:

```python
#!/usr/bin/env python3
"""Erstellt ein Self-Signed SSL-Zertifikat für BIS"""

import os
import subprocess
import sys

CERT_DIR = "/etc/nginx/ssl/bis"
SERVER_NAME = sys.argv[1] if len(sys.argv) > 1 else "bis-server.local"

# Verzeichnis erstellen
os.makedirs(CERT_DIR, exist_ok=True)

# Zertifikat erstellen
cmd = [
    "openssl", "req", "-x509", "-nodes", "-days", "3650",
    "-newkey", "rsa:4096",
    "-keyout", f"{CERT_DIR}/bis.key",
    "-out", f"{CERT_DIR}/bis.crt",
    "-subj", f"/C=DE/ST=State/L=City/O=BIS/CN={SERVER_NAME}"
]

subprocess.run(cmd, check=True)

# Berechtigungen setzen
os.chmod(f"{CERT_DIR}/bis.key", 0o600)
os.chmod(f"{CERT_DIR}/bis.crt", 0o644)

print(f"✓ Zertifikat erstellt für: {SERVER_NAME}")
print(f"  Key: {CERT_DIR}/bis.key")
print(f"  Cert: {CERT_DIR}/bis.crt")
```

**Verwendung:**
```bash
sudo python3 create_cert.py bis-server.local
```

---

## Nginx konfigurieren

Erstellen Sie die Datei `deployment/nginx_bis_selfsigned.conf`:

```nginx
# HTTP -> HTTPS Redirect (optional, kann auch weggelassen werden)
server {
    listen 80;
    server_name _;  # Alle Hostnamen/IPs
    
    # Optional: Redirect zu HTTPS
    # return 301 https://$host$request_uri;
    
    # Oder: Weiterleitung zu HTTPS mit Port
    # return 301 https://$host:443$request_uri;
    
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
    server_name _;  # Alle Hostnamen/IPs akzeptieren

    # Self-Signed Zertifikate
    ssl_certificate /etc/nginx/ssl/bis/bis.crt;
    ssl_certificate_key /etc/nginx/ssl/bis/bis.key;
    
    # SSL-Konfiguration (kompatibel mit Self-Signed)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    
    # SSL Session Cache
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # OCSP Stapling deaktiviert (nicht verfügbar bei Self-Signed)
    # ssl_stapling off;

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
    # HSTS deaktiviert bei Self-Signed (Browser-Warnung würde bleiben)
    # add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

---

## Einrichtung

### Schritt 1: Zertifikat erstellen

```bash
# Script ausführbar machen
chmod +x create_self_signed_cert.sh

# Zertifikat erstellen (mit Ihrer IP oder Hostname)
sudo bash create_self_signed_cert.sh 192.168.1.100
# oder
sudo bash create_self_signed_cert.sh bis-server.local
```

### Schritt 2: Nginx-Konfiguration aktivieren

```bash
# Konfiguration kopieren
sudo cp deployment/nginx_bis_selfsigned.conf /etc/nginx/sites-available/bis

# Symlink erstellen
sudo ln -s /etc/nginx/sites-available/bis /etc/nginx/sites-enabled/

# Alte Konfiguration entfernen (falls vorhanden)
sudo rm /etc/nginx/sites-enabled/default
```

### Schritt 3: Nginx testen und neu laden

```bash
# Konfiguration testen
sudo nginx -t

# Bei Erfolg: Nginx neu laden
sudo systemctl reload nginx

# Oder neu starten
sudo systemctl restart nginx
```

### Schritt 4: Firewall konfigurieren (falls aktiv)

```bash
# Port 443 öffnen
sudo ufw allow 443/tcp

# Port 80 öffnen (falls HTTP-Redirect verwendet wird)
sudo ufw allow 80/tcp

# Firewall-Status prüfen
sudo ufw status
```

---

## Zugriff

### Mit IP-Adresse
```
https://192.168.1.100
```

### Mit Hostname (falls DNS konfiguriert)
```
https://bis-server.local
```

### Browser-Warnung beim ersten Besuch

Beim ersten Besuch erscheint eine Sicherheitswarnung:

1. **Chrome/Edge:** 
   - "Erweitert" klicken
   - "Weiter zu [Server] (unsicher)" klicken

2. **Firefox:**
   - "Erweitert" klicken
   - "Risiko akzeptieren und fortfahren" klicken

3. **Safari:**
   - "Erweitert" klicken
   - "Trotzdem fortfahren" klicken

Nach der einmaligen Akzeptanz funktioniert die Verbindung normal.

---

## Zertifikat auf Clients installieren (optional)

Um die Browser-Warnung zu vermeiden, können Sie das Zertifikat auf den Clients installieren.

### Windows

1. **Zertifikat herunterladen:**
   ```bash
   # Auf dem Server
   sudo cp /etc/nginx/ssl/bis/bis.crt /tmp/
   sudo chmod 644 /tmp/bis.crt
   ```
   Dann von Windows aus: `\\server-ip\tmp\bis.crt` oder per SCP

2. **Zertifikat installieren:**
   - Doppelklick auf `bis.crt`
   - "Zertifikat installieren" klicken
   - "Aktuellen Benutzer" wählen
   - "Weiter" klicken
   - "Alle Zertifikate in folgendem Speicher speichern" wählen
   - "Durchsuchen" → "Vertrauenswürdige Stammzertifizierungsstellen" wählen
   - "Weiter" → "Fertig"

### Linux (Debian/Ubuntu)

```bash
# Zertifikat kopieren
sudo cp /etc/nginx/ssl/bis/bis.crt /usr/local/share/ca-certificates/bis.crt

# CA-Zertifikate aktualisieren
sudo update-ca-certificates

# Browser neu starten
```

### macOS

1. **Zertifikat herunterladen** (wie bei Windows)

2. **Zertifikat installieren:**
   - Doppelklick auf `bis.crt`
   - Keychain öffnet sich
   - Zertifikat zu "System" Keychain hinzufügen (nicht "Login")
   - Doppelklick auf das Zertifikat in Keychain
   - "Vertrauen" erweitern
   - "Beim Verwenden dieses Zertifikats: Immer vertrauen" wählen

### Android

1. Zertifikat auf Gerät kopieren
2. Einstellungen → Sicherheit → Verschlüsselung & Anmeldedaten
3. "Zertifikat aus Speicher installieren"
4. `bis.crt` auswählen
5. Name vergeben (z.B. "BIS Server")
6. "VPN und Apps" oder "Alle" wählen

---

## Troubleshooting

### Problem: Nginx startet nicht

**Lösung:**
```bash
# Fehler prüfen
sudo nginx -t

# Logs prüfen
sudo tail -f /var/log/nginx/error.log
```

### Problem: Zertifikat wird nicht gefunden

**Lösung:**
```bash
# Pfad prüfen
sudo ls -la /etc/nginx/ssl/bis/

# Berechtigungen prüfen
sudo chmod 600 /etc/nginx/ssl/bis/bis.key
sudo chmod 644 /etc/nginx/ssl/bis/bis.crt
```

### Problem: Browser zeigt weiterhin Warnung

**Lösung:**
- Zertifikat auf Client installieren (siehe oben)
- Browser-Cache leeren
- Browser neu starten

### Problem: Verbindung wird abgelehnt

**Lösung:**
```bash
# Firewall prüfen
sudo ufw status

# Port 443 öffnen
sudo ufw allow 443/tcp

# Nginx Status prüfen
sudo systemctl status nginx

# Ports prüfen
sudo netstat -tlnp | grep :443
```

### Problem: SSL-Protokoll-Fehler

**Lösung:**
- Stellen Sie sicher, dass moderne SSL-Protokolle aktiviert sind
- Prüfen Sie die `ssl_protocols` Einstellung in der Nginx-Konfiguration

---

## Zertifikat erneuern

Self-Signed Certificates sind standardmäßig 10 Jahre gültig. Um ein neues Zertifikat zu erstellen:

```bash
# Altes Zertifikat sichern (optional)
sudo mv /etc/nginx/ssl/bis /etc/nginx/ssl/bis.backup

# Neues Zertifikat erstellen
sudo bash create_self_signed_cert.sh bis-server.local

# Nginx neu laden
sudo nginx -t && sudo systemctl reload nginx
```

---

## Sicherheitshinweise

1. **Self-Signed Certificates sind nicht für öffentliche Server geeignet**
   - Nur für interne Netzwerke verwenden
   - Nicht für Produktionsumgebungen mit externen Benutzern

2. **Zertifikat-Schlüssel schützen**
   - Private Keys niemals weitergeben
   - Berechtigungen auf 600 setzen
   - Regelmäßig Backups erstellen

3. **Regelmäßige Updates**
   - Nginx und OpenSSL aktuell halten
   - Zertifikat vor Ablauf erneuern

4. **Alternative für Produktion**
   - Für öffentliche Server: Let's Encrypt verwenden
   - Für größere interne Netzwerke: Private CA einrichten

---

## Weitere Ressourcen

- [Nginx SSL Documentation](https://nginx.org/en/docs/http/configuring_https_servers.html)
- [OpenSSL Documentation](https://www.openssl.org/docs/)
- [BIS Deployment Guide](DEPLOYMENT_GUIDE.md)

---

**Erstellt:** $(date)
**Version:** 1.0

