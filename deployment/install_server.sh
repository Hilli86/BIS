#!/bin/bash

#########################################
# BIS - Automatisches Server-Setup Script
# Für Ubuntu 24.04 / Debian 12 LXC Container
#########################################

set -e  # Bei Fehler abbrechen

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}BIS Server Installation${NC}"
echo -e "${GREEN}================================${NC}"

# Prüfen ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Bitte als root ausführen (sudo)${NC}"
    exit 1
fi

# Konfiguration
BIS_USER="bis"
BIS_HOME="/opt/bis"
BIS_DATA="/var/www/bis-data"
BIS_LOG="/var/log/bis"
BACKUP_DIR="/opt/backups"

echo -e "\n${YELLOW}1. System aktualisieren...${NC}"
apt update && apt upgrade -y

echo -e "\n${YELLOW}2. Zeitzone einstellen...${NC}"
timedatectl set-timezone Europe/Berlin

echo -e "\n${YELLOW}3. Systemabhängigkeiten installieren...${NC}"
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    nginx \
    sqlite3 \
    curl \
    vim \
    htop \
    ufw \
    certbot \
    python3-certbot-nginx \
    fail2ban

echo -e "\n${YELLOW}4. Benutzer '${BIS_USER}' erstellen...${NC}"
if id "$BIS_USER" &>/dev/null; then
    echo "Benutzer existiert bereits"
else
    useradd -m -s /bin/bash "$BIS_USER"
    echo -e "${GREEN}Benutzer erstellt. Bitte Passwort setzen:${NC}"
    passwd "$BIS_USER"
fi

echo -e "\n${YELLOW}5. Verzeichnisse erstellen...${NC}"
mkdir -p "$BIS_HOME"
mkdir -p "$BIS_DATA"
mkdir -p "$BIS_LOG"
mkdir -p "$BACKUP_DIR"
mkdir -p "$BIS_DATA/Daten/Schichtbuch/Themen"

# Berechtigungen setzen
chown -R "$BIS_USER:$BIS_USER" "$BIS_HOME"
chown -R "$BIS_USER:$BIS_USER" "$BIS_DATA"
chown -R "$BIS_USER:$BIS_USER" "$BIS_LOG"

echo -e "\n${YELLOW}6. Firewall konfigurieren...${NC}"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw --force enable

echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}Basis-Installation abgeschlossen!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Nächste Schritte:${NC}"
echo "1. Code nach ${BIS_HOME} hochladen (SCP/Git)"
echo "2. Als Benutzer '${BIS_USER}' einloggen: su - ${BIS_USER}"
echo "3. Deployment-Script ausführen: ./deployment/deploy_app.sh"
echo ""
echo -e "${YELLOW}Oder nutzen Sie das Deployment-Guide:${NC}"
echo "cat DEPLOYMENT_GUIDE.md"



