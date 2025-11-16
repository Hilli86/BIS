# Proxmox Installation & Konfiguration mit kostenlosen Repositories

Diese Anleitung erklärt, wie man Proxmox VE richtig einrichtet, auf kostenlose Repositories umstellt und die "invalid subscription" Warnung entfernt.

## 1. Proxmox Installation

### Schritt 1: ISO-Datei herunterladen
1. Besuchen Sie die offizielle Proxmox-Download-Seite: https://www.proxmox.com/en/downloads
2. Laden Sie die neueste ISO-Datei für Proxmox VE herunter

### Schritt 2: Installation starten
1. Erstellen Sie einen bootfähigen USB-Stick mit der ISO-Datei
2. Booten Sie den Server vom USB-Stick
3. Folgen Sie dem Installationsassistenten
4. Notieren Sie sich die IP-Adresse, die während der Installation zugewiesen wird

### Schritt 3: Web-Interface aufrufen
1. Öffnen Sie einen Browser und navigieren Sie zu: `https://Ihre-IP:8006`
2. Loggen Sie sich mit den Root-Credentials ein, die Sie während der Installation festgelegt haben

## 2. Umstellung auf kostenlose Repositories (pve-no-subscription)

Proxmox wird standardmäßig mit Enterprise-Repositories installiert, die eine gültige Subscription erfordern. Für den privaten oder kleinen Geschäftsgebrauch können Sie kostenlos auf die `pve-no-subscription` Repositories umstellen.

### Schritt 1: Aktuelle Repository-Dateien sichern

```bash
# Enterprise-Repository-Datei sichern (falls Sie später zurückwechseln möchten)
cp /etc/apt/sources.list.d/pve-enterprise.list /etc/apt/sources.list.d/pve-enterprise.list.bak
```

### Schritt 2: Enterprise-Repository deaktivieren/entfernen

**Option A: Repository-Datei entfernen (empfohlen)**
```bash
rm /etc/apt/sources.list.d/pve-enterprise.list
```

**Option B: Repository-Datei auskommentieren**
```bash
# Enterprise-Repository auskommentieren
sed -i 's|deb https://enterprise.proxmox.com/debian/pve|#deb https://enterprise.proxmox.com/debian/pve|' /etc/apt/sources.list.d/pve-enterprise.list
```

### Schritt 3: Kostenloses Repository aktivieren

```bash
# pve-no-subscription Repository hinzufügen (für Proxmox VE)
echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" > /etc/apt/sources.list.d/pve-no-subscription.list

# Ceph Repository (falls Sie Ceph verwenden)
echo "deb http://download.proxmox.com/debian/ceph-quincy bookworm no-subscription" > /etc/apt/sources.list.d/ceph.list
```

**Hinweis:** Ersetzen Sie `bookworm` durch die entsprechende Debian-Version, falls Sie eine andere verwenden:
- Bullseye (Debian 11)
- Bookworm (Debian 12)
- Trixie (Debian 13)

### Schritt 4: Repository-Liste aktualisieren

```bash
apt update
apt upgrade -y
```

Nach diesem Schritt sollten Sie keine Fehlermeldungen mehr bezüglich ungültiger Subscriptions beim Update sehen.

## 3. Subscription-Warnung in der Web-Oberfläche entfernen

Nach der Umstellung auf kostenlose Repositories erscheint weiterhin eine Warnung in der Web-Oberfläche über eine ungültige Subscription. Diese kann durch Anpassung einer JavaScript-Datei entfernt werden.

### Methode 1: JavaScript-Datei patchen (empfohlen)

```bash
# Backup der Originaldatei erstellen
cp /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js.bak

# Subscription-Prüfung deaktivieren
sed -i.bak "s/data.status !== 'Active'/false/g" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
```

**Alternative: Manuelle Bearbeitung**
```bash
# Datei öffnen
nano /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js

# Suchen Sie nach:
if (data.status !== 'Active') {

# Ersetzen Sie durch:
if (false) {
```

### Methode 2: Browser-Cache leeren

Nach der Änderung müssen Sie den Browser-Cache leeren:
- **Chrome/Edge:** Strg + Shift + R (Hard Refresh)
- **Firefox:** Strg + F5
- Oder: Browser-Cache komplett leeren

### Wichtiger Hinweis

**Nach jedem größeren Proxmox-Update muss diese Änderung erneut vorgenommen werden**, da die JavaScript-Datei durch Updates überschrieben wird.

## 4. Subscription-Hinweis im Terminal entfernen (optional)

Wenn Sie auch die Warnung beim SSH-Login entfernen möchten:

