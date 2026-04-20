# BIS - Postgres-Deployment

Dieses Dokument beschreibt, wie BIS gegen **PostgreSQL** (statt SQLite)
betrieben wird. Es ergaenzt den [Deployment Guide](DEPLOYMENT_GUIDE.md) und das
[Backup-Runbook](BACKUP_STRATEGIE.md).

BIS nutzt [SQLAlchemy Core](../utils/database.py) und [Alembic](../alembic/)
als dialektneutrale Schicht. Ein Wechsel von SQLite auf Postgres ist daher
**Konfigurationssache** – der Anwendungscode bleibt unveraendert.

## 1. Voraussetzungen

- PostgreSQL 14 oder neuer (getestet: 16).
- Datenbank-User mit Rechten `CREATE`, `CONNECT` auf der Ziel-DB.
- Python-Dependencies aktuell (`pip install -r requirements.txt`).
  Der Treiber `psycopg[binary]` ist in [`requirements.txt`](../requirements.txt)
  enthalten und bringt ein vorgebautes `libpq` mit – es muss kein
  `pg_config`/`postgresql-dev` auf dem Applikationshost installiert sein.

## 2. DATABASE_URL-Format

```bash
# SQLite (Default, rueckwaertskompatibel)
DATABASE_URL=database_main.db
# oder vollstaendig:
DATABASE_URL=sqlite:///C:/BIS-Daten/database_main.db

# PostgreSQL
DATABASE_URL=postgresql+psycopg://bis_user:GeheimesPasswort@db.example.com:5432/bis
```

Der Treiber-Prefix `+psycopg` ist wichtig; andernfalls versucht SQLAlchemy den
aelteren `psycopg2`-Treiber zu laden.

## 3. Neue (leere) Postgres-DB in Betrieb nehmen

### 3.1 Datenbank anlegen

Auf dem Postgres-Server:

```bash
sudo -u postgres createuser -P bis_user      # setzt Passwort interaktiv
sudo -u postgres createdb -O bis_user bis
# optional: GRANT CONNECT ON DATABASE bis TO bis_user;
```

### 3.2 Schema per Alembic einspielen

Auf dem Applikationshost (mit aktivem Python-Venv):

```powershell
$env:DATABASE_URL = "postgresql+psycopg://bis_user:GeheimesPasswort@db.example.com:5432/bis"
py -m alembic upgrade head
```

Ergebnis: Alle Tabellen und Indizes aus [`utils/db_schema.py`](../utils/db_schema.py)
existieren in der Postgres-DB, 1:1 zu einer frisch migrierten SQLite-DB.

### 3.3 BIS-Admin anlegen (Seed)

```powershell
py scripts/init_database.py
```

Das Skript fuehrt intern `alembic upgrade head` erneut idempotent aus (no-op,
wenn bereits auf HEAD) und erzeugt Abteilung `BIS-Admin` sowie den initialen
Admin-Benutzer. Das einmalige Passwort wird auf stdout ausgegeben.

### 3.4 App starten

```powershell
$env:DATABASE_URL = "postgresql+psycopg://bis_user:GeheimesPasswort@db.example.com:5432/bis"
py app.py
```

## 4. Umzug von SQLite nach Postgres (einmalig)

Zwei empfohlene Wege, beide ohne Downtime-Risiko fuer die Quell-DB:

### 4.1 Variante A: Python-Skript (`migrate_sqlite_to_postgres.py`)

Vorteil: Nutzt dasselbe Schema wie die App, keine Zusatz-Tools,
funktioniert unter Windows/Linux/macOS identisch.

```powershell
# 1) Leere Postgres-DB mit BIS-Schema anlegen
$env:DATABASE_URL = "postgresql+psycopg://bis_user:GeheimesPasswort@db.example.com:5432/bis"
py -m alembic upgrade head

# 2) Daten aus SQLite in die Postgres-DB kopieren
$env:SOURCE_URL = "sqlite:///C:/BIS-Daten/database_main.db"
$env:TARGET_URL = $env:DATABASE_URL
$env:TRUNCATE   = "1"   # Zieltabellen leeren, falls die DB nicht frisch ist
py scripts/migrate_sqlite_to_postgres.py
```

