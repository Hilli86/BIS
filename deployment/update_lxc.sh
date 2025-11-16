#!/bin/bash

#########################################
# BIS - LXC Update Script
# Aktualisiert die BIS-Anwendung in einem LXC-Container
# Als root ausführen!
#########################################

set -e

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfiguration
BIS_HOME="/opt/bis"
BIS_DATA="/var/www/bis-data"
BACKUP_DIR="/opt/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BIS_USER="bis"
BACKUP_NAME=""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  BIS LXC Update Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Prüfen ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}✗ Bitte als root ausführen (sudo)${NC}"
    exit 1
fi

# Prüfen ob App-Verzeichnis existiert
if [ ! -d "$BIS_HOME" ]; then
    echo -e "${RED}✗ App-Verzeichnis nicht gefunden: $BIS_HOME${NC}"
    exit 1
fi

# Prüfen ob Git-Repository vorhanden
if [ ! -d "$BIS_HOME/.git" ]; then
    echo -e "${RED}✗ Kein Git-Repository in $BIS_HOME gefunden${NC}"
    exit 1
fi

# Prüfen ob bis-Benutzer existiert
if ! id "$BIS_USER" &>/dev/null; then
    echo -e "${RED}✗ Benutzer '$BIS_USER' existiert nicht${NC}"
    exit 1
fi

echo -e "${BLUE}Konfiguration:${NC}"
echo "  BIS_HOME:    $BIS_HOME"
echo "  BIS_DATA:    $BIS_DATA"
echo "  BACKUP_DIR:  $BACKUP_DIR"
echo "  BIS_USER:    $BIS_USER"
echo ""

# ============================================
# 1. Backup erstellen
# ============================================
echo -e "${YELLOW}[1/7] Backup erstellen...${NC}"
mkdir -p "$BACKUP_DIR"

# Backup der Datenbank
if [ -f "$BIS_DATA/database_main.db" ]; then
    BACKUP_NAME="bis_backup_${TIMESTAMP}.tar.gz"
    tar -czf "${BACKUP_DIR}/${BACKUP_NAME}" \
        -C "$(dirname "$BIS_DATA")" "$(basename "$BIS_DATA")/database_main.db" \
        2>/dev/null || true
    
    if [ -f "${BACKUP_DIR}/${BACKUP_NAME}" ]; then
        echo -e "${GREEN}✓ Backup erstellt: ${BACKUP_NAME}${NC}"
    else
        echo -e "${YELLOW}⚠ Backup konnte nicht erstellt werden${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Datenbank nicht gefunden, kein Backup erstellt${NC}"
fi

# Backup der .env Datei falls vorhanden
if [ -f "$BIS_HOME/.env" ]; then
    cp "$BIS_HOME/.env" "$BIS_HOME/.env.backup_${TIMESTAMP}"
    echo -e "${GREEN}✓ .env gesichert${NC}"
fi

# ============================================
# 2. Service stoppen
# ============================================
echo -e "\n${YELLOW}[2/7] Service stoppen...${NC}"
if systemctl is-active --quiet bis.service 2>/dev/null; then
    systemctl stop bis.service
    sleep 2
    echo -e "${GREEN}✓ Service gestoppt${NC}"
else
    echo -e "${YELLOW}⚠ Service war nicht aktiv${NC}"
fi

# ============================================
# 3. Git Pull
# ============================================
echo -e "\n${YELLOW}[3/7] Code aktualisieren (Git Pull)...${NC}"

# Git safe.directory konfigurieren (für bis-Benutzer)
su - "$BIS_USER" -c "cd $BIS_HOME && git config --global --add safe.directory $BIS_HOME" 2>/dev/null || true

# Aktuellen Branch ermitteln (als bis-Benutzer)
CURRENT_BRANCH=$(su - "$BIS_USER" -c "cd $BIS_HOME && git rev-parse --abbrev-ref HEAD")
echo -e "${BLUE}  Aktueller Branch: ${CURRENT_BRANCH}${NC}"

# Git Status prüfen (als bis-Benutzer)
HAS_CHANGES=$(su - "$BIS_USER" -c "cd $BIS_HOME && git status --porcelain" | wc -l)
if [ "$HAS_CHANGES" -gt 0 ]; then
    echo -e "${YELLOW}⚠ Uncommitted Änderungen gefunden!${NC}"
    echo -e "${YELLOW}  Diese werden beim Pull möglicherweise überschrieben${NC}"
    read -p "  Fortfahren? (j/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Jj]$ ]]; then
        echo -e "${RED}✗ Update abgebrochen${NC}"
        systemctl start bis.service 2>/dev/null || true
        exit 1
    fi
fi

# Git Pull ausführen (als bis-Benutzer)
if su - "$BIS_USER" -c "cd $BIS_HOME && git pull origin $CURRENT_BRANCH"; then
    echo -e "${GREEN}✓ Code aktualisiert${NC}"
    LATEST_COMMIT=$(su - "$BIS_USER" -c "cd $BIS_HOME && git rev-parse --short HEAD")
    echo -e "${BLUE}  Neuester Commit: ${LATEST_COMMIT}${NC}"
