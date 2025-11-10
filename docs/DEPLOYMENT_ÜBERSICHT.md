# 📦 BIS Deployment - Komplette Übersicht

Willkommen zur Deployment-Dokumentation für das BIS (Betriebsinformationssystem)!

## 📚 Verfügbare Dokumentation

### 🚀 Für den schnellen Start
- **[SCHNELLSTART_DEPLOYMENT.md](SCHNELLSTART_DEPLOYMENT.md)** ⭐ **START HIER!**
  - Schritt-für-Schritt-Anleitung in 3 Hauptschritten
  - Perfekt für Einsteiger
  - Zeitaufwand: 30-45 Minuten
  - Enthält alle wichtigen Befehle

### 📖 Für detaillierte Informationen
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**
  - Vollständige Dokumentation (alle Details)
  - 10 Kapitel mit umfassenden Erklärungen
  - Troubleshooting-Sektion
  - Best Practices für Produktion
  - Sicherheits-Checkliste
  - Performance-Tipps

### 🛠 Deployment-Verzeichnis
- **[deployment/README.md](deployment/README.md)**
  - Übersicht über alle Scripts und Konfigurationsdateien
  - Schnellreferenz für Befehle
  - Beschreibung der einzelnen Komponenten

---

## 🗂 Deployment-Dateien im Überblick

### 📜 Automatisierungs-Scripts (Bash)

| Script | Beschreibung | Ausführen als |
|--------|-------------|---------------|
| `deployment/install_server.sh` | Installiert Systemabhängigkeiten auf dem Server | root |
| `deployment/deploy_app.sh` | Deployed die Anwendung (venv, deps, config) | bis-Benutzer |
| `deployment/update_app.sh` | Aktualisiert die App (mit Backup) | root |
| `deployment/backup_bis.sh` | Erstellt Backup von DB und Uploads | root |
| `deployment/healthcheck.sh` | Prüft ob App läuft | root |

### ⚙️ Konfigurationsdateien

| Datei | Zweck |
|-------|-------|
| `deployment/bis.service` | Systemd Service-Datei für Gunicorn |
| `deployment/nginx_bis.conf` | Nginx-Konfiguration (HTTP) |
| `deployment/nginx_bis_ssl.conf` | Nginx-Konfiguration mit SSL/TLS |

### 💻 Windows-Scripts (PowerShell)

| Script | Beschreibung |
|--------|-------------|
| `deployment/upload_to_server.ps1` | Lädt Code von Windows auf Server hoch |

---

## 🎯 Deployment-Strategien

### Strategie 1: Automatisiert (Empfohlen für Einsteiger) ⭐

1. **Container erstellen** in Proxmox
2. **Auf dem Server** ausführen:
   ```bash
   ./deployment/install_server.sh  # als root
   ```
3. **Von Windows** hochladen:
   ```powershell
   .\deployment\upload_to_server.ps1
   ```
4. **Auf dem Server** deployen:
   ```bash
   ./deployment/deploy_app.sh  # als bis-Benutzer
   ```

**Vorteile:**
- Schnell und einfach
- Weniger Fehleranfälligkeit
- Automatische Konfiguration

**Zeitaufwand:** ~30 Minuten

---

### Strategie 2: Manuell (Für vollständige Kontrolle)

Folgen Sie dem **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** Schritt für Schritt.

**Vorteile:**
- Vollständiges Verständnis aller Schritte
- Anpassbar an spezielle Anforderungen
- Lerneffekt

**Zeitaufwand:** ~60 Minuten

---

### Strategie 3: Hybrid (Automatisiert + manuelle Anpassungen)

1. Nutzen Sie die Scripts aus Strategie 1
2. Passen Sie anschließend individuelle Einstellungen an:
   - Domain in Nginx-Config
   - SSL-Zertifikat einrichten
   - Backup-Zeitpläne
   - Performance-Tuning

**Vorteile:**
- Balance zwischen Geschwindigkeit und Kontrolle
- Flexibel

**Zeitaufwand:** ~40 Minuten

---

## 🔄 Typische Workflows

### Erstmaliges Deployment

```
┌─────────────────────────┐
│ 1. LXC Container        │
│    in Proxmox erstellen │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ 2. Server einrichten    │
│    (install_server.sh)  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ 3. Code hochladen       │
│    (SCP / upload.ps1)   │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ 4. App deployen         │
│    (deploy_app.sh)      │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ 5. Services einrichten  │
│    (systemd + nginx)    │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ 6. SSL konfigurieren    │
│    (optional: certbot)  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ ✅ App läuft!           │
└─────────────────────────┘
```

### App-Update durchführen

```
┌─────────────────────────┐
│ 1. Code hochladen       │
│    (upload_to_server)   │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ 2. Update ausführen     │
│    (update_app.sh)      │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│ ✅ Update abgeschlossen │
│    (mit Auto-Backup)    │
└─────────────────────────┘
```

---

## 📋 Checkliste: Was brauche ich?

### Vor dem Start

- [ ] **Proxmox-Zugang** (Web-UI oder SSH)
- [ ] **Ubuntu 24.04 / Debian 12 Template** in Proxmox
- [ ] **SSH-Client** auf Windows (PowerShell, PuTTY, Terminal)
- [ ] **SCP/SFTP-Tool** (in PowerShell enthalten, oder WinSCP)
- [ ] **Server-IP-Adresse** (statisch oder via DHCP)
- [ ] Optional: **Domain-Name** (für SSL/HTTPS)

