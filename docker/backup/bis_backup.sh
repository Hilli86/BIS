#!/bin/bash
# BIS Backup-Skript (Container-Variante)
# Sichert Datenbank (SQLite ODER Postgres) + Uploads nach /backup-plain/,
# erzeugt eine 7z AES-256 verschluesselte Kopie unter /backup-encrypted/
# und benachrichtigt Admins ueber notify_admins.sh.
#
# DB-Typ wird anhand der Umgebungsvariable DATABASE_URL bestimmt:
#   - leer oder mit "sqlite"/Dateipfad -> SQLite-Backup via 'sqlite3 .backup'
#   - "postgresql+psycopg://..."        -> Postgres-Backup via 'pg_dump --format=custom'

set -uo pipefail

DATA_DIR="/data"
PLAIN_DIR="/backup-plain"
ENC_DIR="/backup-encrypted"
DB_FILE="${DATA_DIR}/database_main.db"
UPLOADS_DIR="${DATA_DIR}/Daten"

# DB-Typ bestimmen. Default (leer) = SQLite auf ${DB_FILE}, damit bestehende
# Installationen ohne DATABASE_URL unveraendert weiterlaufen.
DATABASE_URL="${DATABASE_URL:-}"
case "${DATABASE_URL}" in
    postgres://*|postgresql://*|postgresql+*://*)
        DB_KIND="postgres"
        ;;
    *)
        DB_KIND="sqlite"
        ;;
esac

TS="$(date +'%Y%m%d_%H%M%S')"
NAME="bis_${TS}"
WORK_DIR="${PLAIN_DIR}/${NAME}"
ENC_FILE="${ENC_DIR}/${NAME}.7z"

RETENTION_DAILY="${RETENTION_DAILY:-14}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-8}"
RETENTION_MONTHLY="${RETENTION_MONTHLY:-12}"
NOTIFY_ON_SUCCESS="${NOTIFY_ON_SUCCESS:-true}"

START_EPOCH="$(date +%s)"
CURRENT_STAGE="init"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

fail() {
    local stage="$1"
    local exit_code="$2"
    local log_tail
    log_tail="$(tail -n 20 /var/log/backup.log 2>/dev/null | sed 's/"/\\"/g' | tr '\n' ' ' || true)"
    local zusatz
    zusatz="$(printf '{"exit_code": %s, "stage": "%s", "log_tail": "%s"}' \
        "${exit_code}" "${stage}" "${log_tail}")"
    log "FEHLER in Phase '${stage}' (Exit ${exit_code})"
    /usr/local/bin/notify_admins.sh failure "${zusatz}" "${stage}" "${exit_code}" \
        || log "WARNUNG: Failure-Notification konnte nicht geschrieben werden."
    rm -rf "${WORK_DIR}" 2>/dev/null || true
    exit 1
}

trap 'fail "${CURRENT_STAGE}" "$?"' ERR

log "===== Starte Backup ${NAME} (db=${DB_KIND}) ====="

CURRENT_STAGE="preflight"
if [ "${DB_KIND}" = "sqlite" ]; then
    if [ ! -f "${DB_FILE}" ]; then
        log "SQLite-Datenbank nicht gefunden: ${DB_FILE}"
        fail "preflight" 2
    fi
else
    # Postgres: pg_dump vorhanden?
    if ! command -v pg_dump >/dev/null 2>&1; then
        log "pg_dump nicht gefunden - Postgres-Backup nicht moeglich."
        fail "preflight" 2
    fi
fi

mkdir -p "${WORK_DIR}"

# 1) DB-Dump erzeugen
if [ "${DB_KIND}" = "sqlite" ]; then
    CURRENT_STAGE="sqlite_backup"
    DB_ARTIFACT="database_main.db"
    log "Erstelle SQLite Online-Backup..."
    sqlite3 "${DB_FILE}" ".backup '${WORK_DIR}/${DB_ARTIFACT}'"

    # 2) Integrity-Check
    CURRENT_STAGE="integrity_check"
    log "Pruefe Integritaet des Backups..."
    INTEGRITY="$(sqlite3 "${WORK_DIR}/${DB_ARTIFACT}" 'PRAGMA integrity_check;' | head -n1)"
    if [ "${INTEGRITY}" != "ok" ]; then
        log "Integrity-Check FEHLGESCHLAGEN: ${INTEGRITY}"
        fail "integrity_check" 3
    fi
    log "Integrity: ok"
