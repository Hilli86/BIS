#!/bin/bash

#########################################
# BIS - App Update Script
# Aktualisiert die Anwendung auf dem Server
# Als root ausführen!
#########################################

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}BIS App Update${NC}"
echo -e "${GREEN}================================${NC}"

# Prüfen ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Bitte als root ausführen (sudo)${NC}"
    exit 1
fi

BIS_HOME="/opt/bis"
BIS_DATA="/var/www/bis-data"
BACKUP_DIR="/opt/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Prüfen ob App existiert
if [ ! -f "$BIS_HOME/app.py" ]; then
    echo -e "${RED}App nicht gefunden in $BIS_HOME${NC}"
    exit 1
fi

echo -e "\n${YELLOW}1. Backup erstellen...${NC}"
mkdir -p "$BACKUP_DIR"
BACKUP_NAME="bis_pre_update_${TIMESTAMP}.tar.gz"
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}" \
    -C /var/www bis-data/database_main.db \
    -C /opt bis/.env 2>/dev/null || true
echo -e "${GREEN}✓ Backup erstellt: ${BACKUP_NAME}${NC}"

echo -e "\n${YELLOW}2. Service stoppen...${NC}"
systemctl stop bis.service
echo -e "${GREEN}✓ Service gestoppt${NC}"

echo -e "\n${YELLOW}3. Dependencies aktualisieren...${NC}"
su - bis -c "cd $BIS_HOME && source venv/bin/activate && pip install -r requirements.txt --upgrade"
echo -e "${GREEN}✓ Dependencies aktualisiert${NC}"

echo -e "\n${YELLOW}4. Datenbank-Migrationen (automatisch)...${NC}"
# Backup der Datenbank vor Migration
cp "$BIS_DATA/database_main.db" "$BIS_DATA/database_main.db.pre_migration_${TIMESTAMP}"

# Nutze die neue automatische Migrations-Funktion
su - bis -c "cd $BIS_HOME && source venv/bin/activate && bash deployment/run_migrations_after_pull.sh" || {
    echo -e "${RED}✗ Migration fehlgeschlagen - stelle Backup wieder her${NC}"
    cp "$BIS_DATA/database_main.db.pre_migration_${TIMESTAMP}" "$BIS_DATA/database_main.db"
    systemctl start bis.service
    exit 1
}
echo -e "${GREEN}✓ Migrationen durchgeführt${NC}"

echo -e "\n${YELLOW}5. Berechtigungen prüfen...${NC}"
chown -R bis:bis "$BIS_HOME"
chown -R bis:bis "$BIS_DATA"
chmod -R 755 "$BIS_DATA"
echo -e "${GREEN}✓ Berechtigungen aktualisiert${NC}"

echo -e "\n${YELLOW}6. Service starten...${NC}"
systemctl start bis.service
sleep 2

# Status prüfen
if systemctl is-active --quiet bis.service; then
    echo -e "${GREEN}✓ Service läuft${NC}"
else
    echo -e "${RED}✗ Service konnte nicht gestartet werden!${NC}"
    journalctl -u bis.service -n 20 --no-pager
    exit 1
fi

echo -e "\n${YELLOW}7. Health-Check...${NC}"
sleep 3
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null)
if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "302" ]; then
    echo -e "${GREEN}✓ App antwortet (HTTP ${HTTP_STATUS})${NC}"
else
    echo -e "${RED}✗ App antwortet nicht korrekt (HTTP ${HTTP_STATUS})${NC}"
    echo "Prüfen Sie die Logs: journalctl -u bis.service -f"
fi

echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}Update abgeschlossen!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Backup gespeichert unter:${NC}"
echo "${BACKUP_DIR}/${BACKUP_NAME}"
echo ""
echo -e "${YELLOW}Nützliche Befehle:${NC}"
echo "Status:  systemctl status bis.service"
echo "Logs:    journalctl -u bis.service -f"
echo "Restart: systemctl restart bis.service"



