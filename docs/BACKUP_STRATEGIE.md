# BIS � Backup-Strategie und Runbook

Dieses Dokument beschreibt die automatische Datensicherung des BIS-Systems �ber
den Docker-Service `Backup-Service`, die Aufbewahrungsregeln, Passwort-Hinweise
und das **Restore-Runbook** f�r den Ernstfall.

---

## 1. �berblick

Die Strategie folgt der klassischen **3-2-1-Regel**:

- **3 Kopien** der Daten (Produktion + 2 Backups)
- **2 unterschiedliche Speicherorte** (lokale Platte + OneDrive-Cloud)
- **1 Kopie r�umlich getrennt** (OneDrive synchronisiert in die Cloud)

```mermaid
flowchart LR
    subgraph host [Host m-0015]
        AppVol["C:\\BIS-Daten<br/>(DB + Uploads)"]
        BackupVol["C:\\BIS-Backups<br/>(plain)"]
        OneDrive["C:\\Users\\hilli\\OneDrive\\Apps\\BIS\\Backups<br/>(7z AES-256)"]
    end

    subgraph compose [docker compose]
        App[Application-Service]
        Proxy[Proxy-Service]
        Backup[Backup-Service]
    end

    App -- "read/write" --> AppVol
    Backup -- "read" --> AppVol
    Backup -- "write plain" --> BackupVol
    Backup -- "write encrypted" --> OneDrive
    Backup -- "INSERT Benachrichtigung (Erfolg/Fehler)" --> AppVol
```

---

## 2. Was wird gesichert?

| Artefakt | Quelle im Container | Im Backup |
|---|---|---|
| SQLite-Datenbank | `/data/database_main.db` | `database_main.db` (via `sqlite3 .backup`, konsistent) |
| Postgres-Datenbank (optional) | via `DATABASE_URL` (`postgresql+psycopg://...`) | `database_main.dump` (via `pg_dump --format=custom`) |
| Upload-Dateien | `/data/Daten/` | `uploads.tar.gz` |
| Backup-Metadaten | automatisch erzeugt | `backup_info.txt`, `checksums.sha256` |

Welcher DB-Pfad verwendet wird, bestimmt die Umgebungsvariable `DATABASE_URL`
am Backup-Container:

- **nicht gesetzt** (oder SQLite-Pfad) -> SQLite-Backup ueber `sqlite3 .backup`
- **`postgresql+psycopg://user:pw@host/db`** -> Postgres-Backup ueber `pg_dump`

Das Backup-Image enthaelt sowohl `sqlite3` als auch `postgresql-client`.

**Bewusst NICHT im Backup** � diese Artefakte sind rekonstruierbar:

- **Code** (liegt im Git-Repo `Hilli86/BIS`)
- **`.env`** (liegt im Passwort-Manager / Betriebsdoku � siehe Abschnitt 5)
- **Nginx-TLS-Zertifikat** (wird beim Docker-Build regeneriert, siehe
  [`docker/nginx.Dockerfile`](../docker/nginx.Dockerfile))

---

## 3. Wo liegen die Backups?

