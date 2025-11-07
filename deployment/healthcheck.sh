#!/bin/bash

#########################################
# BIS Health Check Script
# Prüft ob die Anwendung läuft
#########################################

# Exit Codes:
# 0 - Alles OK
# 1 - Service Problem
# 2 - HTTP Problem
# 3 - Disk Space Problem

# Log-Funktion
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

ERRORS=0

# Service-Status prüfen
log "Prüfe BIS Service..."
if ! systemctl is-active --quiet bis.service; then
    log "✗ FEHLER: BIS Service ist nicht aktiv!"
    systemctl status bis.service --no-pager
    ERRORS=$((ERRORS + 1))
else
    log "✓ Service läuft"
fi

# HTTP-Status prüfen (lokaler Check)
log "Prüfe HTTP-Antwort..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null)
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "302" ]; then
    log "✓ HTTP OK (Status: ${HTTP_STATUS})"
else
    log "✗ FEHLER: HTTP antwortet nicht korrekt (Status: ${HTTP_STATUS})"
    ERRORS=$((ERRORS + 1))
fi

# Nginx-Status prüfen
log "Prüfe Nginx..."
if ! systemctl is-active --quiet nginx; then
    log "✗ FEHLER: Nginx ist nicht aktiv!"
    ERRORS=$((ERRORS + 1))
else
    log "✓ Nginx läuft"
fi

# Disk-Space prüfen
log "Prüfe Speicherplatz..."
DISK_USAGE=$(df -h /var/www/bis-data 2>/dev/null | tail -1 | awk '{print $5}' | sed 's/%//')
if [ -n "$DISK_USAGE" ]; then
    if [ "$DISK_USAGE" -gt 90 ]; then
        log "✗ KRITISCH: Disk-Space über 90% (${DISK_USAGE}%)"
        ERRORS=$((ERRORS + 1))
    elif [ "$DISK_USAGE" -gt 80 ]; then
        log "⚠ WARNUNG: Disk-Space über 80% (${DISK_USAGE}%)"
    else
        log "✓ Disk-Space OK (${DISK_USAGE}%)"
    fi
else
    log "⚠ Konnte Disk-Space nicht prüfen"
fi

# Datenbank-Größe
DB_SIZE=$(du -h /var/www/bis-data/database_main.db 2>/dev/null | cut -f1)
if [ -n "$DB_SIZE" ]; then
    log "ℹ Datenbank-Größe: ${DB_SIZE}"
fi

# Anzahl Gunicorn-Worker
WORKER_COUNT=$(pgrep -fc "gunicorn.*bis")
if [ "$WORKER_COUNT" -gt 0 ]; then
    log "✓ Gunicorn-Worker: ${WORKER_COUNT}"
else
    log "✗ Keine Gunicorn-Worker gefunden!"
    ERRORS=$((ERRORS + 1))
fi

# Zusammenfassung
log "================================"
if [ $ERRORS -eq 0 ]; then
    log "✓ Alle Checks erfolgreich - System läuft einwandfrei!"
    exit 0
else
    log "✗ ${ERRORS} Fehler gefunden - Bitte prüfen!"
    exit 1
fi



