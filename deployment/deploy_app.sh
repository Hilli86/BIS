#!/bin/bash

#########################################
# BIS - App Deployment Script
# Als 'bis' Benutzer ausführen!
#########################################

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}BIS App Deployment${NC}"
echo -e "${GREEN}================================${NC}"

# Prüfen ob als bis-Benutzer ausgeführt
if [ "$USER" != "bis" ]; then
    echo -e "${RED}Bitte als 'bis' Benutzer ausführen!${NC}"
    echo "Befehl: su - bis"
    exit 1
fi

BIS_HOME="/opt/bis"
BIS_DATA="/var/www/bis-data"

# Prüfen ob im richtigen Verzeichnis
if [ ! -f "$BIS_HOME/app.py" ]; then
    echo -e "${RED}app.py nicht gefunden in $BIS_HOME${NC}"
    echo "Bitte zuerst den Code nach $BIS_HOME hochladen"
    exit 1
fi

cd "$BIS_HOME"

echo -e "\n${YELLOW}1. Virtual Environment erstellen...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
else
    echo "Virtual Environment existiert bereits"
fi

echo -e "\n${YELLOW}2. Dependencies installieren...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

echo -e "\n${YELLOW}3. Umgebungsvariablen erstellen...${NC}"
if [ ! -f ".env" ]; then
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    
    cat > .env << EOF
# Flask-Konfiguration
FLASK_ENV=production
FLASK_DEBUG=False

# Sicherheit
SECRET_KEY=${SECRET_KEY}

# Datenbank
DATABASE_URL=${BIS_DATA}/database_main.db

# Upload-Ordner
UPLOAD_BASE_FOLDER=${BIS_DATA}/Daten

# SQL-Tracing
SQL_TRACING=False
EOF
    echo -e "${GREEN}✓ .env erstellt mit generiertem SECRET_KEY${NC}"
else
    echo -e "${YELLOW}⚠ .env existiert bereits - wird nicht überschrieben${NC}"
fi

echo -e "\n${YELLOW}4. Datenbank und Uploads vorbereiten...${NC}"
if [ -f "database_main.db" ] && [ ! -f "$BIS_DATA/database_main.db" ]; then
    cp database_main.db "$BIS_DATA/database_main.db"
    echo "✓ Datenbank kopiert"
fi

if [ -d "Daten" ]; then
    cp -r Daten/* "$BIS_DATA/Daten/" 2>/dev/null || true
    echo "✓ Upload-Dateien kopiert"
fi

echo -e "\n${YELLOW}5. Gunicorn-Konfiguration erstellen...${NC}"
cat > gunicorn_config.py << 'EOF'
import multiprocessing

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 120
accesslog = "/var/log/bis/access.log"
errorlog = "/var/log/bis/error.log"
loglevel = "info"
proc_name = "bis-app"
daemon = False
raw_env = ["FLASK_ENV=production"]
EOF
echo "✓ gunicorn_config.py erstellt"

echo -e "\n${YELLOW}6. App testen...${NC}"
source venv/bin/activate
export $(grep -v '^#' .env | xargs)

# Kurzer Test
timeout 5 python3 -c "from app import app; print('✓ App kann importiert werden')" || {
    echo -e "${RED}✗ Fehler beim Import der App${NC}"
    exit 1
}

echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}App-Deployment abgeschlossen!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "${YELLOW}Nächste Schritte (als root):${NC}"
echo "1. Systemd Service einrichten:"
echo "   sudo cp $BIS_HOME/deployment/bis.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable bis.service"
echo "   sudo systemctl start bis.service"
echo ""
echo "2. Nginx einrichten:"
echo "   sudo cp $BIS_HOME/deployment/nginx_bis.conf /etc/nginx/sites-available/bis"
echo "   sudo ln -s /etc/nginx/sites-available/bis /etc/nginx/sites-enabled/"
echo "   sudo rm /etc/nginx/sites-enabled/default"
echo "   sudo nginx -t"
echo "   sudo systemctl restart nginx"
echo ""
echo "3. Status prüfen:"
echo "   sudo systemctl status bis.service"



