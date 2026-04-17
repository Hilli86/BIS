"""
Plausible Test-Wartungen für BIS (SQLite).

Legt an: Wartung → Wartungsplan → Wartungsdurchführung(en) inkl. Teilnehmer (Mitarbeiter).
Nutzt bestehende Gewerke, Mitarbeiter und Abteilungen aus der Datenbank.

Aufruf (Projektroot):
    py scripts/generate_test_wartungen.py
    py scripts/generate_test_wartungen.py --anzahl 5 --jahr 2026 --seed 42
    py scripts/generate_test_wartungen.py --dry-run

Umgebung: DATABASE_URL (optional), sonst database_main.db im aktuellen Verzeichnis.
"""

from __future__ import annotations

import argparse
import calendar
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta

# Projektroot für Importe / konsistente Pfade
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

INTERVALL_EINHEITEN = ('Tag', 'Woche', 'Monat')

WARTUNG_TITEL_FRAGMENTS = [
    'Inspektion',
    'Wartung gemäß Herstellervorgabe',
    'Funktionsprüfung',
    'Verschleißkontrolle',
    'Schmierung und Nachstellung',
    'Sichtprüfung Anschlüsse',
    'Kalibrierung / Abgleich',
    'Filterwechsel',
    'Dichtigkeitsprüfung',
    'Sicherheitsrelevante Prüfung',
]

BESCHREIBUNGEN = [
    'Prüfprotokoll liegt im Dokumentenordner der Wartung.',
    'Bei Auffälligkeiten QS und Bereichsleitung informieren.',
    'Ersatzteile nur aus freigegebenem Lager entnehmen.',
    'Arbeiten nur bei freigegebenem Sicherheitskonzept.',
    'Messwerte im Prüfblatt dokumentieren.',
]

BEMERKUNGEN_DF = [
    'Durchführung ohne Beanstandung.',
    'Leichte Verschmutzung beseitigt, Funktion i. O.',
    'Eine Dichtung erneuert, Rest i. O.',
    'Nachjustierung der Spindel / Lagerluft.',
    'Software-Update eingespielt, Testlauf OK.',
    'Fremdfirma hat Prüfung dokumentiert, Abnahme intern.',
    'Ersatzteilverbuchung siehe Lager.',
    None,
]


def _db_path() -> str:
    return os.environ.get('DATABASE_URL', 'database_main.db')


def add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return d.replace(year=y, month=m, day=min(d.day, last))


def faelligkeitstermine_im_jahr(
    jahr: int,
    einheit: str,
    anzahl: int,
    rng: random.Random,
    max_termine: int,
) -> list[date]:
    """Nächste Termine ab zufälligem Start im Q1 bis Jahresende (begrenzt)."""
    d0 = date(jahr, rng.randint(1, 3), rng.randint(1, 28))
    ende = date(jahr, 12, 31)
    out: list[date] = []
    d = d0
    while d <= ende and len(out) < max_termine:
        out.append(d)
        if einheit == 'Tag':
            d = d + timedelta(days=anzahl)
        elif einheit == 'Woche':
            d = d + timedelta(weeks=anzahl)
        else:
            d = add_months(d, anzahl)
    return out


def naechste_faelligkeit_string(rng: random.Random, jahr: int) -> str:
    """Datum für NaechsteFaelligkeit (nächste 2–8 Monate ab Jahresmitte)."""
    m = rng.randint(1, 12)
    last = calendar.monthrange(jahr, m)[1]
    day = rng.randint(1, last)
    return date(jahr, m, day).isoformat()


def fetch_gewerke(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        '''
        SELECT g.ID, g.Bezeichnung AS Gewerk, b.Bezeichnung AS Bereich
        FROM Gewerke g
        JOIN Bereich b ON g.BereichID = b.ID
        ORDER BY b.Bezeichnung, g.Bezeichnung
        '''
    ).fetchall()


def fetch_mitarbeiter_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        'SELECT ID FROM Mitarbeiter WHERE Aktiv = 1 ORDER BY ID'
    ).fetchall()
    return [int(r['ID']) for r in rows]


def fetch_abteilung_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        'SELECT ID FROM Abteilung WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung'
    ).fetchall()
    return [int(r['ID']) for r in rows]


def fetch_fremdfirmen_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        'SELECT ID FROM Fremdfirma WHERE Aktiv = 1 ORDER BY Firmenname'
    ).fetchall()
    return [int(r['ID']) for r in rows]