| Kopie | Pfad | Verschl�sselung | Zweck |
|---|---|---|---|
| Plain | `C:\BIS-Backups\bis_YYYYMMDD_HHMMSS\` | nein | Schneller lokaler Restore |
| Encrypted | `C:\Users\hilli\OneDrive\Apps\BIS\Backups\bis_YYYYMMDD_HHMMSS.7z` | 7z AES-256 + Header-Encryption | Offsite via OneDrive-Sync |

Das lokale Plain-Backup enth�lt die unver�nderten Einzeldateien. Das OneDrive-
Archiv ist ein 7z-Paket mit **verschl�sselten Dateinamen** (`-mhe=on`),
Passwort aus `.env` (siehe Abschnitt 5).

---

## 4. Zeitplan & Retention (GFS)

**Zeitplan:** t�glich um **02:00** (Container-Zeitzone `Europe/Berlin`),
Cron-Job in [`docker/backup.Dockerfile`](../docker/backup.Dockerfile).

**Retention (Gro�vater-Vater-Sohn):**

| Ebene | Regel | Aufbewahrung (Default) |
|---|---|---|
| T�glich | jedes Backup | 14 Tage |
| W�chentlich | Backups vom Sonntag | 8 Wochen |
| Monatlich | Backups vom 1. eines Monats | 12 Monate |

Anpassbar �ber Umgebungsvariablen in
[`docker-compose.yml`](../docker-compose.yml):
`RETENTION_DAILY`, `RETENTION_WEEKLY`, `RETENTION_MONTHLY`.

---

## 5. Passwort-Ort (`BACKUP_ENCRYPTION_PASSWORD`)

Das 7z-Passwort wird ausschlie�lich �ber die `.env`-Datei ins Compose injiziert
und an den `Backup-Service`-Container als `BACKUP_ENCRYPTION_PASSWORD` weiter-
gereicht. **Es wird nirgendwo im Git versioniert.**

| Ort | Inhalt | Zugriff |
|---|---|---|
| `.env` (Host, Projektordner) | Klartext, Leserechte nur Admin | Admin-Konto `m-0015` |
| Passwort-Manager (Master) | Klartext, Pflicht-Sicherung | _hier eintragen_: z. B. KeePass-Eintrag `BIS/Backup 7z` |
| Optional: versiegelter Umschlag (Tresor) | Papier-Fallback | _hier eintragen_ |

> **Wichtig:** Geht das Passwort verloren, sind s�mtliche Offsite-Kopien
> unbrauchbar. Der lokale Plain-Ordner `C:\BIS-Backups\` ist dann die einzige
> Restore-Quelle.

**Neues Passwort erzeugen:**

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Nach einer Passwort-�nderung m�ssen alle Container neu gestartet werden
(`docker compose up -d`). Bestehende verschl�sselte Archive behalten weiterhin
das **alte** Passwort � bitte dokumentieren, ab welchem Datum welches Passwort
gilt.

---

## 6. Ansprechpartner

| Rolle | Name | Kontakt | Vertretung |
|---|---|---|---|
| BIS-Admin (Prim�r) | _einf�gen_ | _einf�gen_ | _einf�gen_ |
| BIS-Admin (Vertretung) | _einf�gen_ | _einf�gen_ | _einf�gen_ |
| Infrastruktur / OneDrive | _einf�gen_ | _einf�gen_ | _einf�gen_ |
| Datenschutz / DSGVO | _einf�gen_ | _einf�gen_ | _einf�gen_ |

Im Notfall zuerst den Prim�r-Admin informieren; dieser entscheidet �ber den
Restore-Zeitpunkt (App-Downtime!).

---

## 7. Restore-Runbook

> Alle folgenden Befehle werden auf dem Host `m-0015` in einer **PowerShell
> als Administrator** im Projekt-Ordner `C:\Projekte\Github\BIS` ausgef�hrt.

### 7.1 App stoppen

```powershell
docker compose stop Application-Service
```

### 7.2a Restore aus lokalem Plain-Backup (SQLite)

```powershell
$ts = "20260418_020000"   # gewuenschten Zeitstempel eintragen
$src = "C:\BIS-Backups\bis_$ts"

Copy-Item "$src\database_main.db" "C:\BIS-Daten\database_main.db" -Force

# Uploads zuruecksichern (vorher ggf. alten Ordner sichern)
Rename-Item "C:\BIS-Daten\Daten" "C:\BIS-Daten\Daten.alt-$ts" -ErrorAction SilentlyContinue
tar -xzf "$src\uploads.tar.gz" -C "C:\BIS-Daten"
```

### 7.2a-PG Restore aus lokalem Plain-Backup (Postgres)

```powershell
$ts = "20260418_020000"
$src = "C:\BIS-Backups\bis_$ts"
$pgurl = "postgresql://bis_user:GeheimesPasswort@localhost:5432/bis"

# Leere DB vorher anlegen (oder bestehende Objekte per --clean ersetzen)
pg_restore --clean --if-exists --no-owner --no-privileges `
    --dbname=$pgurl "$src\database_main.dump"

# Uploads wie bei SQLite zuruecksichern
Rename-Item "C:\BIS-Daten\Daten" "C:\BIS-Daten\Daten.alt-$ts" -ErrorAction SilentlyContinue
tar -xzf "$src\uploads.tar.gz" -C "C:\BIS-Daten"
```

### 7.2b Restore aus OneDrive-Backup (verschl�sselt)

```powershell
$ts = "20260418_020000"
$pw = "<BACKUP_ENCRYPTION_PASSWORD>"   # aus Passwort-Manager
$enc = "C:\Users\hilli\OneDrive\Apps\BIS\Backups\bis_$ts.7z"
$tmp = "C:\BIS-Restore\bis_$ts"

New-Item -ItemType Directory -Path $tmp -Force | Out-Null
7z x "$enc" -o"$tmp" -p"$pw"

# Danach wie 7.2a weiter, aber mit $src = "$tmp\bis_$ts"
```

### 7.3 Integrit�ts-Check vor dem App-Start

SQLite:

```powershell
docker run --rm -v C:\BIS-Daten:/data bis/backup-service:latest `
  sqlite3 /data/database_main.db "PRAGMA integrity_check;"
