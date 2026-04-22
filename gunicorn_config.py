"""
Gunicorn-Konfiguration fuer BIS.

Wird von Docker (``docker/bis.Dockerfile``) und systemd (``deployment/bis.service``)
genutzt. Startkommando: ``gunicorn -c gunicorn_config.py app:app``.

Design:
- ``preload_app=True``: ``app.py`` wird einmal im Master-Prozess importiert.
  Dadurch laufen Alembic-Migration, Benachrichtigungs-Cleanup und Nachversand
  (siehe ``run_startup_tasks`` in ``app.py``) genau einmal, nicht einmal pro
  Worker. Workers erben den Zustand per ``os.fork()``.
- ``BIS_RUN_STARTUP_TASKS=1`` wird hier direkt zu Beginn gesetzt, damit es vor
  dem App-Import im Master greift. Im ``post_fork``-Hook wird die Variable in
  jedem Worker auf ``0`` gesetzt – relevant nur, falls ein Worker die App aus
  irgendeinem Grund neu importieren sollte.
- ``post_fork``: ruft ``utils.database.dispose_all_engines()`` auf, damit die
  vom Master geerbten SQLAlchemy-Verbindungen nicht gemeinsam genutzt werden
  (SQLite/psycopg-Connections sind fork-unsicher). Jeder Worker baut danach
  seinen eigenen Pool auf.

Umgebungsvariablen (jeweils mit sinnvollem Default):
- ``GUNICORN_BIND``      (Default ``0.0.0.0:5000``)
- ``GUNICORN_WORKERS``   (Default ``2``; empfohlen 2-4 bei SQLite+WAL)
- ``GUNICORN_THREADS``   (Default ``4``)
- ``GUNICORN_TIMEOUT``   (Default ``120``; LibreOffice-Konvertierung kann dauern)
- ``GUNICORN_LOGLEVEL``  (Default ``info``)
"""

from __future__ import annotations

import os

# Muss VOR dem Import von app:app gesetzt werden. Gunicorn laedt diese Config-
# Datei vor dem Master-Import der WSGI-App (preload_app=True).
os.environ.setdefault('BIS_RUN_STARTUP_TASKS', '1')


bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5000')
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gthread'
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
graceful_timeout = int(os.environ.get('GUNICORN_GRACEFUL_TIMEOUT', '30'))
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))
preload_app = True
proc_name = 'bis-app'

accesslog = os.environ.get('GUNICORN_ACCESSLOG', '-')
errorlog = os.environ.get('GUNICORN_ERRORLOG', '-')
loglevel = os.environ.get('GUNICORN_LOGLEVEL', 'info')


def post_fork(server, worker):
    """Nach fork(): Engine-Pool im Worker frisch aufbauen."""
    os.environ['BIS_RUN_STARTUP_TASKS'] = '0'
    try:
        from utils.database import dispose_all_engines
        dispose_all_engines()
    except Exception as exc:
        server.log.warning('post_fork: dispose_all_engines fehlgeschlagen: %s', exc)


def on_starting(server):
    """Einmalig im Master vor dem Spawn der Worker. Nur Info-Log."""
    server.log.info(
        'BIS Gunicorn startet: workers=%s threads=%s preload=%s',
        workers, threads, preload_app,
    )