def insert_wartung(
    conn: sqlite3.Connection,
    gewerk_id: int,
    bezeichnung: str,
    beschreibung: str | None,
    erstellt_von_id: int,
    abteilung_ids: list[int],
) -> int:
    cur = conn.execute(
        '''
        INSERT INTO Wartung (GewerkID, Bezeichnung, Beschreibung, ErstelltVonID)
        VALUES (?, ?, ?, ?)
        ''',
        (gewerk_id, bezeichnung.strip(), (beschreibung or '').strip() or None, erstellt_von_id),
    )
    wid = cur.lastrowid
    conn.execute('DELETE FROM WartungAbteilungZugriff WHERE WartungID = ?', (wid,))
    for aid in abteilung_ids:
        conn.execute(
            'INSERT INTO WartungAbteilungZugriff (WartungID, AbteilungID) VALUES (?, ?)',
            (wid, aid),
        )
    return int(wid)


def insert_plan(
    conn: sqlite3.Connection,
    wartung_id: int,
    einheit: str,
    anzahl: int,
    naechste: str | None,
) -> int:
    cur = conn.execute(
        '''
        INSERT INTO Wartungsplan
        (WartungID, IntervallEinheit, IntervallAnzahl, NaechsteFaelligkeit, HatFestesIntervall,
         ErinnerungTageVor, TerminVereinbart, TerminVereinbartDatum)
        VALUES (?, ?, ?, ?, 0, NULL, 0, NULL)
        ''',
        (wartung_id, einheit, anzahl, naechste),
    )
    return int(cur.lastrowid)


def insert_durchfuehrung(
    conn: sqlite3.Connection,
    plan_id: int,
    durchgefuehrt_am: str,
    bemerkung: str | None,
    protokollierer_id: int,
    teilnehmer_ma_ids: list[int],
    fremdfirma: tuple[int, str, str | None] | None,
) -> int:
    cur = conn.execute(
        '''
        INSERT INTO Wartungsdurchfuehrung
        (WartungsplanID, DurchgefuehrtAm, Bemerkung, ProtokolliertVonID)
        VALUES (?, ?, ?, ?)
        ''',
        (plan_id, durchgefuehrt_am, bemerkung, protokollierer_id),
    )
    df_id = int(cur.lastrowid)
    for mid in teilnehmer_ma_ids:
        conn.execute(
            '''INSERT OR IGNORE INTO WartungsdurchfuehrungMitarbeiter
               (WartungsdurchfuehrungID, MitarbeiterID) VALUES (?, ?)''',
            (df_id, mid),
        )
    if fremdfirma:
        fid, techniker, telefon = fremdfirma
        conn.execute(
            '''INSERT INTO WartungsdurchfuehrungFremdfirma
               (WartungsdurchfuehrungID, FremdfirmaID, Techniker, Telefon)
               VALUES (?, ?, ?, ?)''',
            (df_id, fid, techniker, telefon),
        )
    return df_id


