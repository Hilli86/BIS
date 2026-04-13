"""Business-Logik Wartungen."""

import calendar
from datetime import date, datetime, timedelta

from utils.abteilungen import (
    get_mitarbeiter_abteilungen,
    get_sichtbare_abteilungen_fuer_mitarbeiter,
)

INTERVALL_EINHEITEN = ('Tag', 'Woche', 'Monat')


def _add_months(d: date, months: int) -> date:
    """Addiert Monate; Tag wird auf den letzten Tag des Zielmonats begrenzt."""
    y, m = d.year, d.month + months
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def berechne_naechste_faelligkeit_nach_basis(basis_datum: date, einheit: str, anzahl) -> date:
    """Nächstes Fälligkeitsdatum = Basis-Kalendertag + Plan-Intervall (Durchführung oder Soll)."""
    if basis_datum is None:
        raise ValueError('Basisdatum fehlt.')
    if einheit not in INTERVALL_EINHEITEN:
        raise ValueError('Ungültige Intervall-Einheit.')
    try:
        n = int(anzahl)
    except (TypeError, ValueError):
        raise ValueError('Intervall-Anzahl ungültig.') from None
    if n < 1:
        raise ValueError('Intervall-Anzahl muss mindestens 1 sein.')
    if einheit == 'Tag':
        return basis_datum + timedelta(days=n)
    if einheit == 'Woche':
        return basis_datum + timedelta(weeks=n)
    return _add_months(basis_datum, n)


def _datum_aus_durchgefuehrt_am(durchgefuehrt_am):
    """Kalendertag aus datetime, date oder ISO-ähnlichem String (erste 10 Zeichen YYYY-MM-DD)."""
    if durchgefuehrt_am is None:
        return None
    if isinstance(durchgefuehrt_am, datetime):
        return durchgefuehrt_am.date()
    if isinstance(durchgefuehrt_am, date):
        return durchgefuehrt_am
    s = str(durchgefuehrt_am).strip()
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    return None


def _datum_aus_naechste_faelligkeit_feld(wert):
    """Kalendertag aus DB-Feld NaechsteFaelligkeit (meist YYYY-MM-DD)."""
    if wert is None:
        return None
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    s = str(wert).strip()
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    return None


def naechste_faelligkeit_stufe(value):
    """
    Nächste Fälligkeit (Datum) → Kennzeichnungsstufe wie in Tabellen/Badges.
    0 neutral, 1 innerhalb der nächsten 7 Tage, 2 heute bis 7 Tage überfällig,
    3 mehr als 7 Tage überfällig.
    """
    if not value:
        return 0
    s = str(value).strip()[:10]
    try:
        d = datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return 0
    today = date.today()
    if d > today + timedelta(days=7):
        return 0
    if d > today:
        return 1
    if d >= today - timedelta(days=7):
        return 2
    return 3


def aktualisiere_naechste_faelligkeit_nach_durchfuehrung(conn, plan_id, durchgefuehrt_am):
    """Setzt NaechsteFaelligkeit aus Basisdatum + Intervall; nur bei aktivem Plan.
    Bei HatFestesIntervall: Basis = bisherige NaechsteFaelligkeit, sonst Durchführungstag (Fallback wie im Plan).
    Gibt das neue Datum als YYYY-MM-DD zurück, sonst None."""
    plan = get_plan(conn, plan_id)
    if not plan or not plan['Aktiv']:
        return None
    try:
        if int(plan['IntervallAnzahl']) == 0:
            return None
    except (TypeError, ValueError, KeyError, IndexError):
        pass
    df_basis = _datum_aus_durchgefuehrt_am(durchgefuehrt_am)
    if df_basis is None:
        return None
    try:
        hat_fest = bool(plan['HatFestesIntervall'])
    except (KeyError, IndexError):
        hat_fest = False
    if hat_fest:
        soll_basis = _datum_aus_naechste_faelligkeit_feld(plan['NaechsteFaelligkeit'])
        basis = soll_basis if soll_basis is not None else df_basis
    else:
        basis = df_basis
    einheit = plan['IntervallEinheit']
    try:
        neu = berechne_naechste_faelligkeit_nach_basis(basis, einheit, plan['IntervallAnzahl'])
    except ValueError:
        return None
    neu_str = neu.isoformat()
    conn.execute(
        '''UPDATE Wartungsplan SET NaechsteFaelligkeit = ?
           WHERE ID = ? AND Aktiv = 1''',
        (neu_str, plan_id),
    )
    return neu_str


def list_wartungen(conn, mitarbeiter_id, is_admin, bereich_id=None, gewerk_id=None):
    """Nicht-Admin: Wartung sichtbar bei ErstelltVon oder Zuordnung zu einer der direkten Mitarbeiter-Abteilungen
    (Primär + MitarbeiterAbteilung), nicht über rekursive Unterabteilungen."""
    extra = []
    params_tail = []
    if bereich_id is not None:
        extra.append('AND b.ID = ?')
        params_tail.append(bereich_id)
    if gewerk_id is not None:
        extra.append('AND g.ID = ?')
        params_tail.append(gewerk_id)

    if is_admin:
        sql_admin = f'''
            SELECT w.ID, w.Bezeichnung, w.Aktiv, w.ErstelltAm,
                   g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
            FROM Wartung w
            JOIN Gewerke g ON w.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            {"WHERE 1=1 " + " ".join(extra) if extra else ""}
            ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung
        '''
        return conn.execute(sql_admin, params_tail).fetchall()

    abt_ids = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not abt_ids:
        return []
    ph = ','.join(['?'] * len(abt_ids))
    base_params = [mitarbeiter_id] + abt_ids
    sql_user = f'''
        SELECT DISTINCT w.ID, w.Bezeichnung, w.Aktiv, w.ErstelltAm,
               g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
        FROM Wartung w
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        {" ".join(extra)}
        ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung
    '''
    return conn.execute(sql_user, base_params + params_tail).fetchall()


