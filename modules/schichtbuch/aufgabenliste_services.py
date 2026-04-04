"""
Aufgabenlisten: Sichtbarkeit, Stammdaten, Themen-Zuordnung (Schichtbuch).
"""

from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.berechtigungen import hat_berechtigung

from . import services as schichtbuch_services

BERECHTIGUNG_THEMEN = 'darf_aufgabenliste_themen_verwalten'


def mitarbeiter_sieht_aufgabenliste(mitarbeiter_id, aufgabenliste_id, conn, is_admin=False):
    """Admin/Ersteller immer; sonst nur nach expliziter Abteilungs- und/oder Mitarbeiter-Sichtbarkeit (ODER)."""
    if is_admin:
        return True
    row = conn.execute(
        'SELECT ErstellerMitarbeiterID FROM Aufgabenliste WHERE ID = ? AND Aktiv = 1',
        (aufgabenliste_id,),
    ).fetchone()
    if not row:
        return False
    if row['ErstellerMitarbeiterID'] == mitarbeiter_id:
        return True

    n_abt = conn.execute(
        'SELECT COUNT(*) AS c FROM AufgabenlisteSichtbarkeitAbteilung WHERE AufgabenlisteID = ?',
        (aufgabenliste_id,),
    ).fetchone()['c']
    n_ma = conn.execute(
        'SELECT COUNT(*) AS c FROM AufgabenlisteSichtbarkeitMitarbeiter WHERE AufgabenlisteID = ?',
        (aufgabenliste_id,),
    ).fetchone()['c']

    dept_ok = False
    ma_ok = False

    if n_abt > 0:
        sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn) or []
        if sichtbare:
            ph = ','.join(['?'] * len(sichtbare))
            hit = conn.execute(
                f'''SELECT COUNT(*) AS c FROM AufgabenlisteSichtbarkeitAbteilung
                    WHERE AufgabenlisteID = ? AND AbteilungID IN ({ph})''',
                [aufgabenliste_id] + sichtbare,
            ).fetchone()['c']
            dept_ok = hit > 0

    if n_ma > 0:
        hit_ma = conn.execute(
            '''SELECT COUNT(*) AS c FROM AufgabenlisteSichtbarkeitMitarbeiter
               WHERE AufgabenlisteID = ? AND MitarbeiterID = ?''',
            (aufgabenliste_id, mitarbeiter_id),
        ).fetchone()['c']
        ma_ok = hit_ma > 0

    if n_abt > 0 and n_ma > 0:
        return dept_ok or ma_ok
    if n_abt > 0:
        return dept_ok
    if n_ma > 0:
        return ma_ok
    return False


def darf_aufgabenliste_stammdaten_bearbeiten(mitarbeiter_id, aufgabenliste_id, conn, is_admin=False):
    if is_admin:
        return True
    row = conn.execute(
        'SELECT ErstellerMitarbeiterID FROM Aufgabenliste WHERE ID = ? AND Aktiv = 1',
        (aufgabenliste_id,),
    ).fetchone()
    return bool(row and row['ErstellerMitarbeiterID'] == mitarbeiter_id)


def darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, aufgabenliste_id, conn, is_admin=False):
    """Themen hinzufügen/entfernen: Admin, Berechtigung oder Ersteller der Liste."""
    if is_admin:
        return True
    if hat_berechtigung(mitarbeiter_id, BERECHTIGUNG_THEMEN, conn):
        return True
    row = conn.execute(
        'SELECT ErstellerMitarbeiterID FROM Aufgabenliste WHERE ID = ? AND Aktiv = 1',
        (aufgabenliste_id,),
    ).fetchone()
    return bool(row and row['ErstellerMitarbeiterID'] == mitarbeiter_id)


def thema_sichtbar_ueber_aufgabenliste(thema_id, mitarbeiter_id, conn, is_admin=False):
    """True, wenn Thema in mindestens einer für den Nutzer sichtbaren Aufgabenliste liegt."""
    rows = conn.execute(
        '''SELECT DISTINCT al.ID FROM AufgabenlisteThema at
           JOIN Aufgabenliste al ON al.ID = at.AufgabenlisteID
           WHERE at.ThemaID = ? AND al.Aktiv = 1''',
        (thema_id,),
    ).fetchall()
    for r in rows:
        if mitarbeiter_sieht_aufgabenliste(mitarbeiter_id, r['ID'], conn, is_admin=is_admin):
            return True
    return False