Das Skript:

- kopiert alle in [`utils/db_schema.py`](../utils/db_schema.py) deklarierten
  Tabellen in **topologischer Reihenfolge** der Foreign Keys,
- schreibt batchweise (Default 500 Zeilen, ueber `BATCH_SIZE` anpassbar),
- setzt anschliessend die Postgres-IDENTITY/SERIAL-Sequenzen auf `MAX(id)+1`,
- vergleicht am Ende die Zeilenzahlen in Quelle und Ziel.

Abweichende Zeilenzahlen sind ein **Fehler** und beenden das Skript mit
Exit-Code 4.

Hinweis zu Legacy-Daten: Bricht das Skript mit `IntegrityError` ab (z. B.
`NOT NULL constraint failed: ...`), enthaelt die Quelle Zeilen, die gegen das
in [`utils/db_schema.py`](../utils/db_schema.py) deklarierte Schema verstossen.
Quelle vor dem Umzug bereinigen (gezielte `UPDATE`/`DELETE` gegen SQLite) und
das Migrationsskript erneut mit `TRUNCATE=1` starten – ein teilweise befuelltes
Ziel wuerde sonst zu doppelten Primaerschluesseln fuehren.

### 4.2 Variante B: pgloader

Vorteil: Sehr schnell bei grossen Datenbanken, batterien-inklusive.
Nachteil: Zusatz-Tool, unter Windows nur ueber WSL/Linux praktisch nutzbar.

```bash
# Linux/WSL
sudo apt install pgloader

# Achtung: pgloader erzeugt Tabellen selbst, wenn die Ziel-DB leer ist.
# Damit das Schema exakt zu Alembic passt, vorher einmal migrieren und
# anschliessend pgloader mit --with "data only" benutzen.
psql "postgresql://bis_user@db.example.com/bis" <<'SQL'
TRUNCATE TABLE
    "Mitarbeiter", "Abteilung", "SchichtbuchThema"  -- ... usw.
    RESTART IDENTITY CASCADE;
SQL

pgloader \
  --with "data only" \
  --with "disable triggers" \
  --with "reset sequences" \
  sqlite:///C:/BIS-Daten/database_main.db \
  postgresql://bis_user:GeheimesPasswort@db.example.com/bis
```

Fuer die Mehrheit der Installationen ist **Variante A** ausreichend schnell
und deutlich besser reproduzierbar.

### 4.3 Verifikation nach dem Umzug

```bash
# Stichproben:
psql "$TARGET_URL" -c 'SELECT COUNT(*) FROM "Mitarbeiter";'
psql "$TARGET_URL" -c 'SELECT COUNT(*) FROM "SchichtbuchThema";'

# App gegen Postgres starten, Login mit einem bestehenden Account durchfuehren.
```

## 5. Docker Compose mit Postgres (optional)

Der mitgelieferte [`docker-compose.yml`](../docker-compose.yml) nutzt weiterhin
SQLite (`DATABASE_URL=/data/database_main.db`). Fuer Postgres genuegt ein
ergaenzender Service und eine Anpassung an `Application-Service`:

```yaml
services:
  Application-Service:
    environment:
      DATABASE_URL: postgresql+psycopg://bis_user:${POSTGRES_PASSWORD}@Postgres-Service:5432/bis
    depends_on:
      Postgres-Service:
        condition: service_healthy
    # DB liegt nicht mehr im Host-Volume; Uploads weiterhin unter /data/Daten

  Postgres-Service:
    image: postgres:16-alpine
    container_name: bis-postgres
    environment:
      POSTGRES_USER: bis_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD fehlt}
      POSTGRES_DB: bis
      TZ: Europe/Berlin
    volumes:
      - C:\BIS-Postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bis_user -d bis"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Der Backup-Service braucht fuer Postgres dieselbe DATABASE_URL wie die App,
  # damit bis_backup.sh / notify_admins.sh pg_dump bzw. psql statt sqlite3
  # verwenden. Der Applikations-Volume-Mount mit der .db-Datei entfaellt.
  Backup-Service:
    environment:
      DATABASE_URL: postgresql+psycopg://bis_user:${POSTGRES_PASSWORD}@Postgres-Service:5432/bis
    depends_on:
      Postgres-Service:
        condition: service_healthy
```