def _wartung_sichtbar_params(mitarbeiter_id, abteilung_ids):
    """Parameterliste für Nicht-Admin: ErstelltVon + direkte Mitarbeiter-Abteilungen (ohne Unterbaum)."""
    return [mitarbeiter_id] + abteilung_ids


def list_bereiche_fuer_wartungen_sichtbar(conn, mitarbeiter_id, is_admin):
    """Bereiche, in denen der Nutzer mindestens eine sichtbare Wartung hat."""
    if is_admin:
        return conn.execute('''
            SELECT DISTINCT b.ID, b.Bezeichnung
            FROM Bereich b
            JOIN Gewerke g ON g.BereichID = b.ID
            JOIN Wartung w ON w.GewerkID = g.ID
            ORDER BY b.Bezeichnung
        ''').fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT DISTINCT b.ID, b.Bezeichnung
        FROM Bereich b
        JOIN Gewerke g ON g.BereichID = b.ID
        JOIN Wartung w ON w.GewerkID = g.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY b.Bezeichnung
    ''', _wartung_sichtbar_params(mitarbeiter_id, sichtbare)).fetchall()


def list_gewerke_fuer_bereich_sichtbar(conn, bereich_id, mitarbeiter_id, is_admin):
    """Gewerke im Bereich mit mindestens einer sichtbaren Wartung."""
    if is_admin:
        return conn.execute('''
            SELECT DISTINCT g.ID, g.Bezeichnung
            FROM Gewerke g
            JOIN Wartung w ON w.GewerkID = g.ID
            WHERE g.BereichID = ?
            ORDER BY g.Bezeichnung
        ''', (bereich_id,)).fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT DISTINCT g.ID, g.Bezeichnung
        FROM Gewerke g
        JOIN Wartung w ON w.GewerkID = g.ID
        WHERE g.BereichID = ?
          AND w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY g.Bezeichnung
    ''', (bereich_id,) + tuple(_wartung_sichtbar_params(mitarbeiter_id, sichtbare))).fetchall()


def list_gewerke_fuer_wartung_liste_filter(conn, mitarbeiter_id, is_admin, bereich_id=None):
    """Gewerke für das Filter-Dropdown: gefiltert nach Bereich oder alle mit sichtbarer Wartung."""
    if bereich_id is not None:
        return list_gewerke_fuer_bereich_sichtbar(conn, bereich_id, mitarbeiter_id, is_admin)
    if is_admin:
        return conn.execute('''
            SELECT DISTINCT g.ID, g.Bezeichnung, b.Bezeichnung AS BereichLabel
            FROM Gewerke g
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Wartung w ON w.GewerkID = g.ID
            ORDER BY b.Bezeichnung, g.Bezeichnung
        ''').fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT DISTINCT g.ID, g.Bezeichnung, b.Bezeichnung AS BereichLabel
        FROM Gewerke g
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Wartung w ON w.GewerkID = g.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY b.Bezeichnung, g.Bezeichnung
    ''', _wartung_sichtbar_params(mitarbeiter_id, sichtbare)).fetchall()


def list_wartungen_fuer_gewerk_sichtbar(conn, gewerk_id, mitarbeiter_id, is_admin):
    """Sichtbare Wartungen eines Gewerks (Sortierung nach Bezeichnung)."""
    if is_admin:
        return conn.execute('''
            SELECT w.ID, w.Bezeichnung, w.Aktiv
            FROM Wartung w
            WHERE w.GewerkID = ?
            ORDER BY w.Bezeichnung
        ''', (gewerk_id,)).fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT w.ID, w.Bezeichnung, w.Aktiv
        FROM Wartung w
        WHERE w.GewerkID = ?
          AND w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY w.Bezeichnung
    ''', (gewerk_id,) + tuple(_wartung_sichtbar_params(mitarbeiter_id, sichtbare))).fetchall()


def list_durchfuehrungen_fuer_gewerk_jahr(conn, gewerk_id, jahr, mitarbeiter_id, is_admin):
    """
    Alle Wartungsdurchführungen im Gewerk für ein Kalenderjahr (sichtbare Wartungen).
    Monat 1–12 als Integer-Spalte Monat.
    """
    jahr_str = str(int(jahr))
    if is_admin:
        return conn.execute('''
            SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung,
                   w.ID AS WartungID, w.Bezeichnung AS WartungBez,
                   p.ID AS PlanID, p.IntervallEinheit, p.IntervallAnzahl,
                   CAST(strftime('%m', d.DurchgefuehrtAm) AS INTEGER) AS Monat
            FROM Wartungsdurchfuehrung d
            JOIN Wartungsplan p ON d.WartungsplanID = p.ID
            JOIN Wartung w ON p.WartungID = w.ID
            JOIN Gewerke g ON w.GewerkID = g.ID
            WHERE g.ID = ? AND strftime('%Y', d.DurchgefuehrtAm) = ?
            ORDER BY w.Bezeichnung, d.DurchgefuehrtAm, d.ID
        ''', (gewerk_id, jahr_str)).fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung,
               w.ID AS WartungID, w.Bezeichnung AS WartungBez,
               p.ID AS PlanID, p.IntervallEinheit, p.IntervallAnzahl,
               CAST(strftime('%m', d.DurchgefuehrtAm) AS INTEGER) AS Monat
        FROM Wartungsdurchfuehrung d
        JOIN Wartungsplan p ON d.WartungsplanID = p.ID
        JOIN Wartung w ON p.WartungID = w.ID
        JOIN Gewerke g ON w.GewerkID = g.ID
        WHERE g.ID = ? AND strftime('%Y', d.DurchgefuehrtAm) = ?
          AND w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY w.Bezeichnung, d.DurchgefuehrtAm, d.ID
    ''', (gewerk_id, jahr_str) + tuple(_wartung_sichtbar_params(mitarbeiter_id, sichtbare))).fetchall()


def list_wartungen_jahresuebersicht(conn, mitarbeiter_id, is_admin, bereich_id=None, gewerk_id=None):
    """Sichtbare Wartungen für Matrix, optional nach Bereich/Gewerk; Sortierung für Gruppierung."""
    extra = []
    params_tail = []
    if bereich_id is not None:
        extra.append('AND b.ID = ?')
        params_tail.append(bereich_id)
    if gewerk_id is not None:
        extra.append('AND g.ID = ?')
        params_tail.append(gewerk_id)
    extra_sql = ' ' + ' '.join(extra) if extra else ''

    if is_admin:
        return conn.execute(f'''
            SELECT w.ID, w.Bezeichnung, w.Aktiv, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
            FROM Wartung w
            JOIN Gewerke g ON w.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            WHERE 1=1{extra_sql}
            ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung
        ''', params_tail).fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT w.ID, w.Bezeichnung, w.Aktiv, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
        FROM Wartung w
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        ){extra_sql}
        ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung
    ''', [mitarbeiter_id] + sichtbare + params_tail).fetchall()