```

Erwartete Ausgabe: `ok` � bei anderem Ergebnis **nicht** starten, n�chsteres
Backup probieren.

Postgres (nach `pg_restore`):

```powershell
psql "$pgurl" -c "SELECT 'Mitarbeiter' AS tabelle, COUNT(*) FROM \"Mitarbeiter\";"
psql "$pgurl" -c "SELECT 'SchichtbuchThema' AS tabelle, COUNT(*) FROM \"SchichtbuchThema\";"
```

Die Zeilenzahlen sollten zum letzten erfolgreichen Lauf passen (Vergleich mit
`backup_info.txt` oder der Produktion vor dem Restore).

### 7.4 App starten und pr�fen

```powershell
docker compose start Application-Service

# Health-Check
docker logs --tail 50 bis-application-service
Start-Process "https://localhost/"
```

Nach erfolgreichem Login sollten die Admins eine Benachrichtigung in der Glocke
sehen (n�chster planm��iger Backup-Lauf kommt um 02:00).

### 7.5 Aufr�umen

```powershell
# Alte Daten-Sicherung entfernen, wenn Restore ok ist:
Remove-Item "C:\BIS-Daten\Daten.alt-$ts" -Recurse -Force
# Entpackten Temp-Ordner entfernen (nur bei 7.2b):
Remove-Item "C:\BIS-Restore\bis_$ts" -Recurse -Force
```

---

## 8. Monitoring und Verifikation

### In-App-Benachrichtigungen

Der `Backup-Service` schreibt nach jedem Lauf in die Tabelle `Benachrichtigung`:

| Lauf | Modul | Aktion | Typ | Titel |
|---|---|---|---|---|
| Erfolg | `backup` | `backup_success` | `info` | `Backup erfolgreich` |
| Fehler | `backup` | `backup_failure` | `system` | `Backup fehlgeschlagen` |

Empf�nger sind alle aktiven Mitarbeiter mit Berechtigung `admin`.

- **Erfolg**: 1� pro Nacht (per `NOTIFY_ON_SUCCESS=false` deaktivierbar).
- **Fehler**: Rate-Limit 6 h pro Empf�nger, um wiederholte Cron-Fehler nicht zu
  spammen. Zusatzdaten enthalten Phase (`sqlite_backup`, `integrity_check`,
  `tar`, `encrypt`, `retention`) und die letzten Logzeilen.

### Container-Logs

```powershell
docker logs bis-backup-service          # tail der laufenden Logs
docker exec bis-backup-service cat /var/log/backup.log
```

### Lokale Backup-Info

Jeder Plain-Ordner enth�lt `backup_info.txt` und `checksums.sha256`. Die
SHA-256 sollte beim Restore gepr�ft werden:

```powershell
Set-Location "C:\BIS-Backups\bis_$ts"
Get-Content checksums.sha256
# Vergleichen mit:
Get-FileHash database_main.db -Algorithm SHA256
```

### Dead-Man's-Switch

Wenn **l�nger als 26 h** keine neue Erfolgs-Benachrichtigung eintrifft, muss
die Situation manuell gepr�ft werden (Container abgest�rzt, OneDrive voll,
Passwort entfernt, ...).

### Pflicht-Restore-Test

**Mindestens einmal pro Quartal** muss ein vollst�ndiger Restore auf einem
Testsystem durchgef�hrt werden. Ergebnis im �nderungsprotokoll (Abschnitt 10)
vermerken.

---

## 9. Bekannte Einschr�nkungen

- **WAL-Dateien:** SQLite nutzt ggf. ein Write-Ahead-Log. Ein einfaches `copy`
  der `.db` ist deshalb verboten � der Service verwendet stattdessen
  `sqlite3 .backup`, das WAL-safe ist.
- **OneDrive-Sync-Latenz:** Backups sind erst nach erfolgreicher Synchroni-
  sierung offsite. Bei gro�er Datenbank ggf. Sync-Status pr�fen.
- **Passwortverlust = Datenverlust** bei verschl�sselter Kopie. Plain-Ordner
  ist dann das einzige Fallback.
- **`/data` rw n�tig:** Der Backup-Container muss in `Benachrichtigung`
  schreiben k�nnen. Das eigentliche Backup ist davon unber�hrt.
- **Kein Point-in-Time-Recovery:** Es gibt keine WAL-Archivierung � der
  Verlust zwischen zwei Backups entspricht bis zu 24 h.

---

## 10. �nderungsprotokoll

| Datum | Autor | �nderung |
|---|---|---|
| 2026-04-18 | Initial | Backup-Service eingef�hrt, Runbook erstellt |
| 2026-04-20 | Phase 5 | pg_dump-Pfad f�r Postgres erg�nzt (siehe `docs/POSTGRES_DEPLOYMENT.md`) |