def list_aufgabenlisten_fuer_mitarbeiter(mitarbeiter_id, conn, is_admin=False):
    """Alle für den Mitarbeiter sichtbaren aktiven Aufgabenlisten."""
    all_ids = conn.execute(
        'SELECT ID FROM Aufgabenliste WHERE Aktiv = 1 ORDER BY Bezeichnung COLLATE NOCASE'
    ).fetchall()
    result = []
    for r in all_ids:
        lid = r['ID']
        if mitarbeiter_sieht_aufgabenliste(mitarbeiter_id, lid, conn, is_admin=is_admin):
            row = conn.execute(
                '''
                SELECT al.ID, al.Bezeichnung, al.Beschreibung, al.ErstellerMitarbeiterID,
                       al.ErstelltAm,
                       m.Vorname, m.Nachname,
                       CASE WHEN EXISTS (
                           SELECT 1 FROM AufgabenlisteThema at
                           INNER JOIN SchichtbuchThema t ON t.ID = at.ThemaID AND t.Gelöscht = 0
                           WHERE at.AufgabenlisteID = al.ID
                             AND (t.StatusID IS NULL OR t.StatusID != 1)
                       ) THEN 1 ELSE 0 END AS IstOffen
                FROM Aufgabenliste al
                LEFT JOIN Mitarbeiter m ON m.ID = al.ErstellerMitarbeiterID
                WHERE al.ID = ?
                ''',
                (lid,),
            ).fetchone()
            if row:
                result.append(row)
    return result


def get_aufgabenlisten_fuer_thema_neu_formular(mitarbeiter_id, conn, is_admin=False):
    """
    Für Checkboxen "Thema neu": sichtbare Listen mit Flag, ob Zuordnung erlaubt.
    """
    rows = list_aufgabenlisten_fuer_mitarbeiter(mitarbeiter_id, conn, is_admin=is_admin)
    out = []
    for row in rows:
        lid = row['ID']
        out.append({
            'id': lid,
            'bezeichnung': row['Bezeichnung'],
            'beschreibung': row['Beschreibung'],
            'darf_zuordnen': darf_themen_zu_aufgabenliste_zuordnen(
                mitarbeiter_id, lid, conn, is_admin=is_admin
            ),
        })
    return out


def link_thema_zu_aufgabenlisten(thema_id, mitarbeiter_id, aufgabenliste_ids, conn, is_admin=False):
    """
    Fügt Thema zu Listen hinzu (nach Thema-Erstellung). Prüft je Liste Zuordnungsrecht und Sichtbarkeit.
    """
    import sqlite3

    for lid_raw in aufgabenliste_ids or []:
        try:
            lid = int(lid_raw)
        except (TypeError, ValueError):
            continue
        if not mitarbeiter_sieht_aufgabenliste(mitarbeiter_id, lid, conn, is_admin=is_admin):
            continue
        if not darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, lid, conn, is_admin=is_admin):
            continue
        max_sort = conn.execute(
            'SELECT COALESCE(MAX(Sortierung), -1) AS m FROM AufgabenlisteThema WHERE AufgabenlisteID = ?',
            (lid,),
        ).fetchone()['m']
        try:
            conn.execute(
                '''INSERT INTO AufgabenlisteThema
                   (AufgabenlisteID, ThemaID, Sortierung, HinzugefuegtVonMitarbeiterID)
                   VALUES (?, ?, ?, ?)''',
                (lid, thema_id, max_sort + 1, mitarbeiter_id),
            )
        except sqlite3.IntegrityError:
            pass


