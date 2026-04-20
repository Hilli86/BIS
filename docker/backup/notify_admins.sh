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

# DB-Typ anhand DATABASE_URL bestimmen (gleiche Logik wie bis_backup.sh).
DATABASE_URL="${DATABASE_URL:-}"
case "${DATABASE_URL}" in
    postgres://*|postgresql://*|postgresql+*://*)
        DB_KIND="postgres"
        # SA-URL ("postgresql+psycopg://...") -> libpq-URL ("postgresql://...")
        PGURL="$(printf '%s' "${DATABASE_URL}" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"
        ;;
    *)
        DB_KIND="sqlite"
        ;;
esac

if [ "${DB_KIND}" = "sqlite" ] && [ ! -f "${DB_FILE}" ]; then
    echo "[notify_admins] DB nicht gefunden: ${DB_FILE}" >&2
    exit 2
fi

# Wrapper: fuehrt ein SQL-Statement gegen den aktuellen Backend-Typ aus.
# $1 = SQL, stdout = Ergebniszeilen ohne Kopf/Rahmen.
db_query() {
    local sql="$1"
    if [ "${DB_KIND}" = "sqlite" ]; then
        sqlite3 "${DB_FILE}" "${sql}"
    else
        # -A: ungepaddet, -t: nur Tupel, -X: kein .psqlrc, -q: still
        psql -Aqt -X -v ON_ERROR_STOP=1 "${PGURL}" -c "${sql}"
    fi
}

db_exec() {
    local sql="$1"
    if [ "${DB_KIND}" = "sqlite" ]; then
        sqlite3 "${DB_FILE}" "${sql}"
    else
        psql -Aqt -X -v ON_ERROR_STOP=1 "${PGURL}" -c "${sql}"
    fi
}

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

# SQL-Zeitfilter fuer "ErstelltAm >= jetzt - 6h" dialektabhaengig.
if [ "${DB_KIND}" = "sqlite" ]; then
    TIME_FILTER_6H="datetime('now', '-6 hours')"
    TABLE_MA='Mitarbeiter'
    TABLE_MB='MitarbeiterBerechtigung'
    TABLE_B='Berechtigung'
    TABLE_N='Benachrichtigung'
else
    TIME_FILTER_6H="(CURRENT_TIMESTAMP - INTERVAL '6 hours')"
    # Postgres: Identifier mit gemischter Schreibweise muessen gequotet werden.
    TABLE_MA='"Mitarbeiter"'
    TABLE_MB='"MitarbeiterBerechtigung"'
    TABLE_B='"Berechtigung"'
    TABLE_N='"Benachrichtigung"'
fi

# Empfaenger ermitteln: aktive Mitarbeiter mit Berechtigung 'admin'
if [ "${DB_KIND}" = "sqlite" ]; then
    EMPFAENGER=$(db_query "
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
else
    EMPFAENGER=$(db_query "
        SELECT DISTINCT M.\"ID\"
        FROM ${TABLE_MA} M
        JOIN ${TABLE_MB} MB ON M.\"ID\" = MB.\"MitarbeiterID\"
        JOIN ${TABLE_B} B ON MB.\"BerechtigungID\" = B.\"ID\"
        WHERE M.\"Aktiv\" = 1
          AND B.\"Schluessel\" = 'admin'
          AND B.\"Aktiv\" = 1;
    " 2>/dev/null) || {
        echo "[notify_admins] SQL-Fehler beim Ermitteln der Admins." >&2
        exit 3
    }
fi

if [ -z "${EMPFAENGER}" ]; then
    echo "[notify_admins] Keine Admin-Empfaenger gefunden - ueberspringe."
    exit 0
fi

INSERTS=0
SKIPPED=0
for MID in ${EMPFAENGER}; do
    # Rate-Limit nur bei failure: 1 Benachrichtigung pro Admin in 6 h
    if [ "${MODUS}" = "failure" ]; then
        if [ "${DB_KIND}" = "sqlite" ]; then
            RECENT=$(db_query "
                SELECT COUNT(*) FROM Benachrichtigung
                WHERE MitarbeiterID = ${MID}
                  AND Modul = 'backup'
                  AND Aktion = 'backup_failure'
                  AND ErstelltAm >= ${TIME_FILTER_6H};
            " 2>/dev/null || echo "0")
        else
            RECENT=$(db_query "
                SELECT COUNT(*) FROM ${TABLE_N}
                WHERE \"MitarbeiterID\" = ${MID}
                  AND \"Modul\" = 'backup'
                  AND \"Aktion\" = 'backup_failure'
                  AND \"ErstelltAm\" >= ${TIME_FILTER_6H};
            " 2>/dev/null || echo "0")
        fi
        # psql liefert ggf. Whitespace - trimmen.
        RECENT="$(printf '%s' "${RECENT}" | tr -d '[:space:]')"
        if [ "${RECENT}" != "0" ]; then
            SKIPPED=$((SKIPPED + 1))
            continue
        fi
    fi

    if [ "${DB_KIND}" = "sqlite" ]; then
        db_exec "
            INSERT INTO Benachrichtigung
                (MitarbeiterID, ThemaID, BemerkungID, Typ, Titel, Nachricht,
                 Modul, Aktion, AbteilungID, Zusatzdaten)
            VALUES
                (${MID}, 0, NULL, '${TYP_ESC}', '${TITEL_ESC}', '${NACHRICHT_ESC}',
                 'backup', '${AKTION_ESC}', NULL, '${ZUSATZ_ESC}');
        " >/dev/null 2>&1 && INSERTS=$((INSERTS + 1)) || {
            echo "[notify_admins] INSERT fehlgeschlagen fuer MitarbeiterID=${MID}" >&2
        }
    else
        db_exec "
            INSERT INTO ${TABLE_N}
                (\"MitarbeiterID\", \"ThemaID\", \"BemerkungID\", \"Typ\", \"Titel\", \"Nachricht\",
                 \"Modul\", \"Aktion\", \"AbteilungID\", \"Zusatzdaten\")
            VALUES
                (${MID}, 0, NULL, '${TYP_ESC}', '${TITEL_ESC}', '${NACHRICHT_ESC}',
                 'backup', '${AKTION_ESC}', NULL, '${ZUSATZ_ESC}');
        " >/dev/null 2>&1 && INSERTS=$((INSERTS + 1)) || {
            echo "[notify_admins] INSERT fehlgeschlagen fuer MitarbeiterID=${MID}" >&2
        }
    fi
done

echo "[notify_admins] Modus=${MODUS} eingefuegt=${INSERTS} rate_limited=${SKIPPED}"
exit 0
