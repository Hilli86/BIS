"""Alembic-Umgebungsskript fuer BIS.

Bezieht die Datenbank-URL aus ``DATABASE_URL`` (Phase 0: reiner SQLite-Pfad
oder vollstaendige SA-URL; Phase 5+ dann Postgres-URL) und bindet die zentrale
``utils.db_schema.metadata`` als ``target_metadata`` fuer Autogenerate-Diffs.

Fallbacks:

- Wenn ``DATABASE_URL`` nicht gesetzt ist, wird ``DATABASE_URL`` aus der
  Flask-Config (``app.py``) gelesen – dort ist der Default ``database_main.db``.
- ``sqlalchemy.url`` aus ``alembic.ini`` wird weiterhin respektiert, falls
  jemand Alembic gezielt mit ``-x`` oder eigener INI startet.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Projekt-Root in sys.path, damit ``utils.db_schema`` und ``utils.database``
# importierbar sind, auch wenn Alembic aus einem beliebigen Arbeitsverzeichnis
# gestartet wird.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.database import normalize_db_url  # noqa: E402
from utils.db_schema import metadata  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    env_url = os.environ.get('DATABASE_URL')
    if env_url:
        return normalize_db_url(env_url)
    ini_url = config.get_main_option('sqlalchemy.url')
    if ini_url and ini_url.strip() and 'driver://' not in ini_url:
        return normalize_db_url(ini_url)
    # Letzter Fallback: gleicher Default wie in config.py (Flask-App).
    return normalize_db_url('database_main.db')


target_metadata = metadata


def run_migrations_offline() -> None:
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        render_as_batch=url.startswith('sqlite'),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _resolve_url()
    ini_section = config.get_section(config.config_ini_section, {}) or {}
    ini_section['sqlalchemy.url'] = url

    connectable = engine_from_config(
        ini_section,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith('sqlite'),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