def list_durchfuehrungen_jahresuebersicht(
    conn, jahr, mitarbeiter_id, is_admin, bereich_id=None, gewerk_id=None,
):
    """Durchführungen eines Jahres, gefiltert wie die Wartungsmatrix (Bereich/Gewerk optional)."""
    jahr_str = str(int(jahr))
    extra = []
    params_tail = []
    if bereich_id is not None:
        extra.append('AND b.ID = ?')
        params_tail.append(bereich_id)
    if gewerk_id is not None:
        extra.append('AND g.ID = ?')
        params_tail.append(gewerk_id)
    extra_sql = ' ' + ' '.join(extra) if extra else ''

    if is_admin:
        return conn.execute(f'''
            SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung,
                   w.ID AS WartungID, w.Bezeichnung AS WartungBez,
                   p.ID AS PlanID, p.IntervallEinheit, p.IntervallAnzahl,
                   CAST(strftime('%m', d.DurchgefuehrtAm) AS INTEGER) AS Monat
            FROM Wartungsdurchfuehrung d
            JOIN Wartungsplan p ON d.WartungsplanID = p.ID
            JOIN Wartung w ON p.WartungID = w.ID
            JOIN Gewerke g ON w.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            WHERE strftime('%Y', d.DurchgefuehrtAm) = ?{extra_sql}
            ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung, d.DurchgefuehrtAm, d.ID
        ''', (jahr_str,) + tuple(params_tail)).fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung,
               w.ID AS WartungID, w.Bezeichnung AS WartungBez,
               p.ID AS PlanID, p.IntervallEinheit, p.IntervallAnzahl,
               CAST(strftime('%m', d.DurchgefuehrtAm) AS INTEGER) AS Monat
        FROM Wartungsdurchfuehrung d
        JOIN Wartungsplan p ON d.WartungsplanID = p.ID
        JOIN Wartung w ON p.WartungID = w.ID
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE strftime('%Y', d.DurchgefuehrtAm) = ?{extra_sql}
          AND w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
          )
        ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung, d.DurchgefuehrtAm, d.ID
    ''', (jahr_str,) + tuple(params_tail) + tuple(_wartung_sichtbar_params(mitarbeiter_id, sichtbare))).fetchall()


_CHRONO_SORT_SQL_COL = {
    'id': 'd.ID',
    'datum': 'd.DurchgefuehrtAm',
}
_CHRONO_SORT_SQL_DIR = {
    'asc': 'ASC',
    'desc': 'DESC',
}


def list_durchfuehrungen_chronologisch_sichtbar(
    conn,
    mitarbeiter_id,
    is_admin,
    bereich_id=None,
    gewerk_id=None,
    wartung_id=None,
    datum_von=None,
    datum_bis=None,
    limit=5000,
    sort_by='id',
    sort_dir='desc',
):
    """
    Alle protokollierten Durchführungen für den Nutzer sichtbarer Wartungen.
    sort_by: 'id' | 'datum' (DurchgefuehrtAm), sort_dir: 'asc' | 'desc'.
    datum_von / datum_bis: 'YYYY-MM-DD' oder None.
    """
    col = _CHRONO_SORT_SQL_COL.get((sort_by or '').strip().lower(), _CHRONO_SORT_SQL_COL['id'])
    direc = _CHRONO_SORT_SQL_DIR.get((sort_dir or '').strip().lower(), 'DESC')
    tie = f', d.ID {direc}' if col == _CHRONO_SORT_SQL_COL['datum'] else ''
    order_clause = f' ORDER BY {col} {direc}{tie} LIMIT ?'
    extra = []
    params = []
    if bereich_id is not None:
        extra.append('AND b.ID = ?')
        params.append(bereich_id)
    if gewerk_id is not None:
        extra.append('AND g.ID = ?')
        params.append(gewerk_id)
    if wartung_id is not None:
        extra.append('AND w.ID = ?')
        params.append(wartung_id)
    if datum_von:
        extra.append('AND date(d.DurchgefuehrtAm) >= date(?)')
        params.append(str(datum_von)[:10])
    if datum_bis:
        extra.append('AND date(d.DurchgefuehrtAm) <= date(?)')
        params.append(str(datum_bis)[:10])
    extra_sql = ' ' + ' '.join(extra) if extra else ''

    base_sql = f'''
        SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung,
               w.ID AS WartungID, w.Bezeichnung AS WartungBez,
               p.IntervallAnzahl, p.IntervallEinheit,
               g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich,
               m.Vorname || ' ' || m.Nachname AS ProtokolliertVon,
               (SELECT COUNT(*) FROM Datei dt
                WHERE dt.BereichTyp = 'Wartungsdurchfuehrung' AND dt.BereichID = d.ID) AS DateiAnzahl
        FROM Wartungsdurchfuehrung d
        JOIN Wartungsplan p ON d.WartungsplanID = p.ID
        JOIN Wartung w ON p.WartungID = w.ID
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        LEFT JOIN Mitarbeiter m ON d.ProtokolliertVonID = m.ID
        WHERE 1=1{extra_sql}
    '''

    if is_admin:
        sql = base_sql + order_clause
        return conn.execute(sql, params + [limit]).fetchall()

    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    vis = f'''
        AND w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
    '''
    sql = base_sql + vis + order_clause
    all_params = params + _wartung_sichtbar_params(mitarbeiter_id, sichtbare) + [limit]
    return conn.execute(sql, all_params).fetchall()


def get_wartung(conn, wartung_id):
    return conn.execute('''
        SELECT w.*, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich, b.ID AS BereichID
        FROM Wartung w
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE w.ID = ?
    ''', (wartung_id,)).fetchone()


def get_wartung_abteilungen(conn, wartung_id):
    return conn.execute('''
        SELECT a.ID, a.Bezeichnung
        FROM WartungAbteilungZugriff z
        JOIN Abteilung a ON z.AbteilungID = a.ID
        WHERE z.WartungID = ? AND a.Aktiv = 1
        ORDER BY a.Sortierung, a.Bezeichnung
    ''', (wartung_id,)).fetchall()


def set_wartung_abteilungen(conn, wartung_id, abteilung_ids):
    conn.execute('DELETE FROM WartungAbteilungZugriff WHERE WartungID = ?', (wartung_id,))
    for aid in abteilung_ids:
        try:
            aid = int(aid)
            conn.execute(
                'INSERT INTO WartungAbteilungZugriff (WartungID, AbteilungID) VALUES (?, ?)',
                (wartung_id, aid),
            )
        except (TypeError, ValueError):
            continue


def create_wartung(conn, gewerk_id, bezeichnung, beschreibung, mitarbeiter_id, abteilung_ids):
    cur = conn.execute(
        '''INSERT INTO Wartung (GewerkID, Bezeichnung, Beschreibung, ErstelltVonID)
           VALUES (?, ?, ?, ?)''',
        (gewerk_id, bezeichnung.strip(), (beschreibung or '').strip() or None, mitarbeiter_id),
    )
    wid = cur.lastrowid
    set_wartung_abteilungen(conn, wid, abteilung_ids)
    return wid


def update_wartung(conn, wartung_id, gewerk_id, bezeichnung, beschreibung, aktiv, abteilung_ids):
    conn.execute(
        '''UPDATE Wartung SET GewerkID = ?, Bezeichnung = ?, Beschreibung = ?, Aktiv = ?,
           GeaendertAm = datetime('now', 'localtime')
           WHERE ID = ?''',
        (gewerk_id, bezeichnung.strip(), (beschreibung or '').strip() or None, 1 if aktiv else 0, wartung_id),
    )
    set_wartung_abteilungen(conn, wartung_id, abteilung_ids)


def list_plaene_fuer_wartung(conn, wartung_id):
    return conn.execute('''
        SELECT ID, IntervallEinheit, IntervallAnzahl, NaechsteFaelligkeit, HatFestesIntervall, Aktiv, ErstelltAm
        FROM Wartungsplan
        WHERE WartungID = ?
        ORDER BY Aktiv DESC, ID DESC
    ''', (wartung_id,)).fetchall()


def get_plan(conn, plan_id):
    return conn.execute(
        'SELECT * FROM Wartungsplan WHERE ID = ?',
        (plan_id,),
    ).fetchone()


def create_wartungsplan(conn, wartung_id, einheit, anzahl, naechste, hat_festes_intervall=False):
    if einheit not in INTERVALL_EINHEITEN:
        raise ValueError('Ungültige Intervall-Einheit.')
    try:
        anzahl = int(anzahl)
    except (TypeError, ValueError):
        raise ValueError('Intervall-Anzahl ungültig.') from None
    if anzahl < 0:
        raise ValueError('Intervall-Anzahl darf nicht negativ sein.')
    if anzahl == 0:
        na = None
        hat_festes_intervall = False
    else:
        na = (naechste or '').strip() or None
    cur = conn.execute(
        '''INSERT INTO Wartungsplan
           (WartungID, IntervallEinheit, IntervallAnzahl, NaechsteFaelligkeit, HatFestesIntervall)
           VALUES (?, ?, ?, ?, ?)''',
        (wartung_id, einheit, anzahl, na, 1 if hat_festes_intervall else 0),
    )
    return cur.lastrowid


def update_wartungsplan(conn, plan_id, einheit, anzahl, naechste, aktiv, hat_festes_intervall=False):
    if einheit not in INTERVALL_EINHEITEN:
        raise ValueError('Ungültige Intervall-Einheit.')
    try:
        anzahl = int(anzahl)
    except (TypeError, ValueError):
        raise ValueError('Intervall-Anzahl ungültig.') from None
    if anzahl < 0:
        raise ValueError('Intervall-Anzahl darf nicht negativ sein.')
    if anzahl == 0:
        na = None
        hat_festes_intervall = False
    else:
        na = (naechste or '').strip() or None
    conn.execute(
        '''UPDATE Wartungsplan SET IntervallEinheit = ?, IntervallAnzahl = ?,
           NaechsteFaelligkeit = ?, HatFestesIntervall = ?, Aktiv = ? WHERE ID = ?''',
        (einheit, anzahl, na, 1 if hat_festes_intervall else 0, 1 if aktiv else 0, plan_id),
    )


def list_bereiche_fuer_plaene_sichtbar(conn, mitarbeiter_id, is_admin):
    """Bereiche mit mindestens einem sichtbaren Wartungsplan."""
    if is_admin:
        return conn.execute('''
            SELECT DISTINCT b.ID, b.Bezeichnung
            FROM Bereich b
            JOIN Gewerke g ON g.BereichID = b.ID
            JOIN Wartung w ON w.GewerkID = g.ID
            JOIN Wartungsplan p ON p.WartungID = w.ID
            WHERE w.Aktiv = 1
            ORDER BY b.Bezeichnung
        ''').fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT DISTINCT b.ID, b.Bezeichnung
        FROM Bereich b
        JOIN Gewerke g ON g.BereichID = b.ID
        JOIN Wartung w ON w.GewerkID = g.ID
        JOIN Wartungsplan p ON p.WartungID = w.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY b.Bezeichnung
    ''', _wartung_sichtbar_params(mitarbeiter_id, sichtbare)).fetchall()


