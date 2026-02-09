# BIS - Cloudflare Tunnel Setup mit eigener Domain

Anleitung zur Einrichtung eines Cloudflare Tunnels für den Zugriff auf die BIS-Anwendung über die eigene Domain `hilli86.at` mit SSL-Verschlüsselung.

## Inhaltsverzeichnis
1. [Überblick](#1-überblick)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Cloudflare Account einrichten](#3-cloudflare-account-einrichten)
4. [Domain bei World4You konfigurieren](#4-domain-bei-world4you-konfigurieren)
5. [Cloudflare Tunnel installieren](#5-cloudflare-tunnel-installieren)
6. [Cloudflare Tunnel konfigurieren](#6-cloudflare-tunnel-konfigurieren)
7. [Cloudflare Tunnel als Windows Service einrichten](#7-cloudflare-tunnel-als-windows-service-einrichten)
8. [SSL/TLS konfigurieren](#8-ssltls-konfigurieren)
9. [Nginx-Konfiguration anpassen](#9-nginx-konfiguration-anpassen)
10. [Testen und Verifizieren](#10-testen-und-verifizieren)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Überblick

Diese Anleitung zeigt, wie Sie:
- Ihre BIS-Anwendung über die Domain `hilli86.at` erreichbar machen
- Einen Cloudflare Tunnel einrichten, der Ihre lokale Anwendung sicher ins Internet bringt
- SSL/TLS-Verschlüsselung über Cloudflare aktivieren (kostenlos)
- Keine Port-Weiterleitung im Router benötigen

**Vorteile von Cloudflare Tunnel:**
- ✅ Keine Port-Weiterleitung im Router nötig
- ✅ Automatisches SSL-Zertifikat von Cloudflare
- ✅ DDoS-Schutz durch Cloudflare
- ✅ Kostenlos für persönliche Nutzung
- ✅ Funktioniert hinter NAT/Firewall

---

## 2. Voraussetzungen

- ✅ BIS-Anwendung läuft lokal (siehe `WINDOWS_DEPLOYMENT_GUIDE.md`)
- ✅ Nginx läuft auf Port 80/443
- ✅ Domain `hilli86.at` bei World4You registriert
- ✅ Cloudflare Account (kostenlos)
- ✅ Administratorrechte auf Windows

---

## 3. Cloudflare Account einrichten

### Schritt 1: Cloudflare Account erstellen

1. **Account erstellen:**
   - Besuchen Sie [cloudflare.com](https://www.cloudflare.com/)
   - Klicken Sie auf "Sign Up" und erstellen Sie einen kostenlosen Account

2. **Domain hinzufügen:**
   - Nach dem Login: "Add a Site" klicken
   - Ihre Domain `hilli86.at` eingeben
   - Plan wählen: **Free Plan** (kostenlos) ist ausreichend
   - Cloudflare scannt automatisch Ihre DNS-Einträge

### Schritt 2: Nameserver bei World4You ändern

**Wichtig:** Sie müssen die Nameserver bei World4You auf die Cloudflare-Nameserver umstellen.

1. **Cloudflare Nameserver notieren:**
   - In Cloudflare Dashboard → Overview
   - Sie sehen zwei Nameserver, z.B.:
     - `alex.ns.cloudflare.com`
     - `sue.ns.cloudflare.com`

2. **Bei World4You Nameserver ändern:**
   - Loggen Sie sich in Ihr World4You-Kundencenter ein
   - Gehen Sie zu Domain-Verwaltung → DNS-Verwaltung
   - Ändern Sie die Nameserver auf die von Cloudflare angegebenen
   - **Hinweis:** Die Änderung kann 24-48 Stunden dauern (meist schneller)

3. **Verifizierung:**
   - In Cloudflare Dashboard → Overview
   - Status sollte "Active" werden, sobald die Nameserver-Änderung wirksam ist

---

## 4. Domain bei World4You konfigurieren

**Wichtig:** Nachdem Sie die Nameserver auf Cloudflare umgestellt haben, werden alle DNS-Einträge über Cloudflare verwaltet, nicht mehr über World4You.

Falls Sie noch andere Subdomains oder E-Mail-Server bei World4You nutzen:
- Diese müssen später in Cloudflare als DNS-Einträge hinzugefügt werden
- E-Mail-Server: MX-Records in Cloudflare eintragen

---

## 5. Cloudflare Tunnel installieren

### Schritt 1: Cloudflared herunterladen

1. **Cloudflared herunterladen:**
   - Besuchen Sie [github.com/cloudflare/cloudflared/releases](https://github.com/cloudflare/cloudflared/releases)
   - Laden Sie die neueste Windows-Version herunter (`cloudflared-windows-amd64.exe`)
   - Oder verwenden Sie Chocolatey: `choco install cloudflared`

2. **Cloudflared installieren:**
   ```powershell
   # PowerShell als Administrator
   # Datei nach C:\cloudflared\ kopieren
   New-Item -ItemType Directory -Path "C:\cloudflared" -Force
   Copy-Item cloudflared-windows-amd64.exe C:\cloudflared\cloudflared.exe
   
   # Zu PATH hinzufügen (optional)
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\cloudflared", "Machine")
   ```

### Schritt 2: Cloudflared authentifizieren

```powershell
# PowerShell
cd C:\cloudflared

# Login zu Cloudflare (öffnet Browser)
.\cloudflared.exe tunnel login
```

Dies öffnet einen Browser, in dem Sie sich bei Cloudflare anmelden und den Tunnel autorisieren.

**Ergebnis:** Eine Zertifikatdatei wird erstellt: `C:\Users\<IhrBenutzer>\.cloudflared\cert.pem`

---

## 6. Cloudflare Tunnel konfigurieren

### Schritt 1: Tunnel erstellen

```powershell
# PowerShell als Administrator
cd C:\cloudflared

# Tunnel erstellen (Name: bis-tunnel)
.\cloudflared.exe tunnel create bis-tunnel
```

**Notieren Sie sich die Tunnel-ID** (wird ausgegeben, z.B. `abc123-def456-ghi789`)

### Schritt 2: Route konfigurieren

```powershell
# Route für Domain hinzufügen
.\cloudflared.exe tunnel route dns bis-tunnel hilli86.at
```

Dies erstellt automatisch einen DNS-CNAME-Eintrag in Cloudflare.

### Schritt 3: Konfigurationsdatei erstellen

Erstellen Sie die Datei `C:\cloudflared\config.yml`:

```yaml
tunnel: bis-tunnel
credentials-file: C:\Users\<IhrBenutzer>\.cloudflared\<TUNNEL-ID>.json

ingress:
  # HTTPS-Traffic von Cloudflare zu lokalem Nginx
  - hostname: hilli86.at
    service: https://localhost:443
    originRequest:
      noHappyEyeballs: true
      connectTimeout: 30s
      tcpKeepAlive: 30s
      keepAliveTimeout: 90s
      keepAliveConnections: 100
      httpHostHeader: hilli86.at
  
  # HTTP-Traffic umleiten zu HTTPS
  - hostname: www.hilli86.at
    service: https://localhost:443
    originRequest:
      httpHostHeader: www.hilli86.at
  
  # Catch-all: Alle anderen Anfragen verwerfen
  - service: http_status:404
```

**Wichtig:** 
- Ersetzen Sie `<IhrBenutzer>` mit Ihrem Windows-Benutzernamen
- Ersetzen Sie `<TUNNEL-ID>` mit der tatsächlichen Tunnel-ID (Dateiname der JSON-Datei)

### Schritt 4: Konfiguration testen

```powershell
cd C:\cloudflared

# Tunnel im Testmodus starten
.\cloudflared.exe tunnel --config config.yml run bis-tunnel
```

Sie sollten sehen:
```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has started! Visit it at (it may take some time to be reachable):     |
|  https://hilli86.at                                                                        |
+--------------------------------------------------------------------------------------------+
```

**Stoppen Sie den Tunnel mit `Ctrl+C`** nach dem Test.

---

## 7. Cloudflare Tunnel als Windows Service einrichten

### Schritt 1: Service installieren

```powershell
# PowerShell als Administrator
cd C:\cloudflared

# Service installieren
.\cloudflared.exe service install
```

### Schritt 2: Service konfigurieren

Die Service-Konfiguration wird automatisch erstellt. Falls Sie die Konfigurationsdatei anpassen müssen:

```powershell
# Service-Konfiguration prüfen
Get-Service cloudflared

# Service starten
Start-Service cloudflared

# Service-Status prüfen
Get-Service cloudflared
```

### Schritt 3: Service-Logs prüfen

```powershell
# Event Viewer öffnen
eventvwr.msc

# Oder PowerShell
Get-EventLog -LogName Application -Source cloudflared -Newest 20
```

### Schritt 4: Automatischer Start

Der Service sollte automatisch starten. Falls nicht:

```powershell
# Service auf Auto-Start setzen
Set-Service cloudflared -StartupType Automatic
```

---

## 8. SSL/TLS konfigurieren

### Schritt 1: SSL/TLS-Modus in Cloudflare

1. **Cloudflare Dashboard öffnen:**
   - Gehen Sie zu: SSL/TLS → Overview
   - **Encryption mode:** Wählen Sie **"Full"** oder **"Full (strict)"**

   **Empfehlung:**
   - **"Full"**: Funktioniert mit selbstsignierten Zertifikaten
   - **"Full (strict)"**: Benötigt ein gültiges Zertifikat (empfohlen, wenn Sie ein Let's Encrypt Zertifikat haben)

2. **TLS-Version:**
   - SSL/TLS → Edge Certificates
   - **Minimum TLS Version:** TLS 1.2 (empfohlen)

### Schritt 2: Automatisches HTTPS-Redirect

1. **SSL/TLS → Edge Certificates:**
   - **Always Use HTTPS:** Aktivieren (ON)

2. **SSL/TLS → Overview:**
   - **Automatic HTTPS Rewrites:** Aktivieren (ON)

### Schritt 3: Origin-Zertifikat (optional, für Full Strict)

Falls Sie "Full (strict)" verwenden möchten:

```powershell
# Origin-Zertifikat erstellen in Cloudflare Dashboard
# SSL/TLS → Origin Server → Create Certificate
```

Dann das Zertifikat in Nginx verwenden (siehe nächster Abschnitt).

---

## 9. Nginx-Konfiguration anpassen

### Schritt 1: Nginx-Konfiguration aktualisieren

Bearbeiten Sie `C:\nginx\conf\sites-available\bis.conf`:

```nginx
# HTTP -> HTTPS Redirect
server {
    listen 80;
    server_name hilli86.at www.hilli86.at;
    
    # Redirect zu HTTPS
    return 301 https://$host$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name hilli86.at www.hilli86.at;

    # SSL-Zertifikate
    # Option 1: Selbstsigniertes Zertifikat (für Cloudflare "Full" Modus)
    ssl_certificate C:/nginx/conf/ssl/bis/bis.crt;
    ssl_certificate_key C:/nginx/conf/ssl/bis/bis.key;
    
    # Option 2: Cloudflare Origin-Zertifikat (für "Full Strict" Modus)
    # ssl_certificate C:/nginx/conf/ssl/bis/origin.crt;
    # ssl_certificate_key C:/nginx/conf/ssl/bis/origin.key;
    
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

    # Wichtig: Host-Header von Cloudflare weiterleiten
    # Cloudflare sendet den ursprünglichen Host-Header
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Cloudflare-spezifische Header
    proxy_set_header CF-Connecting-IP $http_cf_connecting_ip;
    proxy_set_header CF-Ray $http_cf_ray;
    proxy_set_header CF-Visitor $http_cf_visitor;

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

### Schritt 2: Nginx neu laden

```powershell
# PowerShell als Administrator
cd C:\nginx

# Konfiguration testen
.\nginx.exe -t

# Nginx neu laden
.\nginx.exe -s reload

# Oder Service neu starten
Restart-Service Nginx
```

---

## 10. Testen und Verifizieren

### Schritt 1: DNS-Verifizierung

```powershell
# PowerShell
# Prüfen ob DNS korrekt aufgelöst wird
nslookup hilli86.at

# Sollte die Cloudflare-IP-Adressen zurückgeben
```

### Schritt 2: SSL-Test

1. **Online SSL-Test:**
   - Besuchen Sie [ssllabs.com/ssltest](https://www.ssllabs.com/ssltest/)
   - Geben Sie `hilli86.at` ein
   - Prüfen Sie die SSL-Konfiguration

2. **Browser-Test:**
   - Öffnen Sie `https://hilli86.at` im Browser
   - Prüfen Sie das SSL-Zertifikat (sollte von Cloudflare sein)
   - Keine Browser-Warnung sollte erscheinen

### Schritt 3: Tunnel-Status prüfen

```powershell
# PowerShell
# Tunnel-Status prüfen
cd C:\cloudflared
.\cloudflared.exe tunnel list

# Tunnel-Info anzeigen
.\cloudflared.exe tunnel info bis-tunnel
```

### Schritt 4: Logs prüfen

```powershell
# Cloudflare Tunnel Logs
Get-EventLog -LogName Application -Source cloudflared -Newest 20

# Nginx Logs
Get-Content C:\nginx\logs\bis_access.log -Tail 20
Get-Content C:\nginx\logs\bis_error.log -Tail 20

# Waitress Logs
Get-Content C:\BIS\logs\waitress_stdout.log -Tail 20
```

---

## 11. Troubleshooting

### Problem: Tunnel startet nicht

**Lösung:**
```powershell
# Service-Status prüfen
Get-Service cloudflared

# Logs prüfen
Get-EventLog -LogName Application -Source cloudflared -Newest 50

# Manuell testen
cd C:\cloudflared
.\cloudflared.exe tunnel --config config.yml run bis-tunnel
```

### Problem: DNS löst nicht auf

**Lösung:**
1. Prüfen Sie in Cloudflare Dashboard → DNS → Records
2. Es sollte ein CNAME-Eintrag für `hilli86.at` existieren
3. Falls nicht: `.\cloudflared.exe tunnel route dns bis-tunnel hilli86.at` erneut ausführen

### Problem: SSL-Zertifikat-Fehler

**Lösung:**
1. Prüfen Sie SSL/TLS → Overview → Encryption mode
2. Stellen Sie sicher, dass "Full" oder "Full (strict)" aktiviert ist
3. Prüfen Sie, ob Nginx das Zertifikat korrekt lädt:
   ```powershell
   cd C:\nginx
   .\nginx.exe -t
   ```

### Problem: 502 Bad Gateway

**Lösung:**
```powershell
# Prüfen ob Nginx läuft
Get-Service Nginx
netstat -ano | findstr :443

# Prüfen ob Waitress läuft
Get-Service BIS-Waitress
netstat -ano | findstr :8000

# Nginx-Logs prüfen
Get-Content C:\nginx\logs\bis_error.log -Tail 50
```

### Problem: Tunnel verbindet nicht

**Lösung:**
1. Prüfen Sie die Firewall:
   ```powershell
   # Cloudflared sollte ausgehende Verbindungen erlauben
   Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*cloudflare*"}
   ```

2. Prüfen Sie die Konfigurationsdatei:
   ```powershell
   cd C:\cloudflared
   # Syntax prüfen
   .\cloudflared.exe tunnel --config config.yml --loglevel debug run bis-tunnel
   ```

### Problem: Domain zeigt auf falsche Seite

**Lösung:**
1. Prüfen Sie die `config.yml`:
   - `hostname` sollte `hilli86.at` sein
   - `service` sollte `https://localhost:443` sein

2. Prüfen Sie Nginx `server_name`:
   - Sollte `hilli86.at www.hilli86.at` enthalten

### Problem: Performance-Probleme

**Lösung:**
1. Cloudflare Dashboard → Speed → Optimization
   - **Auto Minify:** Aktivieren für CSS, HTML, JavaScript
   - **Brotli:** Aktivieren

2. Caching optimieren:
   - Cloudflare Dashboard → Caching → Configuration
   - **Caching Level:** Standard

---

## Nützliche Befehle

### Cloudflare Tunnel Management

```powershell
# Tunnel-Liste anzeigen
cd C:\cloudflared
.\cloudflared.exe tunnel list

# Tunnel-Info
.\cloudflared.exe tunnel info bis-tunnel

# Tunnel löschen (falls nötig)
.\cloudflared.exe tunnel delete bis-tunnel

# Route hinzufügen
.\cloudflared.exe tunnel route dns bis-tunnel hilli86.at

# Route entfernen
.\cloudflared.exe tunnel route dns delete hilli86.at
```

### Service-Management

```powershell
# Cloudflare Tunnel Service
Start-Service cloudflared
Stop-Service cloudflared
Restart-Service cloudflared
Get-Service cloudflared

# Nginx Service
Start-Service Nginx
Restart-Service Nginx
Get-Service Nginx

# BIS-Waitress Service
Start-Service BIS-Waitress
Get-Service BIS-Waitress
```

### Logs anzeigen

```powershell
# Cloudflare Tunnel Logs
Get-EventLog -LogName Application -Source cloudflared -Newest 50

# Nginx Logs
Get-Content C:\nginx\logs\bis_access.log -Tail 50 -Wait
Get-Content C:\nginx\logs\bis_error.log -Tail 50

# BIS Logs
Get-Content C:\BIS\logs\waitress_stdout.log -Tail 50
```

---

## Sicherheits-Checkliste

- [ ] Cloudflare Account erstellt
- [ ] Nameserver bei World4You auf Cloudflare umgestellt
- [ ] Cloudflare Tunnel installiert und konfiguriert
- [ ] Tunnel als Windows Service eingerichtet
- [ ] SSL/TLS-Modus auf "Full" oder "Full (strict)" gesetzt
- [ ] "Always Use HTTPS" aktiviert
- [ ] Nginx-Konfiguration angepasst
- [ ] Domain funktioniert über HTTPS
- [ ] Logs überwachen eingerichtet
- [ ] Backup der Tunnel-Konfiguration erstellt

---

## Weitere Ressourcen

- [Cloudflare Tunnel Dokumentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflare DNS Dokumentation](https://developers.cloudflare.com/dns/)
- [Cloudflare SSL/TLS Dokumentation](https://developers.cloudflare.com/ssl/)

---

**Viel Erfolg mit Ihrem Cloudflare Tunnel Setup! 🚀**