def get_thema_aufgabenlisten_json(thema_id, mitarbeiter_id, conn, is_admin=False):
    """Payload für GET Modal: alle sichtbaren Listen mit is_current und darf_edit."""
    sichtbar = list_aufgabenlisten_fuer_mitarbeiter(mitarbeiter_id, conn, is_admin=is_admin)
    current_rows = conn.execute(
        'SELECT AufgabenlisteID FROM AufgabenlisteThema WHERE ThemaID = ?',
        (thema_id,),
    ).fetchall()
    current_ids = {r['AufgabenlisteID'] for r in current_rows}

    listen = []
    for row in sichtbar:
        lid = row['ID']
        listen.append({
            'id': lid,
            'bezeichnung': row['Bezeichnung'],
            'is_current': lid in current_ids,
            'darf_edit': darf_themen_zu_aufgabenliste_zuordnen(
                mitarbeiter_id, lid, conn, is_admin=is_admin
            ),
        })

    any_edit = any(x['darf_edit'] for x in listen)
    return {
        'success': True,
        'thema_id': thema_id,
        'listen': listen,
        'any_edit': any_edit,
    }


def set_thema_aufgabenlisten(thema_id, mitarbeiter_id, gewaehlte_liste_ids, conn, is_admin=False):
    """
    Synchronisiert Zuordnungen: gewaehlte_liste_ids = gewünschte Menge sichtbarer Listen.
    Nur Listen, die der Nutzer bearbeiten darf, werden geändert.
    """
    import sqlite3

    gewaehlt = set()
    for x in gewaehlte_liste_ids or []:
        try:
            gewaehlt.add(int(x))
        except (TypeError, ValueError):
            pass

    current = conn.execute(
        'SELECT AufgabenlisteID FROM AufgabenlisteThema WHERE ThemaID = ?',
        (thema_id,),
    ).fetchall()
    current_ids = {r['AufgabenlisteID'] for r in current}

    editable = set()
    for row in list_aufgabenlisten_fuer_mitarbeiter(mitarbeiter_id, conn, is_admin=is_admin):
        lid = row['ID']
        if darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, lid, conn, is_admin=is_admin):
            editable.add(lid)

    new_ids = set()
    for lid in current_ids:
        if lid not in editable:
            new_ids.add(lid)
    for lid in editable:
        if lid in gewaehlt:
            new_ids.add(lid)

    to_add = new_ids - current_ids
    to_remove = current_ids - new_ids

    for lid in to_add:
        max_sort = conn.execute(
            'SELECT COALESCE(MAX(Sortierung), -1) AS m FROM AufgabenlisteThema WHERE AufgabenlisteID = ?',
            (lid,),
        ).fetchone()['m']
        try:
            conn.execute(
                '''INSERT INTO AufgabenlisteThema
                   (AufgabenlisteID, ThemaID, Sortierung, HinzugefuegtVonMitarbeiterID)
                   VALUES (?, ?, ?, ?)''',
                (lid, thema_id, max_sort + 1, mitarbeiter_id),
            )
        except sqlite3.IntegrityError:
            pass

    for lid in to_remove:
        conn.execute(
            'DELETE FROM AufgabenlisteThema WHERE AufgabenlisteID = ? AND ThemaID = ?',
            (lid, thema_id),
        )

    return True, 'Aufgabenlisten aktualisiert.'


def create_aufgabenliste(bezeichnung, beschreibung, ersteller_id, abteilung_ids, mitarbeiter_ids, conn):
    """Neue Liste; Sichtbarkeit nur explizite Einträge (keine Auto-Abteilungen)."""
    cur = conn.cursor()
    cur.execute(
        '''INSERT INTO Aufgabenliste (Bezeichnung, Beschreibung, ErstellerMitarbeiterID)
           VALUES (?, ?, ?)''',
        ((bezeichnung or '').strip(), (beschreibung or '').strip() or None, ersteller_id),
    )
    lid = cur.lastrowid
    for abt in abteilung_ids or []:
        try:
            aid = int(abt)
            cur.execute(
                '''INSERT OR IGNORE INTO AufgabenlisteSichtbarkeitAbteilung (AufgabenlisteID, AbteilungID)
                   VALUES (?, ?)''',
                (lid, aid),
            )
        except (TypeError, ValueError):
            pass
    for mid in mitarbeiter_ids or []:
        try:
            mx = int(mid)
            cur.execute(
                '''INSERT OR IGNORE INTO AufgabenlisteSichtbarkeitMitarbeiter (AufgabenlisteID, MitarbeiterID)
                   VALUES (?, ?)''',
                (lid, mx),
            )
        except (TypeError, ValueError):
            pass
    return lid