def list_gewerke_fuer_plan_liste_filter(conn, mitarbeiter_id, is_admin, bereich_id=None):
    """Gewerke für Planliste-Filter (mit mind. einem Plan auf sichtbarer Wartung)."""
    if bereich_id is not None:
        if is_admin:
            return conn.execute('''
                SELECT DISTINCT g.ID, g.Bezeichnung
                FROM Gewerke g
                JOIN Wartung w ON w.GewerkID = g.ID
                JOIN Wartungsplan p ON p.WartungID = w.ID
                WHERE g.BereichID = ? AND w.Aktiv = 1
                ORDER BY g.Bezeichnung
            ''', (bereich_id,)).fetchall()
        sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
        if not sichtbare:
            return []
        ph = ','.join(['?'] * len(sichtbare))
        return conn.execute(f'''
            SELECT DISTINCT g.ID, g.Bezeichnung
            FROM Gewerke g
            JOIN Wartung w ON w.GewerkID = g.ID
            JOIN Wartungsplan p ON p.WartungID = w.ID
            WHERE g.BereichID = ?
              AND w.Aktiv = 1 AND (
                w.ErstelltVonID = ?
                OR w.ID IN (
                    SELECT WartungID FROM WartungAbteilungZugriff
                    WHERE AbteilungID IN ({ph})
                )
              )
            ORDER BY g.Bezeichnung
        ''', (bereich_id,) + tuple(_wartung_sichtbar_params(mitarbeiter_id, sichtbare))).fetchall()

    if is_admin:
        return conn.execute('''
            SELECT DISTINCT g.ID, g.Bezeichnung, b.Bezeichnung AS BereichLabel
            FROM Gewerke g
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Wartung w ON w.GewerkID = g.ID
            JOIN Wartungsplan p ON p.WartungID = w.ID
            WHERE w.Aktiv = 1
            ORDER BY b.Bezeichnung, g.Bezeichnung
        ''').fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT DISTINCT g.ID, g.Bezeichnung, b.Bezeichnung AS BereichLabel
        FROM Gewerke g
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Wartung w ON w.GewerkID = g.ID
        JOIN Wartungsplan p ON p.WartungID = w.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        )
        ORDER BY b.Bezeichnung, g.Bezeichnung
    ''', _wartung_sichtbar_params(mitarbeiter_id, sichtbare)).fetchall()


def list_plaene_sichtbar(
    conn,
    mitarbeiter_id,
    is_admin,
    bereich_id=None,
    gewerk_id=None,
    sort_mode='stamm',
    sort_dir='asc',
):
    """Alle Pläne, deren Stamm-Wartung der Nutzer sehen darf."""
    extra = []
    params_tail = []
    if bereich_id is not None:
        extra.append('AND b.ID = ?')
        params_tail.append(bereich_id)
    if gewerk_id is not None:
        extra.append('AND g.ID = ?')
        params_tail.append(gewerk_id)
    extra_sql = ' ' + ' '.join(extra) if extra else ''

    sort_mode = (sort_mode or 'stamm').strip().lower()
    sort_dir = (sort_dir or 'asc').strip().lower()
    if sort_mode == 'faelligkeit' and sort_dir == 'desc':
        order_sql = (
            'ORDER BY (p.NaechsteFaelligkeit IS NULL), p.NaechsteFaelligkeit DESC, '
            'b.Bezeichnung, w.Bezeichnung, p.ID'
        )
    elif sort_mode == 'faelligkeit':
        order_sql = (
            'ORDER BY (p.NaechsteFaelligkeit IS NULL), p.NaechsteFaelligkeit ASC, '
            'b.Bezeichnung, w.Bezeichnung, p.ID'
        )
    else:
        order_sql = 'ORDER BY b.Bezeichnung, w.Bezeichnung, p.ID'

    letzte_df_sql = (
        '(SELECT MAX(d.DurchgefuehrtAm) FROM Wartungsdurchfuehrung d '
        'WHERE d.WartungsplanID = p.ID) AS LetzteDurchfuehrung'
    )
    if is_admin:
        return conn.execute(f'''
            SELECT p.ID, p.IntervallEinheit, p.IntervallAnzahl, p.NaechsteFaelligkeit, p.Aktiv,
                   w.ID AS WartungID,
                   w.Bezeichnung AS WartungBez, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich,
                   {letzte_df_sql}
            FROM Wartungsplan p
            JOIN Wartung w ON p.WartungID = w.ID
            JOIN Gewerke g ON w.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            WHERE w.Aktiv = 1{extra_sql}
            {order_sql}
        ''', params_tail).fetchall()
    sichtbare = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT p.ID, p.IntervallEinheit, p.IntervallAnzahl, p.NaechsteFaelligkeit, p.Aktiv,
               w.ID AS WartungID,
               w.Bezeichnung AS WartungBez, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich,
               {letzte_df_sql}
        FROM Wartungsplan p
        JOIN Wartung w ON p.WartungID = w.ID
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE w.Aktiv = 1 AND (
            w.ErstelltVonID = ?
            OR w.ID IN (
                SELECT WartungID FROM WartungAbteilungZugriff
                WHERE AbteilungID IN ({ph})
            )
        ){extra_sql}
        {order_sql}
    ''', [mitarbeiter_id] + sichtbare + params_tail).fetchall()


