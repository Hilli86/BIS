"""
Datenbank-Pruefung und Initialisierung beim App-Start.

Phase 1: Standardpfad ist ``alembic upgrade head`` (siehe ``alembic/env.py``).
Die Baseline-Migration ``0001_baseline`` legt Tabellen per
``metadata.create_all(checkfirst=True)`` an und ist damit sowohl auf frischen
als auch auf bestehenden Datenbanken sicher.

Legacy-Pfad ist weiterhin verfuegbar ueber die Umgebungsvariable
``BIS_DB_LEGACY_INIT=1`` (oder App-Config ``DB_LEGACY_INIT=True``). Damit
laeuft das alte ``init_database_schema`` aus ``database_schema_init.py`` –
nuetzlich als Fallback, falls Alembic in einem Spezialfall nicht startet.
"""

from __future__ import annotations

import os
import sys

from .database_check_helpers import check_database_integrity
from .database_schema_init import init_database_schema
from .database import normalize_db_url


def _use_legacy_init(app) -> bool:
    env_val = os.environ.get('BIS_DB_LEGACY_INIT', '').strip().lower()
    if env_val in ('1', 'true', 'yes', 'on'):
        return True
    return bool(app.config.get('DB_LEGACY_INIT', False))


def _sqlite_path_from_url(url: str):
    """Wenn ``url`` eine SQLite-URL ist, gib den Dateipfad zurueck; sonst None."""
    if not url:
        return None
    if url.startswith('sqlite:////'):
        return '/' + url[len('sqlite:////'):]
    if url.startswith('sqlite:///'):
        return url[len('sqlite:///'):]
    return None


def _run_alembic_upgrade(app, db_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    ini_path = os.path.join(project_root, 'alembic.ini')

    cfg = Config(ini_path)
    cfg.set_main_option('script_location', os.path.join(project_root, 'alembic'))
    cfg.set_main_option('sqlalchemy.url', db_url)
    # env.py liest DATABASE_URL bevorzugt aus der Umgebung; ohne das hier
    # erzeugte env-Var wuerde ein leer gesetzter INI-Wert zu einer
    # Fallback-URL fuehren.
    os.environ.setdefault('DATABASE_URL', db_url)

    app.logger.info('Alembic: upgrade head (url=%s)', db_url)
    command.upgrade(cfg, 'head')


def initialize_database_on_startup(app):
    """Hauptfunktion: startet beim App-Start Alembic (oder Legacy-Init).

    Rueckgabe ``True`` signalisiert einen erfolgreichen Lauf; andernfalls
    beendet die Funktion den Prozess via ``sys.exit(1)``.
    """
    raw_url = app.config['DATABASE_URL']
    db_url = normalize_db_url(raw_url)
    sqlite_path = _sqlite_path_from_url(db_url)

    print('=' * 70)
    print('  BIS - Datenbank-Pruefung und Initialisierung')
    print('=' * 70)
    print()

    if _use_legacy_init(app):
        if sqlite_path is None:
            print('[FEHLER] Legacy-Init unterstuetzt nur SQLite; DATABASE_URL ist nicht-sqlite.')
            sys.exit(1)
        print('[INFO] Legacy-Modus aktiv (BIS_DB_LEGACY_INIT=1 bzw. DB_LEGACY_INIT=True)')
        _run_legacy_init(sqlite_path)
    else:
        try:
            _run_alembic_upgrade(app, db_url)
            print('[OK] Alembic upgrade head abgeschlossen')
            # Haertung fuer Legacy-SQLite-Dateien:
            # Alembic-0001 verwendet metadata.create_all(checkfirst=True) und fuegt
            # damit auf bestehenden Tabellen keine spaeteren Spalten hinzu.
            # Deshalb im SQLite-Betrieb unmittelbar danach den idempotenten
            # Legacy-Schema-Abgleich laufen lassen (fehlende Spalten/Indizes).
            if sqlite_path is not None:
                print('[INFO] Pruefe auf fehlende Spalten und Indexes...')
                init_database_schema(sqlite_path, verbose=False)
                print('[OK] Spaltenpruefung abgeschlossen')
        except Exception as exc:
            print(f'[FEHLER] Alembic-Migration fehlgeschlagen: {exc}')
            sys.exit(1)

    # Integritaets-Gegencheck (leichtgewichtig): pruefe bekannte Kerntabellen.
    if sqlite_path is not None:
        print('[INFO] Pruefe Datenbank-Integritaet...')
        is_valid, missing_tables, errors = check_database_integrity(sqlite_path)
        if not is_valid:
            if missing_tables:
                print(f'[WARNUNG] Fehlende Tabellen trotz Migration: {", ".join(missing_tables)}')
            for error in errors:
                print(f'[FEHLER] {error}')
            sys.exit(1)
        print('[OK] Datenbank-Integritaet OK')

    print()
    print('=' * 70)
    print('  Datenbank-Pruefung abgeschlossen')
    print('=' * 70)
    print()

    return True


def _run_legacy_init(db_path: str) -> None:
    if not os.path.exists(db_path):
        print(f"[INFO] Datenbank '{db_path}' existiert nicht, erstelle sie...")
        init_database_schema(db_path, verbose=False)
        print('[OK] Datenbank erstellt und initialisiert')
        print()

    print('[INFO] Pruefe Datenbank-Integritaet...')
    is_valid, missing_tables, errors = check_database_integrity(db_path)

    if not is_valid:
        if missing_tables:
            print(f"[INFO] Fehlende Tabellen gefunden: {', '.join(missing_tables)}")
            print('[INFO] Initialisiere fehlende Strukturen...')
            init_database_schema(db_path, verbose=False)
            print('[OK] Datenbankstruktur aktualisiert')
        else:
            for error in errors:
                print(f'[FEHLER] {error}')
            print()
            sys.exit(1)
    else:
        print('[OK] Datenbank-Integritaet OK')
        print('[INFO] Pruefe auf fehlende Spalten und Indexes...')
        init_database_schema(db_path, verbose=False)
        print('[OK] Spaltenpruefung abgeschlossen')
