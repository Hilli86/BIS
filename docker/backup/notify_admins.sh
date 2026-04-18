#!/bin/bash
# BIS Backup-Service � Admin-Benachrichtigung
# Aufruf:
#   notify_admins.sh success <zusatz_json> <dauer_sek> <plain_size> <encrypted_size>
#   notify_admins.sh failure <zusatz_json> <stage> <exit_code>
#
# Schreibt eine Zeile pro Admin (Berechtigung 'admin', Aktiv=1) in die Tabelle
# Benachrichtigung. Bei 'failure' gilt ein Rate-Limit (6 h pro Empfaenger), um
# wiederholte Cron-Fehlschlaege nicht zu spammen.

set -uo pipefail

DB_FILE="/data/database_main.db"
MODUS="${1:-}"
ZUSATZ_JSON="${2:-{}}"

if [ ! -f "${DB_FILE}" ]; then
    echo "[notify_admins] DB nicht gefunden: ${DB_FILE}" >&2
    exit 2
fi

case "${MODUS}" in
    success)
        TYP="info"
        TITEL="Backup erfolgreich"
        AKTION="backup_success"
        DAUER="${3:-?}"
        PLAIN="${4:-?}"
        ENC="${5:-?}"
        NACHRICHT="Backup abgeschlossen in ${DAUER}s. Plain: ${PLAIN}, verschluesselt: ${ENC}."
        ;;
    failure)
        TYP="system"
        TITEL="Backup fehlgeschlagen"
        AKTION="backup_failure"
        STAGE="${3:-unbekannt}"
        EC="${4:-?}"
        NACHRICHT="Backup ist in Phase '${STAGE}' mit Exit-Code ${EC} abgebrochen. Siehe Container-Log 'bis-backup-service'."
        ;;
    *)
        echo "[notify_admins] Unbekannter Modus: '${MODUS}' (erwartet: success|failure)" >&2
        exit 2
        ;;
esac

# Helper: Single-Quotes fuer SQL verdoppeln
sql_escape() {
    printf "%s" "$1" | sed "s/'/''/g"
}

TITEL_ESC="$(sql_escape "${TITEL}")"
NACHRICHT_ESC="$(sql_escape "${NACHRICHT}")"
AKTION_ESC="$(sql_escape "${AKTION}")"
TYP_ESC="$(sql_escape "${TYP}")"
ZUSATZ_ESC="$(sql_escape "${ZUSATZ_JSON}")"

# Empfaenger ermitteln: aktive Mitarbeiter mit Berechtigung 'admin'
EMPFAENGER=$(sqlite3 "${DB_FILE}" "
    SELECT DISTINCT M.ID
    FROM Mitarbeiter M
    JOIN MitarbeiterBerechtigung MB ON M.ID = MB.MitarbeiterID
    JOIN Berechtigung B ON MB.BerechtigungID = B.ID
    WHERE M.Aktiv = 1
      AND B.Schluessel = 'admin'
      AND B.Aktiv = 1;
" 2>/dev/null) || {
    echo "[notify_admins] SQL-Fehler beim Ermitteln der Admins." >&2
    exit 3
}

if [ -z "${EMPFAENGER}" ]; then
    echo "[notify_admins] Keine Admin-Empfaenger gefunden - ueberspringe."
    exit 0
fi

INSERTS=0
SKIPPED=0
for MID in ${EMPFAENGER}; do
    # Rate-Limit nur bei failure: 1 Benachrichtigung pro Admin in 6 h
    if [ "${MODUS}" = "failure" ]; then
        RECENT=$(sqlite3 "${DB_FILE}" "
            SELECT COUNT(*) FROM Benachrichtigung
            WHERE MitarbeiterID = ${MID}
              AND Modul = 'backup'
              AND Aktion = 'backup_failure'
              AND ErstelltAm >= datetime('now', '-6 hours');
        " 2>/dev/null || echo "0")
        if [ "${RECENT}" != "0" ]; then
            SKIPPED=$((SKIPPED + 1))
            continue
        fi
    fi

    sqlite3 "${DB_FILE}" "
        INSERT INTO Benachrichtigung
            (MitarbeiterID, ThemaID, BemerkungID, Typ, Titel, Nachricht,
             Modul, Aktion, AbteilungID, Zusatzdaten)
        VALUES
            (${MID}, 0, NULL, '${TYP_ESC}', '${TITEL_ESC}', '${NACHRICHT_ESC}',
             'backup', '${AKTION_ESC}', NULL, '${ZUSATZ_ESC}');
    " 2>/dev/null && INSERTS=$((INSERTS + 1)) || {
        echo "[notify_admins] INSERT fehlgeschlagen fuer MitarbeiterID=${MID}" >&2
    }
done

echo "[notify_admins] Modus=${MODUS} eingefuegt=${INSERTS} rate_limited=${SKIPPED}"
exit 0