```bash
# Nachricht beim Login entfernen
chmod -x /etc/update-motd.d/85-hw-gpu
```

## 5. Repository-Status überprüfen

### Aktive Repositories anzeigen
```bash
cat /etc/apt/sources.list.d/*.list
```

Die Ausgabe sollte etwa so aussehen:
```
deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription
```

**Sollte NICHT enthalten sein:**
```
deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise
```

### Proxmox-Version und Pakete prüfen
```bash
# Installierte Proxmox-Version anzeigen
pveversion -v

# Verfügbare Updates prüfen
apt update && apt list --upgradable
```

## 6. Automatische Updates (optional)

Für Produktionsumgebungen können Sie automatische Sicherheits-Updates einrichten:

```bash
# Unattended-Upgrades installieren
apt install unattended-upgrades -y

# Konfigurieren
dpkg-reconfigure -plow unattended-upgrades
```

## 7. Wichtige Dateien im Überblick

| Datei | Beschreibung |
|-------|--------------|
| `/etc/apt/sources.list.d/pve-enterprise.list` | Enterprise-Repository (sollte entfernt/auskommentiert sein) |
| `/etc/apt/sources.list.d/pve-no-subscription.list` | Kostenloses Repository (sollte aktiv sein) |
| `/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js` | JavaScript für Subscription-Warnung |
| `/etc/update-motd.d/85-hw-gpu` | Login-Meldung |

## 8. Häufige Probleme und Lösungen

### Problem: "E: Repository '...' does not have a Release file"

**Lösung:** Überprüfen Sie die Debian-Version:
```bash
cat /etc/debian_version
```
Stellen Sie sicher, dass die Repository-URLs die korrekte Debian-Version verwenden.

### Problem: Warnung erscheint nach Update wieder

**Lösung:** Führen Sie Schritt 3 (JavaScript patchen) erneut aus. Dies ist nach größeren Proxmox-Updates normal.

### Problem: Updates schlagen fehl

**Lösung:** 
1. Überprüfen Sie die Repository-Dateien: `cat /etc/apt/sources.list.d/*.list`
2. Stellen Sie sicher, dass keine Enterprise-Repositories mehr aktiv sind
3. Führen Sie `apt update` erneut aus

## 9. Schnell-Referenz für häufige Befehle

```bash
# Repository-Status prüfen
apt update && apt list --upgradable

# Proxmox aktualisieren (nach Repository-Wechsel)
apt update && apt full-upgrade -y

# Warnung entfernen (nach jedem größeren Update)
sed -i.bak "s/data.status !== 'Active'/false/g" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js

# Services neu starten (falls nötig)
systemctl restart pveproxy

# Proxmox-Version anzeigen
pveversion -v

# Backup der JavaScript-Datei erstellen
cp /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js.bak
```

## 10. Wichtige Hinweise

### Unterschied zwischen Enterprise und No-Subscription

- **Enterprise Repository:** Erfordert eine kostenpflichtige Subscription, bietet früheren Zugang zu Updates und Support
- **No-Subscription Repository:** Kostenlos, Updates werden etwas später verfügbar gemacht

### Für Produktionsumgebungen

Für kritische Produktionsumgebungen sollten Sie eine Enterprise-Subscription in Betracht ziehen:
- Zugang zu früheren Updates
- Professioneller Support
- Enterprise-Funktionen

### Sicherheit

Die kostenlosen Repositories sind sicher und werden von der Proxmox-Community aktiv gepflegt. Updates erscheinen nur wenige Tage später als in den Enterprise-Repositories.

## 11. Zurückwechseln auf Enterprise (falls nötig)

Falls Sie später doch eine Subscription erwerben:

```bash
# Enterprise-Repository wiederherstellen
cp /etc/apt/sources.list.d/pve-enterprise.list.bak /etc/apt/sources.list.d/pve-enterprise.list

# No-Subscription Repository entfernen
rm /etc/apt/sources.list.d/pve-no-subscription.list

# Repositories aktualisieren
apt update
```

## Zusammenfassung

1. ✅ Enterprise-Repository entfernen/auskommentieren
2. ✅ No-Subscription Repository hinzufügen
3. ✅ `apt update && apt upgrade` ausführen
4. ✅ JavaScript-Datei patchen, um Warnung zu entfernen
5. ✅ Browser-Cache leeren
6. ✅ Nach jedem Update Schritt 4 wiederholen

Nach diesen Schritten haben Sie Proxmox VE vollständig mit kostenlosen Repositories eingerichtet und die Subscription-Warnungen entfernt.