def map_wartung_zu_aktiven_plan_ids(conn, wartung_ids, mitarbeiter_id, is_admin, bereich_id=None, gewerk_id=None):
    """Pro Wartungs-ID: sortierte IDs aktiver Pläne (gleiche Sichtbarkeit wie list_plaene_sichtbar)."""
    if not wartung_ids:
        return {}
    rows = list_plaene_sichtbar(
        conn, mitarbeiter_id, is_admin, bereich_id=bereich_id, gewerk_id=gewerk_id,
    )
    out = {int(wid): [] for wid in wartung_ids}
    for r in rows:
        if not r['Aktiv']:
            continue
        wid = r['WartungID']
        if wid in out:
            out[wid].append(r['ID'])
    return out


def map_wartung_aktive_plaene_metadaten(
    conn, wartung_ids, mitarbeiter_id, is_admin, bereich_id=None, gewerk_id=None,
):
    """
    Pro Wartung: Liste aktiver Pläne mit Intervall und NaechsteFaelligkeit,
    sortiert nach Fälligkeit (ohne Datum zuletzt).
    """
    if not wartung_ids:
        return {}
    wid_set = {int(w) for w in wartung_ids}
    rows = list_plaene_sichtbar(
        conn, mitarbeiter_id, is_admin, bereich_id=bereich_id, gewerk_id=gewerk_id,
    )
    out = {w: [] for w in wid_set}
    for r in rows:
        if not r['Aktiv']:
            continue
        wid = r['WartungID']
        if wid not in wid_set:
            continue
        out[wid].append({
            'PlanID': r['ID'],
            'IntervallAnzahl': r['IntervallAnzahl'],
            'IntervallEinheit': r['IntervallEinheit'],
            'NaechsteFaelligkeit': r['NaechsteFaelligkeit'],
        })
    for lst in out.values():
        lst.sort(key=lambda x: (x['NaechsteFaelligkeit'] is None, x['NaechsteFaelligkeit'] or ''))
    return out