else
    CURRENT_STAGE="pg_backup"
    DB_ARTIFACT="database_main.dump"
    # SA-URL ("postgresql+psycopg://...") -> libpq-URL ("postgresql://...")
    # konvertieren, damit pg_dump sie direkt akzeptiert.
    PGURL="$(printf '%s' "${DATABASE_URL}" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"
    log "Erstelle Postgres-Dump (custom format)..."
    # --format=custom ist pg_restore-faehig und bereits komprimiert.
    pg_dump --format=custom --file="${WORK_DIR}/${DB_ARTIFACT}" "${PGURL}"

    # 2) Integrity-Check: pg_restore -l listet das Inhaltsverzeichnis;
    # scheitert der Aufruf, ist der Dump unbrauchbar.
    CURRENT_STAGE="integrity_check"
    log "Pruefe Integritaet des Dumps (pg_restore -l)..."
    if ! pg_restore -l "${WORK_DIR}/${DB_ARTIFACT}" >/dev/null 2>&1; then
        log "Integrity-Check FEHLGESCHLAGEN: pg_restore -l konnte Dump nicht lesen."
        fail "integrity_check" 3
    fi
    log "Integrity: ok"
fi

# 3) Uploads archivieren
CURRENT_STAGE="tar"
if [ -d "${UPLOADS_DIR}" ]; then
    log "Archiviere Uploads..."
    tar -czf "${WORK_DIR}/uploads.tar.gz" -C "${DATA_DIR}" Daten
else
    log "WARNUNG: Upload-Verzeichnis ${UPLOADS_DIR} nicht gefunden (ueberspringe)."
fi

# 4) Checksums + Info
CURRENT_STAGE="checksums"
log "Erstelle Checksums..."
(
    cd "${WORK_DIR}"
    sha256sum "${DB_ARTIFACT}" > checksums.sha256
    if [ -f uploads.tar.gz ]; then
        sha256sum uploads.tar.gz >> checksums.sha256
    fi
)

DB_SIZE="$(du -h "${WORK_DIR}/${DB_ARTIFACT}" | cut -f1)"
UP_SIZE="$(du -h "${WORK_DIR}/uploads.tar.gz" 2>/dev/null | cut -f1 || echo '-')"
PLAIN_SIZE="$(du -sh "${WORK_DIR}" | cut -f1)"
SHA256_DB="$(awk '{print $1}' "${WORK_DIR}/checksums.sha256" | head -n1)"

if [ "${DB_KIND}" = "sqlite" ]; then
    DB_INFO_LINE=" - database_main.db       (SQLite, konsistent via .backup)"
else
    DB_INFO_LINE=" - database_main.dump     (Postgres, pg_dump --format=custom)"
fi

cat > "${WORK_DIR}/backup_info.txt" <<EOF
BIS Backup Information
======================
Erstellt:      $(date +'%Y-%m-%d %H:%M:%S %z')
Hostname:      $(hostname)
Backup-Name:   ${NAME}
DB-Typ:        ${DB_KIND}
Datenbank:     ${DB_SIZE}
Uploads:       ${UP_SIZE}
SHA256-DB:     ${SHA256_DB}

Inhalt:
${DB_INFO_LINE}
 - uploads.tar.gz         (Dateianhaenge)
 - checksums.sha256       (SHA-256 Pruefsummen)
 - backup_info.txt        (diese Datei)

Restore-Hinweis: siehe docs/BACKUP_STRATEGIE.md
EOF

# 5) Verschluesselte Kopie (7z AES-256)
CURRENT_STAGE="encrypt"
ENC_SIZE="-"
if [ -n "${BACKUP_ENCRYPTION_PASSWORD:-}" ]; then
    log "Erzeuge verschluesselte Kopie ${ENC_FILE}..."
    mkdir -p "${ENC_DIR}"
    # -mhe=on verschluesselt auch Dateinamen, -p"$PW" setzt Passwort (AES-256).
    # Keine Shell-Expansion des Passworts im Log (Quiet-Modus).
    7z a -t7z -m0=lzma2 -mx=5 -mhe=on -p"${BACKUP_ENCRYPTION_PASSWORD}" \
        "${ENC_FILE}" "${WORK_DIR}" > /dev/null
    ENC_SIZE="$(du -h "${ENC_FILE}" | cut -f1)"
    log "Verschluesseltes Archiv: ${ENC_SIZE}"
