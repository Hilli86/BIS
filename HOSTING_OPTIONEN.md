# 🚀 Hosting-Optionen für BIS

Empfehlungen für günstiges Hosting der BIS-Anwendung für Testzwecke und den Start mit unter 20 Benutzern.

## 📋 Übersicht

Die BIS-Anwendung ist eine Flask-basierte Web-App mit:
- SQLite-Datenbank
- File-Upload-Funktionalität
- Nginx als Reverse Proxy (optional)
- Gunicorn als WSGI-Server

---

## 💰 Empfohlene Hosting-Optionen

### 1. 🥇 Railway.app (Empfohlen für den Start)

**Kosten:** ~5-10 €/Monat (oder Free Tier mit Limits)

**Vorteile:**
- ✅ Einfaches Deployment (Git-basiert)
- ✅ Automatisches SSL
- ✅ Gute Dokumentation
- ✅ PostgreSQL optional verfügbar (SQLite funktioniert auch)
- ✅ Keine Server-Verwaltung nötig

**Nachteile:**
- ⚠️ Persistente Dateien benötigen Volumes (kostenpflichtig)
- ⚠️ Bei Free Tier: Limits bei Traffic/CPU

**Setup:**
1. Account bei [Railway.app](https://railway.app) erstellen
2. GitHub-Repository verbinden
3. Environment-Variablen setzen
4. Deploy starten

---

### 2. 🥈 Render.com

**Kosten:** Free Tier verfügbar, ab ~7 €/Monat für persistente Services

**Vorteile:**
- ✅ Free Tier für Tests verfügbar
- ✅ Automatisches SSL
- ✅ Einfaches Setup
- ✅ Gute Dokumentation

**Nachteile:**
- ⚠️ Free Tier schläft nach Inaktivität ein
- ⚠️ Persistenter Storage kostet extra

**Setup:**
1. Account bei [Render.com](https://render.com) erstellen
2. "New Web Service" erstellen
3. GitHub-Repository verbinden
4. Build-Command: `pip install -r requirements.txt`
5. Start-Command: `gunicorn app:app`

---

### 3. 🥉 Hetzner Cloud (VPS) - Beste Preis-Leistung

**Kosten:** ~4-5 €/Monat (CX11: 1 vCPU, 2 GB RAM, 20 GB SSD)

**Vorteile:**
- ✅ Vollständige Kontrolle über den Server
- ✅ Dein aktueller Deployment-Guide funktioniert direkt
- ✅ Gute Performance für den Preis
- ✅ Keine Limits
- ✅ SQLite und File-Uploads funktionieren ohne Anpassungen

**Nachteile:**
- ⚠️ Eigenes Server-Management nötig
- ⚠️ SSL muss selbst eingerichtet werden (Let's Encrypt)

**Setup:**
- Siehe [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - funktioniert direkt!

**Server-Konfiguration:**
- **Empfohlene Instanz:** CX11 (1 vCPU, 2 GB RAM, 20 GB SSD)
- **Betriebssystem:** Ubuntu 24.04 oder Debian 12
- **Kosten:** ~4,15 €/Monat

---

### 4. Contabo VPS

**Kosten:** ~3-4 €/Monat (VPS S: 2 vCPU, 4 GB RAM, 50 GB SSD)

**Vorteile:**
- ✅ Sehr günstig
- ✅ Mehr Ressourcen als Hetzner für ähnlichen Preis
- ✅ Gute Performance
- ✅ Keine Limits

**Nachteile:**
- ⚠️ Eigenes Server-Management nötig
- ⚠️ Support auf Deutsch, aber weniger bekannt

**Setup:**
- Siehe [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

### 5. Fly.io

**Kosten:** Free Tier + Pay-as-you-go (~2-5 €/Monat)

**Vorteile:**
- ✅ Generous Free Tier
- ✅ Globale Edge-Deployment
- ✅ Einfaches CLI-Tool
- ✅ Automatisches SSL

**Nachteile:**
- ⚠️ Lernkurve für CLI-Tool
- ⚠️ SQLite kann bei Multi-Instance problematisch sein

**Setup:**
1. `flyctl` installieren
2. `flyctl launch` im Projekt-Verzeichnis
3. Konfiguration anpassen

---

### 6. DigitalOcean App Platform

**Kosten:** ~5 €/Monat (Basic Plan)

**Vorteile:**
- ✅ Managed Platform
- ✅ Automatisches SSL
- ✅ Gute Dokumentation
- ✅ Einfaches Deployment

**Nachteile:**
- ⚠️ Etwas teurer als VPS-Optionen
- ⚠️ Persistenter Storage kostet extra

---

## 🎯 Empfehlung für deinen Use Case

### Für Testzwecke (< 20 User):

#### Option A: Schnellstart ohne Server-Verwaltung
**Render.com Free Tier** oder **Railway.app**
- ✅ Schnell eingerichtet
- ✅ Keine Server-Verwaltung nötig
- ✅ Perfekt zum Testen

#### Option B: Langfristig & Produktiv
**Hetzner Cloud CX11** (~4 €/Monat)
- ✅ Dein Deployment-Guide funktioniert direkt
- ✅ Vollständige Kontrolle
- ✅ Gute Performance für den Preis
- ✅ SQLite und File-Uploads funktionieren ohne Anpassungen

---

## ⚠️ Wichtige Hinweise für deine App

### SQLite-Datenbank
- **Bei Cloud-Plattformen** (Railway, Render): SQLite kann bei mehreren Instanzen problematisch sein
- **Für < 20 User:** Meist unkritisch, aber PostgreSQL wäre robuster
- **Bei VPS** (Hetzner/Contabo): SQLite funktioniert perfekt für deinen Use Case

### File-Uploads
- **Bei Platform-as-a-Service:** Benötigt persistenten Storage (Volumes) - kostet extra
- **Bei VPS:** Dein aktuelles Setup funktioniert direkt ohne Anpassungen

### SSL/TLS
- **Cloud-Plattformen:** Automatisch verfügbar
- **VPS:** Siehe [SSL_SELFSIGNED_SETUP.md](SSL_SELFSIGNED_SETUP.md) oder Let's Encrypt Setup im [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 📊 Vergleichstabelle

| Anbieter | Kosten/Monat | Setup-Aufwand | Server-Management | Empfohlen für |
|----------|--------------|---------------|-------------------|---------------|
| **Railway.app** | 5-10 € | ⭐⭐ Einfach | Nein | Schnellstart |
| **Render.com** | 0-7 € | ⭐⭐ Einfach | Nein | Tests |
| **Hetzner Cloud** | ~4 € | ⭐⭐⭐ Mittel | Ja | Produktiv |
| **Contabo VPS** | ~3-4 € | ⭐⭐⭐ Mittel | Ja | Budget |
| **Fly.io** | 2-5 € | ⭐⭐⭐ Mittel | Nein | Edge-Deployment |
| **DigitalOcean** | ~5 € | ⭐⭐ Einfach | Nein | Managed |

---

## 🔗 Weitere Ressourcen

- **Deployment-Guide:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Vollständige Anleitung für VPS
- **Schnellstart:** [SCHNELLSTART_DEPLOYMENT.md](SCHNELLSTART_DEPLOYMENT.md) - Setup in 30 Min
- **SSL-Setup:** [SSL_SELFSIGNED_SETUP.md](SSL_SELFSIGNED_SETUP.md) - SSL-Zertifikate einrichten

---

## 💡 Tipps

1. **Für den Start:** Beginne mit Render.com Free Tier oder Railway.app zum Testen
2. **Für Produktion:** Wechsle zu Hetzner Cloud für bessere Performance und Kontrolle
3. **Backups:** Stelle sicher, dass regelmäßige Backups eingerichtet sind (siehe [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md))
4. **Monitoring:** Überwache Ressourcen-Nutzung, besonders bei Free Tiers

---

*Stand: 2025 - Preise können variieren, bitte auf den Anbieter-Websites prüfen*

