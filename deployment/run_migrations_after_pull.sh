#!/bin/bash
# Automatische Migrations-Ausführung nach Git Pull
# Kann in update_app.sh integriert werden oder separat aufgerufen werden

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  BIS - Automatische Migrations${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

# Wechsle ins Projektverzeichnis
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Aktiviere virtuelle Umgebung falls vorhanden
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${GREEN}[OK] Virtuelle Umgebung aktiviert${NC}"
fi

# Prüfe ob Datenbank existiert
DB_PATH="${DATABASE_URL:-database_main.db}"
if [ ! -f "$DB_PATH" ]; then
    echo -e "${RED}[FEHLER] Datenbank '$DB_PATH' nicht gefunden!${NC}"
    echo -e "${YELLOW}[INFO] Bitte führen Sie 'python init_database.py' aus${NC}"
    exit 1
fi

# Führe Migrations aus
echo -e "${YELLOW}[INFO] Führe Migrations aus...${NC}"
python3 -c "
import sys
import os
sys.path.insert(0, '.')

from flask import Flask
from config import config

app = Flask(__name__)
config_name = os.environ.get('FLASK_ENV', 'production')
app.config.from_object(config[config_name])

with app.app_context():
    from utils.database_check import run_pending_migrations
    db_path = app.config['DATABASE_URL']
    success, executed, errors = run_pending_migrations(db_path, verbose=True)
    
    if errors:
        print('')
        print('=' * 70)
        print('FEHLER bei Migrations!')
        print('=' * 70)
        for error in errors:
            print(f'  - {error}')
        sys.exit(1)
    
    if executed:
        print('')
        print('=' * 70)
        print(f'Erfolgreich: {len(executed)} Migration(s) ausgeführt')
        print('=' * 70)
    else:
        print('')
        print('=' * 70)
        print('Keine ausstehenden Migrations')
        print('=' * 70)
"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}==========================================${NC}"
    echo -e "${GREEN}  Migrations abgeschlossen${NC}"
    echo -e "${GREEN}==========================================${NC}"
else
    echo ""
    echo -e "${RED}==========================================${NC}"
    echo -e "${RED}  Migrations fehlgeschlagen!${NC}"
    echo -e "${RED}==========================================${NC}"
fi

exit $EXIT_CODE