else
    log "WARNUNG: BACKUP_ENCRYPTION_PASSWORD nicht gesetzt - ueberspringe Verschluesselung."
fi

# 6) Retention (GFS)
CURRENT_STAGE="retention"
log "Wende Retention an (taeglich=${RETENTION_DAILY}, woechentlich=${RETENTION_WEEKLY}, monatlich=${RETENTION_MONTHLY})..."

apply_retention() {
    local base_dir="$1"     # Verzeichnis mit Backup-Eintraegen
    local pattern="$2"      # z. B. 'bis_*' (Verzeichnisse) oder 'bis_*.7z' (Dateien)
    local is_dir="$3"       # 1 = Verzeichnisse, 0 = Dateien

    [ -d "${base_dir}" ] || return 0

    # Liste aller Backups sortiert (juengstes zuerst)
    local entries
    if [ "${is_dir}" = "1" ]; then
        entries=$(find "${base_dir}" -maxdepth 1 -type d -name "${pattern}" -printf '%f\n' 2>/dev/null | sort -r)
    else
        entries=$(find "${base_dir}" -maxdepth 1 -type f -name "${pattern}" -printf '%f\n' 2>/dev/null | sort -r)
    fi

    local keep_daily=0 keep_weekly=0 keep_monthly=0
    local -A keep_set=()

    while IFS= read -r entry; do
        [ -n "${entry}" ] || continue
        # Datum aus bis_YYYYMMDD_HHMMSS extrahieren
        local date_part="${entry#bis_}"
        date_part="${date_part%%_*}"                   # YYYYMMDD
        local yyyy="${date_part:0:4}"
        local mm="${date_part:4:2}"
        local dd="${date_part:6:2}"
        local dow
        dow=$(date -d "${yyyy}-${mm}-${dd}" +%u 2>/dev/null || echo 0)   # 1=Mo..7=So

        local reason=""
        if [ "${keep_daily}" -lt "${RETENTION_DAILY}" ]; then
            reason="daily"
            keep_daily=$((keep_daily + 1))
        fi
        if [ "${dow}" = "7" ] && [ "${keep_weekly}" -lt "${RETENTION_WEEKLY}" ]; then
            reason="${reason:+${reason}+}weekly"
            keep_weekly=$((keep_weekly + 1))
        fi
        if [ "${dd}" = "01" ] && [ "${keep_monthly}" -lt "${RETENTION_MONTHLY}" ]; then
            reason="${reason:+${reason}+}monthly"
            keep_monthly=$((keep_monthly + 1))
        fi

        if [ -n "${reason}" ]; then
            keep_set["${entry}"]="${reason}"
        fi
    done <<< "${entries}"

    while IFS= read -r entry; do
        [ -n "${entry}" ] || continue
        if [ -z "${keep_set[${entry}]:-}" ]; then
            log "  loesche ${base_dir}/${entry}"
            rm -rf "${base_dir}/${entry}"
        fi
    done <<< "${entries}"
}

apply_retention "${PLAIN_DIR}" "bis_*" 1
apply_retention "${ENC_DIR}"   "bis_*.7z" 0

# 7) Erfolg melden
CURRENT_STAGE="notify_success"
END_EPOCH="$(date +%s)"
DURATION=$(( END_EPOCH - START_EPOCH ))

log "Backup abgeschlossen in ${DURATION}s (plain=${PLAIN_SIZE}, encrypted=${ENC_SIZE})"

if [ "${NOTIFY_ON_SUCCESS}" = "true" ]; then
    ZUSATZ="$(printf '{"dauer_sek": %s, "plain_size": "%s", "encrypted_size": "%s", "sha256_db": "%s", "pfad_plain": "%s", "pfad_encrypted": "%s"}' \
        "${DURATION}" "${PLAIN_SIZE}" "${ENC_SIZE}" "${SHA256_DB}" "${WORK_DIR}" "${ENC_FILE}")"
    /usr/local/bin/notify_admins.sh success "${ZUSATZ}" "${DURATION}" "${PLAIN_SIZE}" "${ENC_SIZE}" \
        || log "WARNUNG: Success-Notification konnte nicht geschrieben werden."
else
    log "NOTIFY_ON_SUCCESS=false - keine Erfolgs-Benachrichtigung."
fi

log "===== Ende ${NAME} (OK) ====="
exit 0
