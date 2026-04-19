# BIS � Betriebsinformationssystem
# Docker-Image fuer Linux-Container (z. B. unter Docker Desktop auf Windows 11)
# Build-Kontext: Projektroot (docker-compose: context: .)

FROM python:3.11-slim-bookworm

# LibreOffice fuer DOCX->PDF-Konvertierung (Berichte) und curl fuer HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-common \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Persistente Datenordner. Rechte auf den nicht-root Benutzer setzen.
RUN groupadd --system --gid 1001 bis \
    && useradd --system --uid 1001 --gid bis --home /app --shell /usr/sbin/nologin bis \
    && mkdir -p /data \
    && chown -R bis:bis /app /data

USER bis

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:5000/health || exit 1

# Gunicorn: 0.0.0.0 damit von aussen erreichbar.
# Nur 1 Worker, dafuer mehrere Threads: SQLite-Backend (Schema-Init/Migration in app.py)
# und In-Memory-Rate-Limiter (utils/rate_limit.py) vertragen keinen Multi-Worker-Betrieb.
# Parallele Requests werden ueber Threads bedient (App ist I/O-/Subprocess-bound).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "app:app"]
