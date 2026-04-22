# BIS - Betriebsinformationssystem
# Docker-Image fuer Linux-Container (z. B. unter Docker Desktop auf Windows 11)
# Build-Kontext: Projektroot (docker-compose: context: .)

FROM python:3.11-slim-bookworm

# LibreOffice fuer DOCX->PDF-Konvertierung (Berichte), curl fuer HEALTHCHECK
# und gosu, um im Entrypoint nach dem chown auf den nicht-root Benutzer
# "bis" zu droppen (privilege drop ohne setuid-Root-Skripte).
# tzdata liefert die Zoneinfo-Daten (fehlen im slim-Image); /etc/localtime
# wird zusaetzlich auf Europe/Berlin verlinkt, damit Subprozesse (z. B.
# LibreOffice) und Tools ohne TZ-Env die korrekte Lokalzeit erhalten.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-common \
    curl \
    gosu \
    tzdata \
    && ln -sf /usr/share/zoneinfo/Europe/Berlin /etc/localtime \
    && echo "Europe/Berlin" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Nicht-root Benutzer und persistentes Datenverzeichnis vorbereiten.
# Hinweis: Das chown auf /data gilt nur fuer das Image; ein Bind-Mount
# (z. B. C:\BIS-Daten:/data) ueberlagert diese Rechte zur Laufzeit. Der
# Entrypoint korrigiert das vor dem User-Switch erneut.
RUN groupadd --system --gid 1001 bis \
    && useradd --system --uid 1001 --gid bis --home /app --shell /usr/sbin/nologin bis \
    && mkdir -p /data \
    && chown -R bis:bis /app /data

# Entrypoint installieren. sed -i entfernt CRLF-Line-Endings, falls das Skript
# unter Windows mit CRLF gespeichert wurde - sonst findet Linux den Shebang nicht.
COPY docker/bis-entrypoint.sh /usr/local/bin/bis-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/bis-entrypoint.sh \
    && chmod +x /usr/local/bin/bis-entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:5000/health || exit 1

# Der Entrypoint startet als root, macht /data fuer den bis-Benutzer
# schreibbar und fuehrt dann per gosu das eigentliche Kommando als bis aus.
#
# Gunicorn-Konfiguration liegt in /app/gunicorn_config.py (preload_app=True,
# Workers/Threads aus ENV). Multi-Worker ist unterstuetzt, weil:
#   - Startup-Tasks (Alembic, Cleanup, Nachversand) laufen nur im Master
#     (siehe app.run_startup_tasks + BIS_RUN_STARTUP_TASKS in gunicorn_config.py)
#   - SQLite ist per WAL + busy_timeout fork-sicher (utils/database.py)
#   - Rate-Limiter liest RATELIMIT_STORAGE_URI aus der App-Config (Redis im
#     Compose-Setup, siehe docker-compose.yml)
# Worker-Zahl und Threads per ENV steuerbar (GUNICORN_WORKERS, GUNICORN_THREADS).
ENTRYPOINT ["/usr/local/bin/bis-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
