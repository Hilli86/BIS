"""Zugriffs- und Berechtigungshilfen für das Wartungen-Modul."""

from flask import session

from utils.abteilungen import get_sichtbare_abteilungen_fuer_mitarbeiter


def user_perms():
    return session.get('user_berechtigungen', [])


def is_admin():
    return 'admin' in user_perms()


def kann_wartung_stamm_anlegen():
    return is_admin() or 'wartung_erstellen' in user_perms()


def kann_wartungsplan_pflegen():
    return is_admin() or 'wartung_erstellen' in user_perms() or 'wartung_nur_Plan_erstellen' in user_perms()


def kann_wartung_protokollieren():
    """Wartungsdurchführungen erfassen, Serviceberichte hochladen, Ersatzteile verbuchen."""
    return (
        is_admin()
        or 'wartung_erstellen' in user_perms()
        or 'wartung_nur_Plan_erstellen' in user_perms()
        or 'wartung_protokollieren' in user_perms()
    )


def hat_wartung_zugriff(mitarbeiter_id, wartung_id, conn):
    if is_admin():
        return True
    row = conn.execute(
        'SELECT ErstelltVonID FROM Wartung WHERE ID = ? AND Aktiv = 1',
        (wartung_id,),
    ).fetchone()
    if not row:
        return False
    if row['ErstelltVonID'] == mitarbeiter_id:
        return True
    sichtbare = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    if not sichtbare:
        return False
    ph = ','.join(['?'] * len(sichtbare))
    n = conn.execute(
        f'''SELECT COUNT(*) AS c FROM WartungAbteilungZugriff
            WHERE WartungID = ? AND AbteilungID IN ({ph})''',
        [wartung_id] + sichtbare,
    ).fetchone()
    return n['c'] > 0


def hat_wartung_stamm_bearbeiten(mitarbeiter_id, wartung_id, conn):
    """Stamm speichern: global wartung_erstellen + sichtbar auf Wartung."""
    if not (is_admin() or 'wartung_erstellen' in user_perms()):
        return False
    return hat_wartung_zugriff(mitarbeiter_id, wartung_id, conn)


def get_wartung_id_fuer_plan(conn, plan_id):
    r = conn.execute(
        'SELECT WartungID FROM Wartungsplan WHERE ID = ?',
        (plan_id,),
    ).fetchone()
    return r['WartungID'] if r else None


def hat_wartungsplan_zugriff(mitarbeiter_id, plan_id, conn):
    wid = get_wartung_id_fuer_plan(conn, plan_id)
    if not wid:
        return False
    return hat_wartung_zugriff(mitarbeiter_id, wid, conn)


def hat_wartungsdurchfuehrung_zugriff(mitarbeiter_id, durchfuehrung_id, conn):
    r = conn.execute(
        '''SELECT p.WartungID FROM Wartungsdurchfuehrung d
           JOIN Wartungsplan p ON d.WartungsplanID = p.ID
           WHERE d.ID = ?''',
        (durchfuehrung_id,),
    ).fetchone()
    if not r:
        return False
    return hat_wartung_zugriff(mitarbeiter_id, r['WartungID'], conn)
