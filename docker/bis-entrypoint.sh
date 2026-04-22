#!/bin/sh
# BIS - Application-Service Entrypoint
#
# Stellt sicher, dass das gemountete Datenvolumen (/data) dem nicht-root
# Benutzer "bis" gehoert. Noetig, weil Bind-Mounts (Host-Pfad aus BIS_DATA_HOST -> :/data
# unter Docker Desktop/WSL2) das im Dockerfile gesetzte Ownership zur Laufzeit
# wieder mit Host-Rechten (typischerweise root:root) ueberlagern und der
# Anwendungsbenutzer dann im Volume keine Unterordner anlegen kann
# ("Fehler beim Erstellen des Zielordners" beim Datei-Upload).
#
# Der Container startet deshalb als root, korrigiert die Rechte am Volume
# und wechselt dann per gosu dauerhaft auf UID/GID 1001 (bis:bis), bevor
# das eigentliche Kommando (Gunicorn) ausgefuehrt wird.

set -eu

DATA_DIR="/data"
APP_USER="bis"
APP_GROUP="bis"

if [ -d "$DATA_DIR" ]; then
    # Idempotent: laeuft bei jedem Start, ist aber billig, weil chown nur
    # Inodes anfasst, deren Owner abweicht.
    chown -R "${APP_USER}:${APP_GROUP}" "$DATA_DIR" 2>/dev/null || \
        echo "Warnung: chown auf $DATA_DIR fehlgeschlagen (weiter im Betrieb)." >&2
fi

exec gosu "${APP_USER}:${APP_GROUP}" "$@"
