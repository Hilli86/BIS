# BIS – Betriebsinformationssystem
# Docker-Image für Linux-Container (z. B. unter Docker Desktop auf Windows 11)

FROM python:3.11-slim-bookworm

# LibreOffice für DOCX→PDF-Konvertierung (Berichte)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-common \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

# Gunicorn: 0.0.0.0 damit von außen erreichbar
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "app:app"]