def plaene_options_fuer_select(conn, mitarbeiter_id, is_admin):
    rows = list_plaene_sichtbar(conn, mitarbeiter_id, is_admin)
    out = []
    for r in rows:
        if not r['Aktiv']:
            continue
        try:
            ia = int(r['IntervallAnzahl'])
        except (TypeError, ValueError):
            ia = 1
        if ia == 0:
            intervall_txt = 'ohne Intervall'
        else:
            intervall_txt = f"alle {ia} {r['IntervallEinheit']}(e)"
        out.append({
            'id': r['ID'],
            'label': f"{r['Bereich']} / {r['Gewerk']} – {r['WartungBez']} ({intervall_txt})",
        })
    return out


def validate_teilnehmer(mitarbeiter_ids, fremdfirma_zeilen):
    """
    fremdfirma_zeilen: Liste von dicts mit keys fremdfirma_id, techniker, telefon
    """
    mitarbeiter_ids = [int(x) for x in mitarbeiter_ids if str(x).strip()]
    ff_ok = []
    for z in fremdfirma_zeilen:
        try:
            fid = int(z.get('fremdfirma_id'))
        except (TypeError, ValueError):
            continue
        tech = (z.get('techniker') or '').strip()
        if not tech:
            continue
        ff_ok.append({
            'fremdfirma_id': fid,
            'techniker': tech,
            'telefon': (z.get('telefon') or '').strip() or None,
        })
    if not mitarbeiter_ids and not ff_ok:
        return None, 'Bitte mindestens einen Mitarbeiter oder eine Fremdfirma-Zeile (mit Techniker) angeben.'
    return {'mitarbeiter_ids': mitarbeiter_ids, 'fremdfirma_zeilen': ff_ok}, None


def insert_wartungsdurchfuehrung(conn, plan_id, durchgefuehrt_am, bemerkung, teilnehmer, protokollierer_id):
    """teilnehmer: dict von validate_teilnehmer (ohne Fehler).
    Rückgabe: (Wartungsdurchfuehrung-ID, neues NaechsteFaelligkeit YYYY-MM-DD oder None)."""
    cur = conn.execute(
        '''INSERT INTO Wartungsdurchfuehrung
           (WartungsplanID, DurchgefuehrtAm, Bemerkung, ProtokolliertVonID)
           VALUES (?, ?, ?, ?)''',
        (plan_id, durchgefuehrt_am, (bemerkung or '').strip() or None, protokollierer_id),
    )
    df_id = cur.lastrowid
    for mid in teilnehmer['mitarbeiter_ids']:
        conn.execute(
            '''INSERT OR IGNORE INTO WartungsdurchfuehrungMitarbeiter
               (WartungsdurchfuehrungID, MitarbeiterID) VALUES (?, ?)''',
            (df_id, mid),
        )
    for z in teilnehmer['fremdfirma_zeilen']:
        conn.execute(
            '''INSERT INTO WartungsdurchfuehrungFremdfirma
               (WartungsdurchfuehrungID, FremdfirmaID, Techniker, Telefon)
               VALUES (?, ?, ?, ?)''',
            (df_id, z['fremdfirma_id'], z['techniker'], z['telefon']),
        )
    naechste = aktualisiere_naechste_faelligkeit_nach_durchfuehrung(conn, plan_id, durchgefuehrt_am)
    return df_id, naechste