else
    echo -e "${RED}✗ Git Pull fehlgeschlagen${NC}"
    systemctl start bis.service 2>/dev/null || true
    exit 1
fi

# ============================================
# 4. Dependencies aktualisieren
# ============================================
echo -e "\n${YELLOW}[4/7] Dependencies aktualisieren...${NC}"

# Prüfen ob venv existiert
if [ ! -d "$BIS_HOME/venv" ]; then
    echo -e "${YELLOW}⚠ Virtual Environment nicht gefunden, erstelle neues...${NC}"
    su - "$BIS_USER" -c "cd $BIS_HOME && python3 -m venv venv"
fi

# Dependencies installieren/aktualisieren
if [ -f "$BIS_HOME/requirements.txt" ]; then
    su - "$BIS_USER" -c "cd $BIS_HOME && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt --upgrade" || {
        echo -e "${RED}✗ Fehler beim Installieren der Dependencies${NC}"
        systemctl start bis.service 2>/dev/null || true
        exit 1
    }
    echo -e "${GREEN}✓ Dependencies aktualisiert${NC}"
else
    echo -e "${YELLOW}⚠ requirements.txt nicht gefunden${NC}"
fi

# ============================================
# 5. Datenbank-Migrationen
# ============================================
echo -e "\n${YELLOW}[5/7] Datenbank-Migrationen durchführen...${NC}"

# Backup der Datenbank vor Migration
if [ -f "$BIS_DATA/database_main.db" ]; then
    cp "$BIS_DATA/database_main.db" "$BIS_DATA/database_main.db.pre_migration_${TIMESTAMP}"
    echo -e "${GREEN}✓ Datenbank-Backup vor Migration erstellt${NC}"
fi

# Migrations ausführen
#if [ -f "$BIS_HOME/deployment/run_migrations_after_pull.sh" ]; then
#    su - "$BIS_USER" -c "cd $BIS_HOME && source venv/bin/activate && bash deployment/run_migrations_after_pull.sh" || {
#        echo -e "${RED}✗ Migration fehlgeschlagen - stelle Backup wieder her${NC}"
#        if [ -f "$BIS_DATA/database_main.db.pre_migration_${TIMESTAMP}" ]; then
#            cp "$BIS_DATA/database_main.db.pre_migration_${TIMESTAMP}" "$BIS_DATA/database_main.db"
#        fi
#        systemctl start bis.service 2>/dev/null || true
#        exit 1
#    }
#    echo -e "${GREEN}✓ Migrationen durchgeführt${NC}"
#else
#    echo -e "${YELLOW}⚠ Migrations-Script nicht gefunden, überspringe Migrationen${NC}"
#fi

# ============================================
# 6. Berechtigungen setzen
# ============================================
echo -e "\n${YELLOW}[6/7] Berechtigungen prüfen...${NC}"
chown -R "$BIS_USER:$BIS_USER" "$BIS_HOME"
chown -R "$BIS_USER:$BIS_USER" "$BIS_DATA" 2>/dev/null || true
chmod -R 755 "$BIS_DATA" 2>/dev/null || true
echo -e "${GREEN}✓ Berechtigungen aktualisiert${NC}"

# ============================================
# 7. Service starten und prüfen
# ============================================
echo -e "\n${YELLOW}[7/7] Service starten...${NC}"

# Systemd daemon reload falls Service-Datei geändert wurde
if [ -f "$BIS_HOME/deployment/bis.service" ]; then
    systemctl daemon-reload
fi

# Service starten
systemctl start bis.service
sleep 3

# Status prüfen
if systemctl is-active --quiet bis.service; then
    echo -e "${GREEN}✓ Service läuft${NC}"
else
    echo -e "${RED}✗ Service konnte nicht gestartet werden!${NC}"
    echo -e "${YELLOW}Letzte Log-Einträge:${NC}"
    journalctl -u bis.service -n 30 --no-pager || true
    exit 1
fi

# ============================================
# Health-Check
# ============================================
echo -e "\n${YELLOW}Health-Check durchführen...${NC}"
sleep 2

# Prüfe ob App antwortet
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "302" ] || [ "$HTTP_STATUS" = "301" ]; then
    echo -e "${GREEN}✓ App antwortet (HTTP ${HTTP_STATUS})${NC}"
else
    echo -e "${YELLOW}⚠ App antwortet nicht wie erwartet (HTTP ${HTTP_STATUS})${NC}"
    echo -e "${YELLOW}  Prüfen Sie die Logs: journalctl -u bis.service -f${NC}"
fi

# ============================================
# Zusammenfassung
# ============================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Update abgeschlossen!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Zusammenfassung:${NC}"
echo "  Branch:        $CURRENT_BRANCH"
echo "  Commit:        $LATEST_COMMIT"
if [ -n "$BACKUP_NAME" ] && [ -f "${BACKUP_DIR}/${BACKUP_NAME}" ]; then
    echo "  Backup:        ${BACKUP_DIR}/${BACKUP_NAME}"
fi
echo ""
echo -e "${YELLOW}Nützliche Befehle:${NC}"
echo "  Status:  systemctl status bis.service"
echo "  Logs:    journalctl -u bis.service -f"
echo "  Restart: systemctl restart bis.service"
echo ""