In der `.env`:

```bash
POSTGRES_PASSWORD=<starkes-passwort-hier>
```

Der `Backup-Service` wird automatisch den Postgres-Pfad verwenden, sobald
`DATABASE_URL` auf `postgresql+psycopg://...` zeigt (siehe
[Abschnitt 6](#6-backups-pg_dump)).

## 6. Backups (pg_dump)

Siehe [BACKUP_STRATEGIE.md](BACKUP_STRATEGIE.md) fuer die vollstaendige
Strategie (Retention, Verschluesselung, Benachrichtigungen). Kurzfassung:

- Das Backup-Skript [`docker/backup/bis_backup.sh`](../docker/backup/bis_backup.sh)
  erkennt Postgres anhand der Umgebungsvariablen `DATABASE_URL`.
- Fuer Postgres wird `pg_dump --format=custom` erzeugt
  (`database_main.dump`) statt `sqlite3 .backup`.
- Restore:

  ```bash
  pg_restore --clean --if-exists \
      --dbname=postgresql://bis_user:$PGPASSWORD@db.example.com/bis \
      /backup-plain/bis_YYYYMMDD_HHMMSS/database_main.dump
  ```

- Das Backup-Image enthaelt `postgresql-client`, damit beide DB-Typen ohne
  weitere Host-Installation gesichert werden koennen.
- Uploads (`/data/Daten/`) werden unveraendert als `uploads.tar.gz` archiviert.

## 7. Rollback zu SQLite

SQLite bleibt weiterhin voll unterstuetzt. Um zurueckzuwechseln:

1. `DATABASE_URL` wieder auf den SQLite-Pfad setzen.
2. App neu starten.
3. Alembic-History bleibt konsistent, da beide DBs denselben Revisions-Graph
   teilen.

Ein Re-Import von Daten Postgres -> SQLite ist nicht vorgesehen; bei Bedarf
laesst sich `scripts/migrate_sqlite_to_postgres.py` mit vertauschten URLs
starten – allerdings muss die Ziel-SQLite-Datei vorher existieren und per
Alembic migriert sein.

## 8. Bekannte Unterschiede SQLite <-> Postgres

| Thema | SQLite | Postgres | Hinweis |
|---|---|---|---|
| Autoincrement | `INTEGER PRIMARY KEY` | `IDENTITY`/`SERIAL` | Beides via SA deklariert, siehe [`utils/db_schema.py`](../utils/db_schema.py) |
| Boolean | `INTEGER 0/1` | `BOOLEAN` (kompatibel zu 0/1) | BIS nutzt durchgaengig `Integer` |
| `IFNULL` | `IFNULL(a,b)` | `COALESCE(a,b)` | Helfer: [`utils/db_sql.py`](../utils/db_sql.py) |
| `GROUP_CONCAT` | ja | `STRING_AGG` | Helfer: `string_agg(...)` in `utils/db_sql.py` |
| `strftime` | vorhanden | nicht vorhanden | Datumsfilter besser als Python-`date`/`datetime`-Parameter uebergeben |
| Case-Sensitivity | standardmaessig case-insensitive bei `LIKE` | case-sensitive | Fuer case-insensitive Suchen `ILIKE` oder `func.lower(...)` verwenden |
| `datetime('now')` | vorhanden | `now()` / `current_timestamp` | Helfer: `now_sql()` |
| Sortierung von `NULL` | `NULLS FIRST` | `NULLS LAST` (Default) | Bei Bedarf `.nulls_last()` explizit setzen |

## 9. Regelmaessige Wartung

- `VACUUM (ANALYZE)` laeuft in Postgres automatisch. Bei sehr grossen
  Loesch-/Update-Lasten manuell: `VACUUM ANALYZE;`
- Postgres-Logs unter `/var/log/postgresql/` (nativ) bzw. `docker logs
  bis-postgres` (Container).
- Health-Endpoint der App nicht vergessen – er zeigt auch DB-Konnektivitaet.