def list_durchfuehrungen_fuer_plan(conn, plan_id):
    return conn.execute('''
        SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung, d.ErstelltAm,
               m.Vorname || ' ' || m.Nachname AS ProtokolliertVon
        FROM Wartungsdurchfuehrung d
        LEFT JOIN Mitarbeiter m ON d.ProtokolliertVonID = m.ID
        WHERE d.WartungsplanID = ?
        ORDER BY d.DurchgefuehrtAm DESC, d.ID DESC
    ''', (plan_id,)).fetchall()


def list_durchfuehrungen_fuer_wartung(conn, wartung_id):
    """Alle protokollierten Durchführungen dieser Wartung (über alle Pläne)."""
    return conn.execute('''
        SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung, d.ErstelltAm,
               p.ID AS PlanID, p.IntervallAnzahl, p.IntervallEinheit,
               m.Vorname || ' ' || m.Nachname AS ProtokolliertVon,
               (SELECT COUNT(*) FROM Datei dt
                WHERE dt.BereichTyp = 'Wartungsdurchfuehrung' AND dt.BereichID = d.ID) AS DateiAnzahl
        FROM Wartungsdurchfuehrung d
        JOIN Wartungsplan p ON d.WartungsplanID = p.ID
        LEFT JOIN Mitarbeiter m ON d.ProtokolliertVonID = m.ID
        WHERE p.WartungID = ?
        ORDER BY d.DurchgefuehrtAm DESC, d.ID DESC
    ''', (wartung_id,)).fetchall()


def get_durchfuehrung_detail(conn, durchfuehrung_id):
    d = conn.execute('''
        SELECT d.*, p.WartungID, p.ID AS PlanID, p.IntervallEinheit, p.IntervallAnzahl,
               w.Bezeichnung AS WartungBez, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
        FROM Wartungsdurchfuehrung d
        JOIN Wartungsplan p ON d.WartungsplanID = p.ID
        JOIN Wartung w ON p.WartungID = w.ID
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE d.ID = ?
    ''', (durchfuehrung_id,)).fetchone()
    if not d:
        return None, None, None, None
    mit = conn.execute('''
        SELECT m.ID, m.Vorname, m.Nachname, m.Personalnummer
        FROM WartungsdurchfuehrungMitarbeiter z
        JOIN Mitarbeiter m ON z.MitarbeiterID = m.ID
        WHERE z.WartungsdurchfuehrungID = ?
        ORDER BY m.Nachname, m.Vorname
    ''', (durchfuehrung_id,)).fetchall()
    ff = conn.execute('''
        SELECT f.Firmenname, z.Techniker, z.Telefon
        FROM WartungsdurchfuehrungFremdfirma z
        JOIN Fremdfirma f ON z.FremdfirmaID = f.ID
        WHERE z.WartungsdurchfuehrungID = ?
        ORDER BY z.ID
    ''', (durchfuehrung_id,)).fetchall()
    lager = conn.execute('''
        SELECT
            l.ID AS BuchungsID,
            l.ErsatzteilID,
            l.Typ,
            l.Menge,
            l.Grund,
            l.Buchungsdatum,
            l.Bemerkung,
            l.Preis,
            l.Waehrung,
            e.Bestellnummer,
            e.Bezeichnung AS ErsatzteilBezeichnung,
            m.Vorname || ' ' || m.Nachname AS VerwendetVon,
            k.Bezeichnung AS Kostenstelle
        FROM Lagerbuchung l
        JOIN Ersatzteil e ON l.ErsatzteilID = e.ID
        LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
        LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
        WHERE l.WartungsdurchfuehrungID = ?
        ORDER BY l.Buchungsdatum DESC
    ''', (durchfuehrung_id,)).fetchall()
    return d, mit, ff, lager


def get_context_fuer_lagerbuchung(conn, durchfuehrung_id):
    r = conn.execute('''
        SELECT b.Bezeichnung AS Bereich, g.Bezeichnung AS Gewerk, w.Bezeichnung AS WartungBez,
               d.DurchgefuehrtAm
        FROM Wartungsdurchfuehrung d
        JOIN Wartungsplan p ON d.WartungsplanID = p.ID
        JOIN Wartung w ON p.WartungID = w.ID
        JOIN Gewerke g ON w.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        WHERE d.ID = ?
    ''', (durchfuehrung_id,)).fetchone()
    if not r:
        return None
    parts = [r['Bereich'], r['Gewerk'], r['WartungBez']]
    return ' – '.join(parts)


def get_verfuegbare_ersatzteile(conn, mitarbeiter_id, is_admin):
    # Ersatzteile: erweiterte Abteilungssicht (inkl. Unterabteilungen) wie im Ersatzteil-Modul
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    q = '''
        SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.AktuellerBestand, e.Einheit
        FROM Ersatzteil e
        WHERE e.Gelöscht = 0 AND e.Aktiv = 1 AND e.AktuellerBestand > 0
    '''
    params = []
    if not is_admin and sichtbare:
        ph = ','.join(['?'] * len(sichtbare))
        q += f''' AND e.ID IN (
            SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff WHERE AbteilungID IN ({ph})
        )'''
        params.extend(sichtbare)
    elif not is_admin:
        q += ' AND 1=0'
    q += ' ORDER BY e.Bezeichnung'
    return conn.execute(q, params).fetchall()


