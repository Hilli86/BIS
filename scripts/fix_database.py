"""Schnellfix fuer Schema-Drift.

Seit Phase 4 der SA-Migration laeuft die komplette Schema-Pflege ueber
Alembic. Dieses Skript ist der bequeme Einzeiler ``alembic upgrade head``
und akzeptiert dieselben Umgebungs-Variablen wie ``init_database.py``
(``DATABASE_URL``). Es ersetzt die frueheren handgeschriebenen
``ALTER TABLE``-Reparaturen.

Aufruf aus dem Projektroot:
    py scripts/fix_database.py
"""

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from utils.database import normalize_db_url  # noqa: E402


def fix_database() -> None:
    db_url = normalize_db_url(os.environ.get('DATABASE_URL') or 'database_main.db')
    ini_path = os.path.join(_PROJECT_ROOT, 'alembic.ini')

    cfg = Config(ini_path)
    cfg.set_main_option('script_location', os.path.join(_PROJECT_ROOT, 'alembic'))
    cfg.set_main_option('sqlalchemy.url', db_url)
    os.environ['DATABASE_URL'] = db_url

    print(f"[INFO] Fuehre 'alembic upgrade head' aus (url={db_url}) ...")
    try:
        command.upgrade(cfg, 'head')
    except Exception as exc:
        print(f"\n[FEHLER] Alembic-Migration fehlgeschlagen: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("\n[ERFOLG] Datenbank-Update abgeschlossen!")


if __name__ == '__main__':
    fix_database()