### Während der Installation

- [ ] Root-Passwort für Container
- [ ] Passwort für bis-Benutzer
- [ ] E-Mail für SSL-Zertifikat (optional)

### Nach der Installation

- [ ] Firewall ist aktiv
- [ ] Services laufen (bis.service, nginx)
- [ ] Backups sind eingerichtet
- [ ] App ist erreichbar im Browser
- [ ] SSL/TLS ist konfiguriert (Produktion)

---

## 🚦 Welchen Guide soll ich verwenden?

```
Sind Sie Anfänger oder wollen schnell starten?
│
├─ JA → Start mit SCHNELLSTART_DEPLOYMENT.md
│
└─ NEIN → Haben Sie spezielle Anforderungen?
    │
    ├─ JA → Nutzen Sie DEPLOYMENT_GUIDE.md (vollständig)
    │
    └─ NEIN → Nutzen Sie die automatischen Scripts
              (install_server.sh + deploy_app.sh)
```

---

## 📊 Vergleich der Deployment-Methoden

| Kriterium | Automatisch (Scripts) | Manuell (Guide) |
|-----------|----------------------|-----------------|
| Zeitaufwand | ⭐⭐⭐ ~30 Min | ⭐⭐ ~60 Min |
| Schwierigkeit | ⭐ Einfach | ⭐⭐⭐ Mittel |
| Lerneffekt | ⭐⭐ Gering | ⭐⭐⭐ Hoch |
| Anpassbarkeit | ⭐⭐ Eingeschränkt | ⭐⭐⭐ Voll |
| Fehlerrisiko | ⭐ Niedrig | ⭐⭐ Mittel |

---

## 🔧 Server-Konfiguration im Überblick

### Hardware-Empfehlungen (LXC)

| Komponente | Minimum | Empfohlen | Produktiv |
|------------|---------|-----------|-----------|
| CPU | 1 Core | 2 Cores | 4 Cores |
| RAM | 1 GB | 2 GB | 4 GB |
| Disk | 10 GB | 20 GB | 50 GB |
| Swap | 256 MB | 512 MB | 1 GB |

### Software-Stack

```
┌─────────────────────────────┐
│   Nginx (Reverse Proxy)     │ ← Port 80/443 (extern)
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│   Gunicorn (WSGI Server)    │ ← Port 8000 (intern)
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│   Flask Application         │
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│   SQLite Database           │
└─────────────────────────────┘
```

---

## 📞 Support & Troubleshooting

### Bei Problemen:

1. **Prüfen Sie die Logs:**
   ```bash
   journalctl -u bis.service -f
   tail -f /var/log/bis/error.log
   ```

2. **Führen Sie einen Health-Check aus:**
   ```bash
   /opt/bis/deployment/healthcheck.sh
   ```

3. **Konsultieren Sie die Troubleshooting-Sektion:**
   - In DEPLOYMENT_GUIDE.md (Kapitel "Troubleshooting")
   - In SCHNELLSTART_DEPLOYMENT.md (Abschnitt "Problemlösung")

### Häufige Probleme & Lösungen

| Problem | Lösung |
|---------|--------|
| Service startet nicht | `journalctl -u bis.service -n 50` |
| 502 Bad Gateway | Prüfen ob Gunicorn läuft, Port 8000 |
| Datei-Upload funktioniert nicht | Berechtigungen in `/var/www/bis-data` prüfen |
| Datenbank-Fehler | Prüfen ob DB existiert und Rechte korrekt sind |

---

## 🎓 Erweiterte Themen

Nach erfolgreichem Deployment können Sie sich mit diesen Themen befassen:

- **Monitoring:** Integration von Prometheus/Grafana
- **High Availability:** Mehrere Container mit Load Balancing
- **Continuous Deployment:** GitLab CI/CD oder GitHub Actions
- **Datenbank-Migration:** Zu PostgreSQL für bessere Performance
- **Caching:** Redis für Session-Management
- **CDN:** Für statische Dateien

Weitere Informationen hierzu finden Sie in separaten Guides (können bei Bedarf erstellt werden).

---

## 📝 Zusammenfassung

### Für schnellen Produktiv-Start:

1. Lesen Sie **SCHNELLSTART_DEPLOYMENT.md**
2. Folgen Sie den 3 Hauptschritten
3. Ihre App läuft in ~30 Minuten!

### Für tiefes Verständnis:

1. Lesen Sie **DEPLOYMENT_GUIDE.md**
2. Verstehen Sie jeden Schritt
3. Passen Sie an Ihre Bedürfnisse an

### Empfohlener Workflow:

1. **Testumgebung:** Nutzen Sie die Scripts für schnelles Setup
2. **Produktivumgebung:** Folgen Sie dem vollständigen Guide
3. **Wartung:** Nutzen Sie die Maintenance-Scripts (backup, update, healthcheck)

---

**Viel Erfolg mit Ihrem BIS-Deployment! 🚀**

Bei Fragen oder Problemen konsultieren Sie die entsprechenden Guides oder prüfen Sie die Logs.