def archiviere_aufgabenliste(aufgabenliste_id, mitarbeiter_id, conn, is_admin=False):
    """Setzt Aktiv = 0 (nicht in ?bersicht). Nur Ersteller oder Admin."""
    if not darf_aufgabenliste_stammdaten_bearbeiten(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return False, 'Keine Berechtigung.'
    cur = conn.execute(
        'UPDATE Aufgabenliste SET Aktiv = 0 WHERE ID = ? AND Aktiv = 1',
        (aufgabenliste_id,),
    )
    if cur.rowcount == 0:
        row = conn.execute('SELECT ID FROM Aufgabenliste WHERE ID = ?', (aufgabenliste_id,)).fetchone()
        if not row:
            return False, 'Liste nicht gefunden.'
        return False, 'Liste ist bereits archiviert.'
    return True, 'Liste archiviert.'


def update_aufgabenliste_stammdaten(
    aufgabenliste_id, bezeichnung, beschreibung, abteilung_ids, mitarbeiter_ids, conn
):
    conn.execute(
        'UPDATE Aufgabenliste SET Bezeichnung = ?, Beschreibung = ? WHERE ID = ?',
        ((bezeichnung or '').strip(), (beschreibung or '').strip() or None, aufgabenliste_id),
    )
    conn.execute(
        'DELETE FROM AufgabenlisteSichtbarkeitAbteilung WHERE AufgabenlisteID = ?',
        (aufgabenliste_id,),
    )
    conn.execute(
        'DELETE FROM AufgabenlisteSichtbarkeitMitarbeiter WHERE AufgabenlisteID = ?',
        (aufgabenliste_id,),
    )
    for abt in abteilung_ids or []:
        try:
            aid = int(abt)
            conn.execute(
                '''INSERT OR IGNORE INTO AufgabenlisteSichtbarkeitAbteilung (AufgabenlisteID, AbteilungID)
                   VALUES (?, ?)''',
                (aufgabenliste_id, aid),
            )
        except (TypeError, ValueError):
            pass
    for mid in mitarbeiter_ids or []:
        try:
            mx = int(mid)
            conn.execute(
                '''INSERT OR IGNORE INTO AufgabenlisteSichtbarkeitMitarbeiter (AufgabenlisteID, MitarbeiterID)
                   VALUES (?, ?)''',
                (aufgabenliste_id, mx),
            )
        except (TypeError, ValueError):
            pass


def get_aufgabenliste_detail(aufgabenliste_id, conn):
    liste = conn.execute(
        '''SELECT al.*, m.Vorname, m.Nachname
           FROM Aufgabenliste al
           LEFT JOIN Mitarbeiter m ON m.ID = al.ErstellerMitarbeiterID
           WHERE al.ID = ?''',
        (aufgabenliste_id,),
    ).fetchone()
    if not liste:
        return None
    abt = conn.execute(
        '''SELECT a.ID, a.Bezeichnung FROM AufgabenlisteSichtbarkeitAbteilung s
           JOIN Abteilung a ON a.ID = s.AbteilungID
           WHERE s.AufgabenlisteID = ? ORDER BY a.Sortierung, a.Bezeichnung''',
        (aufgabenliste_id,),
    ).fetchall()
    mas = conn.execute(
        '''SELECT m.ID, m.Vorname, m.Nachname FROM AufgabenlisteSichtbarkeitMitarbeiter s
           JOIN Mitarbeiter m ON m.ID = s.MitarbeiterID
           WHERE s.AufgabenlisteID = ? ORDER BY m.Nachname, m.Vorname''',
        (aufgabenliste_id,),
    ).fetchall()
    return {'liste': liste, 'abteilungen': abt, 'mitarbeiter': mas}


def list_themen_fuer_aufgabenliste(
    aufgabenliste_id,
    conn,
    bereich_filter=None,
    gewerk_filter=None,
    status_filter_list=None,
):
    """Themen in der Liste mit Metadaten; optional Filter wie Themenliste."""
    q = '''
        SELECT
            t.ID,
            b.Bezeichnung AS Bereich,
            g.Bezeichnung AS Gewerk,
            s.Bezeichnung AS Status,
            s.Farbe AS Farbe,
            at.Sortierung,
            at.HinzugefuegtAm,
            at.HinzugefuegtVonMitarbeiterID,
            mv.Vorname AS HinzugefuegtVonVorname,
            mv.Nachname AS HinzugefuegtVonNachname,
            (SELECT MAX(bm.Datum) FROM SchichtbuchBemerkungen bm
             WHERE bm.ThemaID = t.ID AND bm.Gelöscht = 0) AS LetzteBemerkungDatum,
            (SELECT bm.Bemerkung FROM SchichtbuchBemerkungen bm
             WHERE bm.ThemaID = t.ID AND bm.Gelöscht = 0
             ORDER BY bm.Datum DESC LIMIT 1) AS LetzteBemerkungText
        FROM AufgabenlisteThema at
        JOIN SchichtbuchThema t ON t.ID = at.ThemaID AND t.Gelöscht = 0
        JOIN Gewerke g ON t.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Status s ON t.StatusID = s.ID
        LEFT JOIN Mitarbeiter mv ON mv.ID = at.HinzugefuegtVonMitarbeiterID
        WHERE at.AufgabenlisteID = ?
    '''
    params = [aufgabenliste_id]
    if bereich_filter:
        q += ' AND b.Bezeichnung = ?'
        params.append(bereich_filter)
    if gewerk_filter:
        q += ' AND g.Bezeichnung = ?'
        params.append(gewerk_filter)
    if status_filter_list:
        ph = ','.join(['?'] * len(status_filter_list))
        q += f' AND s.Bezeichnung IN ({ph})'
        params.extend(status_filter_list)
    q += ' ORDER BY at.Sortierung ASC, at.HinzugefuegtAm DESC, t.ID DESC'
    return conn.execute(q, params).fetchall()


def remove_thema_from_aufgabenliste(aufgabenliste_id, thema_id, mitarbeiter_id, conn, is_admin=False):
    if not darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return False, 'Keine Berechtigung.'
    conn.execute(
        'DELETE FROM AufgabenlisteThema WHERE AufgabenlisteID = ? AND ThemaID = ?',
        (aufgabenliste_id, thema_id),
    )
    return True, 'Entfernt.'


def add_thema_to_aufgabenliste(aufgabenliste_id, thema_id, mitarbeiter_id, conn, is_admin=False):
    """Thema zur Liste hinzufügen (nicht gelöscht, noch nicht zugeordnet)."""
    import sqlite3

    if not mitarbeiter_sieht_aufgabenliste(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return False, 'Keine Berechtigung für diese Liste.'
    if not darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return False, 'Keine Berechtigung, Themen zuzuordnen.'
    row = conn.execute(
        'SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0',
        (thema_id,),
    ).fetchone()
    if not row:
        return False, 'Thema nicht gefunden.'
    dup = conn.execute(
        'SELECT 1 FROM AufgabenlisteThema WHERE AufgabenlisteID = ? AND ThemaID = ?',
        (aufgabenliste_id, thema_id),
    ).fetchone()
    if dup:
        return False, 'Thema ist bereits in der Liste.'
    max_sort = conn.execute(
        'SELECT COALESCE(MAX(Sortierung), -1) AS m FROM AufgabenlisteThema WHERE AufgabenlisteID = ?',
        (aufgabenliste_id,),
    ).fetchone()['m']
    try:
        conn.execute(
            '''INSERT INTO AufgabenlisteThema
               (AufgabenlisteID, ThemaID, Sortierung, HinzugefuegtVonMitarbeiterID)
               VALUES (?, ?, ?, ?)''',
            (aufgabenliste_id, thema_id, max_sort + 1, mitarbeiter_id),
        )
    except sqlite3.IntegrityError:
        return False, 'Thema ist bereits zugeordnet.'
    return True, 'Thema hinzugefügt.'


def list_offene_themen_picker_fuer_aufgabenliste(
    aufgabenliste_id, mitarbeiter_id, conn, is_admin=False, limit=20
):
    """
    Zuletzt aktive, nicht erledigte Themen (Schichtbuch-Sichtbarkeit wie Themenliste),
    die noch nicht in dieser Aufgabenliste sind.
    """
    if not mitarbeiter_sieht_aufgabenliste(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return []
    if not darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return []
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn) or []
    auf_liste_rows = list_aufgabenlisten_fuer_mitarbeiter(mitarbeiter_id, conn, is_admin=is_admin)
    auf_ids = [r['ID'] for r in auf_liste_rows] or None
    query, params = schichtbuch_services.build_themen_query(
        sichtbare,
        limit=limit,
        offset=0,
        mitarbeiter_id=mitarbeiter_id,
        aufgabenliste_sichtbar_ids=auf_ids,
        exclude_aufgabenliste_id=aufgabenliste_id,
        exclude_erledigt_status=True,
    )
    return conn.execute(query, params).fetchall()


def reorder_aufgabenliste_themen(aufgabenliste_id, thema_ids_ordered, mitarbeiter_id, conn, is_admin=False):
    """thema_ids_ordered: gewünschte Reihenfolge (nur Themen, die in der Liste sind)."""
    if not darf_themen_zu_aufgabenliste_zuordnen(mitarbeiter_id, aufgabenliste_id, conn, is_admin=is_admin):
        return False, 'Keine Berechtigung.'
    existing = conn.execute(
        'SELECT ThemaID FROM AufgabenlisteThema WHERE AufgabenlisteID = ?',
        (aufgabenliste_id,),
    ).fetchall()
    existing_set = {r['ThemaID'] for r in existing}
    order = []
    for x in thema_ids_ordered or []:
        try:
            tid = int(x)
        except (TypeError, ValueError):
            continue
        if tid in existing_set:
            order.append(tid)
    for i, tid in enumerate(order):
        conn.execute(
            'UPDATE AufgabenlisteThema SET Sortierung = ? WHERE AufgabenlisteID = ? AND ThemaID = ?',
            (i, aufgabenliste_id, tid),
    )
    return True, 'Sortierung gespeichert.'


def duplicate_aufgabenliste(source_id, mitarbeiter_id, conn, mit_themen=False):
    """Kopiert Stammdaten + Sichtbarkeit; optional Themen-Zuordnungen."""
    d = get_aufgabenliste_detail(source_id, conn)
    if not d:
        return None
    liste = d['liste']
    bezeichnung = (liste['Bezeichnung'] or '') + ' (Kopie)'
    new_id = create_aufgabenliste(
        bezeichnung,
        liste['Beschreibung'],
        mitarbeiter_id,
        [r['ID'] for r in d['abteilungen']],
        [r['ID'] for r in d['mitarbeiter']],
        conn,
    )
    if mit_themen:
        rows = conn.execute(
            'SELECT ThemaID, Sortierung FROM AufgabenlisteThema WHERE AufgabenlisteID = ? ORDER BY Sortierung',
            (source_id,),
        ).fetchall()
        import sqlite3

        for r in rows:
            try:
                conn.execute(
                    '''INSERT INTO AufgabenlisteThema
                       (AufgabenlisteID, ThemaID, Sortierung, HinzugefuegtVonMitarbeiterID)
                       VALUES (?, ?, ?, ?)''',
                    (new_id, r['ThemaID'], r['Sortierung'], mitarbeiter_id),
                )
            except sqlite3.IntegrityError:
                pass
    return new_id


def alle_aktiven_mitarbeiter_options(conn):
    return conn.execute(
        '''SELECT ID, Vorname, Nachname, Personalnummer FROM Mitarbeiter
           WHERE Aktiv = 1 ORDER BY Nachname COLLATE NOCASE, Vorname COLLATE NOCASE'''
    ).fetchall()