def loesche_test_wartungen(conn: sqlite3.Connection, prefix: str) -> int:
    """Entfernt Wartungen deren Bezeichnung mit prefix beginnt (CASCADE zu Plänen/Durchführungen)."""
    like = prefix + '%'
    rows = conn.execute('SELECT ID FROM Wartung WHERE Bezeichnung LIKE ?', (like,)).fetchall()
    n = 0
    for r in rows:
        conn.execute('DELETE FROM Wartung WHERE ID = ?', (r['ID'],))
        n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description='Plausible Test-Wartungen erzeugen')
    parser.add_argument('--db', default=None, help='Pfad zur SQLite-DB (Standard: DATABASE_URL oder database_main.db)')
    parser.add_argument('--anzahl', type=int, default=8, help='Anzahl neuer Wartungen (Default: 8)')
    parser.add_argument('--jahr', type=int, default=2026, help='Jahr für Durchführungstermine (Default: 2026)')
    parser.add_argument('--seed', type=int, default=None, help='Zufalls-Seed für reproduzierbare Läufe')
    parser.add_argument('--prefix', default='[Test] ', help='Präfix der Bezeichnung (Default: „[Test] „)')
    parser.add_argument('--max-durchfuehrungen', type=int, default=12, help='Max. Durchführungen pro Plan (Default: 12)')
    parser.add_argument('--fremdfirma-anteil', type=float, default=0.25, help='Anteil Durchführungen mit Fremdfirma (0–1)')
    parser.add_argument('--dry-run', action='store_true', help='Nur anzeigen, nichts schreiben')
    parser.add_argument(
        '--loeschen-test',
        action='store_true',
        help='Nur Wartungen löschen, deren Bezeichnung mit --prefix beginnt (CASCADE), dann beenden',
    )
    args = parser.parse_args()
    db_file = args.db or _db_path()
    if not os.path.isfile(db_file):
        print(f'[FEHLER] Datenbank nicht gefunden: {db_file}', file=sys.stderr)
        return 1

    rng = random.Random(args.seed)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        if args.loeschen_test:
            prefix = args.prefix
            n = loesche_test_wartungen(conn, prefix)
            if args.dry_run:
                conn.rollback()
                print(f'[Dry-Run] Würde {n} Wartung(en) mit LIKE {prefix!r} + "%" löschen.')
            else:
                conn.commit()
                print(f'Gelöscht: {n} Wartung(en) (Bezeichnung LIKE {prefix!r} + "%").')
            return 0

        gewerke = fetch_gewerke(conn)
        ma_ids = fetch_mitarbeiter_ids(conn)
        abt_ids = fetch_abteilung_ids(conn)
        ff_ids = fetch_fremdfirmen_ids(conn)

        if not gewerke:
            print('[FEHLER] Keine Gewerke in der Datenbank. Bitte zuerst Stammdaten anlegen.', file=sys.stderr)
            return 1
        if not ma_ids:
            print('[FEHLER] Keine aktiven Mitarbeiter.', file=sys.stderr)
            return 1
        if not abt_ids:
            print('[FEHLER] Keine aktiven Abteilungen.', file=sys.stderr)
            return 1

        geplant = []
        for i in range(args.anzahl):
            g = rng.choice(gewerke)
            frag = rng.choice(WARTUNG_TITEL_FRAGMENTS)
            bez = f'{args.prefix}{g["Gewerk"]}: {frag}'
            besch = rng.choice(BESCHREIBUNGEN)
            erstellt_von = rng.choice(ma_ids)
            k = rng.randint(1, min(3, len(abt_ids)))
            z_abt = rng.sample(abt_ids, k)

            einheit = rng.choice(INTERVALL_EINHEITEN)
            if einheit == 'Tag':
                anzahl = rng.choice([7, 14, 30, 60, 90])
            elif einheit == 'Woche':
                anzahl = rng.choice([1, 2, 4, 8])
            else:
                anzahl = rng.choice([1, 3, 6, 12])

            naechste = naechste_faelligkeit_string(rng, args.jahr)
            termine = faelligkeitstermine_im_jahr(
                args.jahr, einheit, anzahl, rng, args.max_durchfuehrungen
            )

            geplant.append({
                'bez': bez,
                'gewerk_id': int(g['ID']),
                'besch': besch,
                'erstellt_von': erstellt_von,
                'abt': z_abt,
                'einheit': einheit,
                'anzahl': anzahl,
                'naechste': naechste,
                'termine': termine,
            })

        if args.dry_run:
            print('[Dry-Run] Geplante Einträge:')
            for p in geplant:
                print(
                    f'  - {p["bez"]} | Plan: alle {p["anzahl"]} {p["einheit"]}(e) | '
                    f'{len(p["termine"])} Durchführung(en) in {args.jahr}'
                )
            conn.rollback()
            return 0

        erstellt_w = 0
        erstellt_p = 0
        erstellt_d = 0
        for p in geplant:
            wid = insert_wartung(
                conn,
                p['gewerk_id'],
                p['bez'],
                p['besch'],
                p['erstellt_von'],
                p['abt'],
            )
            erstellt_w += 1
            pid = insert_plan(conn, wid, p['einheit'], p['anzahl'], p['naechste'])
            erstellt_p += 1
            for td in p['termine']:
                prot = rng.choice(ma_ids)
                t_ma = [rng.choice(ma_ids)]
                if rng.random() < 0.4 and len(ma_ids) > 1:
                    t2 = rng.choice([x for x in ma_ids if x != t_ma[0]])
                    t_ma.append(t2)
                ff = None
                if ff_ids and rng.random() < args.fremdfirma_anteil:
                    tech_namen = ['K. Schulz', 'A. Yilmaz', 'J. Novak', 'M. Costa']
                    ff = (rng.choice(ff_ids), rng.choice(tech_namen), '+49 30 1234567')
                    t_ma = []
                dt = datetime(td.year, td.month, td.day, rng.randint(7, 15), rng.choice([0, 15, 30, 45]), 0)
                bemerk = rng.choice(BEMERKUNGEN_DF)
                insert_durchfuehrung(
                    conn,
                    pid,
                    dt.strftime('%Y-%m-%d %H:%M:%S'),
                    bemerk,
                    prot,
                    t_ma,
                    ff,
                )
                erstellt_d += 1

        conn.commit()
        print('Fertig.')
        print(f'  Wartungen:        {erstellt_w}')
        print(f'  Wartungspläne:    {erstellt_p}')
        print(f'  Durchführungen:   {erstellt_d}')
        print(f'  Datenbank:        {db_file}')
        return 0
    except Exception as e:
        conn.rollback()
        print(f'[FEHLER] {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
