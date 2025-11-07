#!/bin/bash

#########################################
# BIS Backup Script
# Erstellt Backups der Datenbank und Uploads
#########################################

BACKUP_DIR="/opt/backups"
DATA_DIR="/var/www/bis-data"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="bis_backup_${TIMESTAMP}"
RETENTION_DAYS=30

# Log-Funktion
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "Starte Backup: ${BACKUP_NAME}"

# Backup-Verzeichnis erstellen
mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

# Datenbank-Backup
log "Sichere Datenbank..."
if [ -f "${DATA_DIR}/database_main.db" ]; then
    sqlite3 "${DATA_DIR}/database_main.db" ".backup '${BACKUP_DIR}/${BACKUP_NAME}/database_main.db'"
    log "✓ Datenbank gesichert"
else
    log "✗ FEHLER: Datenbank nicht gefunden!"
    exit 1
fi

# Uploads-Backup
log "Sichere Upload-Dateien..."
if [ -d "${DATA_DIR}/Daten" ]; then
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}/uploads.tar.gz" -C "${DATA_DIR}" Daten/
    log "✓ Upload-Dateien gesichert"
else
    log "⚠ Upload-Verzeichnis nicht gefunden - überspringe"
fi

# Konfiguration sichern
log "Sichere Konfiguration..."
if [ -f "/opt/bis/.env" ]; then
    cp /opt/bis/.env "${BACKUP_DIR}/${BACKUP_NAME}/.env"
    log "✓ Konfiguration gesichert"
fi

# Backup-Info erstellen
cat > "${BACKUP_DIR}/${BACKUP_NAME}/backup_info.txt" << EOF
BIS Backup Information
======================
Erstellt: $(date)
Hostname: $(hostname)
Backup-Name: ${BACKUP_NAME}

Inhalt:
- database_main.db (SQLite Datenbank)
- uploads.tar.gz (Upload-Dateien)
- .env (Konfiguration)

Restore-Anleitung:
1. Service stoppen: systemctl stop bis.service
2. Datenbank: sqlite3 /var/www/bis-data/database_main.db ".restore 'database_main.db'"
3. Uploads: tar -xzf uploads.tar.gz -C /var/www/bis-data/
4. Berechtigungen: chown -R bis:bis /var/www/bis-data
5. Service starten: systemctl start bis.service
EOF

# Backup komprimieren
log "Komprimiere Backup..."
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "${BACKUP_DIR}" "${BACKUP_NAME}"

# Backup-Größe ermitteln
BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
log "✓ Backup erstellt: ${BACKUP_NAME}.tar.gz (${BACKUP_SIZE})"

# Temporäres Verzeichnis löschen
rm -rf "${BACKUP_DIR}/${BACKUP_NAME}"

# Alte Backups löschen (älter als RETENTION_DAYS)
log "Lösche alte Backups (älter als ${RETENTION_DAYS} Tage)..."
DELETED=$(find "${BACKUP_DIR}" -name "bis_backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log "✓ ${DELETED} alte Backups gelöscht"
fi

# Backup-Übersicht
log "Aktuelle Backups:"
ls -lh "${BACKUP_DIR}"/bis_backup_*.tar.gz | tail -5

log "Backup erfolgreich abgeschlossen!"



