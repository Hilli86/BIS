"""Business-Logik Wartungen."""

from utils.abteilungen import get_sichtbare_abteilungen_fuer_mitarbeiter

INTERVALL_EINHEITEN = ('Tag', 'Woche', 'Monat')


def list_wartungen(conn, mitarbeiter_id, is_admin):
    if is_admin:
        return conn.execute('''
            SELECT w.ID, w.Bezeichnung, w.Aktiv, w.ErstelltAm,
                   g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
            FROM Wartung w
            JOIN Gewerke g ON w.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung
        ''').fetchall()
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
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
        ORDER BY b.Bezeichnung, g.Bezeichnung, w.Bezeichnung
    ''', [mitarbeiter_id] + sichtbare).fetchall()


def _wartung_sichtbar_params(mitarbeiter_id, sichtbare_abteilungen):
    """Parameterliste für Nicht-Admin-Sichtbarkeit (ErstelltVon + Abteilungen)."""
    return [mitarbeiter_id] + sichtbare_abteilungen


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
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
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
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
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


def list_wartungen_fuer_gewerk_sichtbar(conn, gewerk_id, mitarbeiter_id, is_admin):
    """Sichtbare Wartungen eines Gewerks (Sortierung nach Bezeichnung)."""
    if is_admin:
        return conn.execute('''
            SELECT w.ID, w.Bezeichnung, w.Aktiv
            FROM Wartung w
            WHERE w.GewerkID = ?
            ORDER BY w.Bezeichnung
        ''', (gewerk_id,)).fetchall()
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
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
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
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
        SELECT ID, IntervallEinheit, IntervallAnzahl, NaechsteFaelligkeit, Aktiv, ErstelltAm
        FROM Wartungsplan
        WHERE WartungID = ?
        ORDER BY Aktiv DESC, ID DESC
    ''', (wartung_id,)).fetchall()


def get_plan(conn, plan_id):
    return conn.execute(
        'SELECT * FROM Wartungsplan WHERE ID = ?',
        (plan_id,),
    ).fetchone()


def create_wartungsplan(conn, wartung_id, einheit, anzahl, naechste):
    if einheit not in INTERVALL_EINHEITEN:
        raise ValueError('Ungültige Intervall-Einheit.')
    try:
        anzahl = int(anzahl)
    except (TypeError, ValueError):
        raise ValueError('Intervall-Anzahl ungültig.') from None
    if anzahl < 1:
        raise ValueError('Intervall-Anzahl muss mindestens 1 sein.')
    na = (naechste or '').strip() or None
    cur = conn.execute(
        '''INSERT INTO Wartungsplan (WartungID, IntervallEinheit, IntervallAnzahl, NaechsteFaelligkeit)
           VALUES (?, ?, ?, ?)''',
        (wartung_id, einheit, anzahl, na),
    )
    return cur.lastrowid


def update_wartungsplan(conn, plan_id, einheit, anzahl, naechste, aktiv):
    if einheit not in INTERVALL_EINHEITEN:
        raise ValueError('Ungültige Intervall-Einheit.')
    try:
        anzahl = int(anzahl)
    except (TypeError, ValueError):
        raise ValueError('Intervall-Anzahl ungültig.') from None
    if anzahl < 1:
        raise ValueError('Intervall-Anzahl muss mindestens 1 sein.')
    na = (naechste or '').strip() or None
    conn.execute(
        '''UPDATE Wartungsplan SET IntervallEinheit = ?, IntervallAnzahl = ?,
           NaechsteFaelligkeit = ?, Aktiv = ? WHERE ID = ?''',
        (einheit, anzahl, na, 1 if aktiv else 0, plan_id),
    )


def list_plaene_sichtbar(conn, mitarbeiter_id, is_admin):
    """Alle Pläne, deren Stamm-Wartung der Nutzer sehen darf."""
    if is_admin:
        return conn.execute('''
            SELECT p.ID, p.IntervallEinheit, p.IntervallAnzahl, p.NaechsteFaelligkeit, p.Aktiv,
                   w.Bezeichnung AS WartungBez, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
            FROM Wartungsplan p
            JOIN Wartung w ON p.WartungID = w.ID
            JOIN Gewerke g ON w.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            WHERE w.Aktiv = 1
            ORDER BY b.Bezeichnung, w.Bezeichnung, p.ID
        ''').fetchall()
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    if not sichtbare:
        return []
    ph = ','.join(['?'] * len(sichtbare))
    return conn.execute(f'''
        SELECT p.ID, p.IntervallEinheit, p.IntervallAnzahl, p.NaechsteFaelligkeit, p.Aktiv,
               w.Bezeichnung AS WartungBez, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
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
        )
        ORDER BY b.Bezeichnung, w.Bezeichnung, p.ID
    ''', [mitarbeiter_id] + sichtbare).fetchall()


def plaene_options_fuer_select(conn, mitarbeiter_id, is_admin):
    rows = list_plaene_sichtbar(conn, mitarbeiter_id, is_admin)
    return [
        {
            'id': r['ID'],
            'label': f"{r['Bereich']} / {r['Gewerk']} – {r['WartungBez']} "
            f"(alle {r['IntervallAnzahl']} {r['IntervallEinheit']}(e))",
        }
        for r in rows
        if r['Aktiv']
    ]


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
    """teilnehmer: dict von validate_teilnehmer (ohne Fehler)."""
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
    return df_id


def list_durchfuehrungen_fuer_plan(conn, plan_id):
    return conn.execute('''
        SELECT d.ID, d.DurchgefuehrtAm, d.Bemerkung, d.ErstelltAm,
               m.Vorname || ' ' || m.Nachname AS ProtokolliertVon
        FROM Wartungsdurchfuehrung d
        LEFT JOIN Mitarbeiter m ON d.ProtokolliertVonID = m.ID
        WHERE d.WartungsplanID = ?
        ORDER BY d.DurchgefuehrtAm DESC, d.ID DESC
    ''', (plan_id,)).fetchall()


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
        SELECT l.ID, l.Menge, l.Buchungsdatum, l.Bemerkung, e.Bestellnummer, e.Bezeichnung AS ErsatzteilBez
        FROM Lagerbuchung l
        JOIN Ersatzteil e ON l.ErsatzteilID = e.ID
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