def process_ersatzteile_fuer_wartungsdurchfuehrung(
    durchfuehrung_id, ersatzteil_ids, ersatzteil_mengen, ersatzteil_bemerkungen,
    mitarbeiter_id, conn, is_admin=False, ersatzteil_kostenstellen=None,
):
    from modules.ersatzteile.services.lagerbuchung_services import create_lagerbuchung

    if not ersatzteil_ids:
        return 0
    ctx = get_context_fuer_lagerbuchung(conn, durchfuehrung_id)
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    verarbeitet = 0
    for i, eid_raw in enumerate(ersatzteil_ids):
        if not eid_raw or not str(eid_raw).strip():
            continue
        try:
            ersatzteil_id = int(eid_raw)
            menge = int(ersatzteil_mengen[i]) if i < len(ersatzteil_mengen) and ersatzteil_mengen[i] else 1
        except (ValueError, TypeError):
            continue
        if menge <= 0:
            continue
        bemerkung = (
            ersatzteil_bemerkungen[i].strip()
            if i < len(ersatzteil_bemerkungen) and ersatzteil_bemerkungen[i]
            else None
        )
        kostenstelle_id = None
        if ersatzteil_kostenstellen and i < len(ersatzteil_kostenstellen) and ersatzteil_kostenstellen[i]:
            try:
                kostenstelle_id = int(ersatzteil_kostenstellen[i])
            except (ValueError, TypeError):
                kostenstelle_id = None
        et = conn.execute(
            '''SELECT ID, AktuellerBestand, Preis, Waehrung FROM Ersatzteil
               WHERE ID = ? AND Gelöscht = 0 AND Aktiv = 1''',
            (ersatzteil_id,),
        ).fetchone()
        if not et:
            continue
        if not is_admin:
            if sichtbare_abteilungen:
                ph = ','.join(['?'] * len(sichtbare_abteilungen))
                z = conn.execute(
                    f'''SELECT 1 FROM ErsatzteilAbteilungZugriff
                        WHERE ErsatzteilID = ? AND AbteilungID IN ({ph})''',
                    [ersatzteil_id] + sichtbare_abteilungen,
                ).fetchone()
                if not z:
                    continue
            else:
                continue
        lb = ctx or 'Wartung'
        if bemerkung:
            lb = f'{lb}\n{bemerkung}'
        ok, _, _ = create_lagerbuchung(
            ersatzteil_id=ersatzteil_id,
            typ='Ausgang',
            menge=menge,
            grund=f'Wartungsdurchführung {durchfuehrung_id}',
            mitarbeiter_id=mitarbeiter_id,
            conn=conn,
            thema_id=None,
            kostenstelle_id=kostenstelle_id,
            bemerkung=lb,
            wartungsdurchfuehrung_id=durchfuehrung_id,
        )
        if ok:
            verarbeitet += 1
    return verarbeitet


def buche_ein_ersatzteil_wartungsdurchfuehrung(
    conn,
    durchfuehrung_id,
    ersatzteil_id_raw,
    menge_raw,
    bemerkung_form,
    kostenstelle_id_raw,
    mitarbeiter_id,
    is_admin,
):
    """Eine Lagerbuchung (Ausgang) für eine Wartungsdurchführung – gleiche Regeln wie Mehrfach-Formular."""
    if not ersatzteil_id_raw or not str(ersatzteil_id_raw).strip():
        return False, 'Bitte ein Ersatzteil wählen oder die ID eingeben.'
    ks_list = []
    if kostenstelle_id_raw and str(kostenstelle_id_raw).strip():
        ks_list = [str(kostenstelle_id_raw).strip()]
    else:
        ks_list = ['']
    n = process_ersatzteile_fuer_wartungsdurchfuehrung(
        durchfuehrung_id,
        [str(ersatzteil_id_raw).strip()],
        [str(menge_raw) if menge_raw is not None else '1'],
        [bemerkung_form or ''],
        mitarbeiter_id,
        conn,
        is_admin=is_admin,
        ersatzteil_kostenstellen=ks_list,
    )
    if n:
        return True, 'Ersatzteil zugeordnet und Lagerbuchung ausgeführt.'
    return False, 'Buchung nicht möglich (Artikel unbekannt, kein Bestand oder keine Berechtigung).'


# --- Fremdfirma ---
def list_fremdfirmen(conn, nur_aktiv=True):
    q = '''
        SELECT f.ID, f.Firmenname, f.Adresse, f.Taetigkeitsbereich, f.Aktiv
        FROM Fremdfirma f
    '''
    if nur_aktiv:
        q += ' WHERE f.Aktiv = 1'
    q += ' ORDER BY f.Firmenname'
    return conn.execute(q).fetchall()


def create_fremdfirma(conn, firmenname, adresse, taetigkeitsbereich):
    cur = conn.execute(
        'INSERT INTO Fremdfirma (Firmenname, Adresse, Taetigkeitsbereich) VALUES (?, ?, ?)',
        (
            firmenname.strip(),
            (adresse or '').strip() or None,
            (taetigkeitsbereich or '').strip() or None,
        ),
    )
    return cur.lastrowid


def update_fremdfirma(conn, fid, firmenname, adresse, taetigkeitsbereich, aktiv):
    conn.execute(
        'UPDATE Fremdfirma SET Firmenname = ?, Adresse = ?, Taetigkeitsbereich = ?, Aktiv = ? WHERE ID = ?',
        (
            firmenname.strip(),
            (adresse or '').strip() or None,
            (taetigkeitsbereich or '').strip() or None,
            1 if aktiv else 0,
            fid,
        ),
    )


def get_fremdfirma(conn, fid):
    return conn.execute('SELECT * FROM Fremdfirma WHERE ID = ?', (fid,)).fetchone()
