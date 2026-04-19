# -*- coding: utf-8 -*-
"""
Zentrale Aufloesung von Etiketten-Druckkonfiguration (Abteilung, Prioritaet, optionaler Drucker).
"""
from __future__ import annotations

import re

FUNKTION_ERSATZTEIL_ETIKETT = 'ersatzteil_etikett'
FUNKTION_LAGERBEHAELTER_ETIKETT = 'lagerbehaelter_etikett'
FUNKTION_PRODUKTION_ETIKETT = 'produktion_etikett'

# Anzeige im Admin (Schluessel stabil, Label deutsch)
FUNKTIONEN_ADMIN = (
    (FUNKTION_ERSATZTEIL_ETIKETT, 'Ersatzteil-Etikett (Liste, Detail, Wareneingang, Batch)'),
    (FUNKTION_LAGERBEHAELTER_ETIKETT, 'Lagerbehaelter-Etikett'),
    (
        FUNKTION_PRODUKTION_ETIKETT,
        'Produktion-Etikett (Platzhalter: {produktion_artikelnummer}, {produktion_produkt}, {produktion_datum}, '
        '{produktion_zu_verwenden_am}, {produktion_stueck}; Kopien: ^PQ)',
    ),
)


def etikett_format_substitution(zpl_header_db):
    """Platzhalter-Wert für ``{etikettenformat}`` aus der DB-Spalte label_formats.zpl_header (str.format)."""
    h = zpl_header_db if zpl_header_db is not None else ''
    return {'etikettenformat': h}


def zpl_produktion_etikett(
    etikett_row,
    produkt,
    datum_text,
    stueck_text,
    anzahl_kopien,
    artikelnummer='',
    zu_verwenden_am_text='',
):
    """
    ZPL aus Etikett-Zeile; ``druckbefehle`` nutzt str.format mit:
    ``produktion_artikelnummer``, ``produktion_produkt``, ``produktion_datum``,
    ``produktion_zu_verwenden_am``, ``produktion_stueck``, ``etikettenformat``.
    Anzahl gedruckter Etiketten wie bei Ersatzteil über ``^PQ`` (Regex-Ersetzung).
    """
    zpl_template = etikett_row['druckbefehle']
    zpl = zpl_template.format(
        produktion_artikelnummer=artikelnummer,
        produktion_produkt=produkt,
        produktion_datum=datum_text,
        produktion_zu_verwenden_am=zu_verwenden_am_text,
        produktion_stueck=stueck_text,
        **etikett_format_substitution(etikett_row['zpl_header']),
    )
    zpl = re.sub(r'\^PQ(\d+)', f'^PQ{anzahl_kopien}', zpl)
    return zpl


def get_mitarbeiter_abteilung_ids(conn, mitarbeiter_id):
    """
    Gibt (menge_abteilung_ids, primaer_abteilung_id) zurueck.
    Ohne mitarbeiter_id: leere Menge, kein Primaer (nur Fallback-Konfigurationen sind wirksam).
    """
    if not mitarbeiter_id:
        return set(), None
    primary = None
    row = conn.execute(
        'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?', (mitarbeiter_id,)
    ).fetchone()
    if row and row['PrimaerAbteilungID'] is not None:
        primary = int(row['PrimaerAbteilungID'])
    ids = set()
    if primary is not None:
        ids.add(primary)
    for r in conn.execute(
        'SELECT AbteilungID FROM MitarbeiterAbteilung WHERE MitarbeiterID = ?', (mitarbeiter_id,)
    ):
        if r['AbteilungID'] is not None:
            ids.add(int(r['AbteilungID']))
    return ids, primary


def get_abteilung_ids_for_konfig(conn, konfig_id):
    rows = conn.execute(
        'SELECT abteilung_id FROM etikett_druck_konfig_abteilung WHERE konfig_id = ?',
        (konfig_id,),
    ).fetchall()
    return {int(r['abteilung_id']) for r in rows}


def resolve_konfig_row(conn, funktion_code, mitarbeiter_id):
    """
    Waehlt eine aktive Zeile aus etikett_druck_konfig.
    Abteilungszeilen: nur wenn Schnitt mit Mitarbeiter-Abteilungen.
    Keine Abteilungszeilen: Fallback fuer alle Abteilungen.
    Bei mehreren Treffern: hoehere prioritaet, dann Treffer mit Primaerabteilung.
    """
    configs = conn.execute(
        '''
        SELECT k.id, k.etikett_id, k.drucker_id, k.prioritaet
        FROM etikett_druck_konfig k
        WHERE k.funktion_code = ? AND k.aktiv = 1
        ''',
        (funktion_code,),
    ).fetchall()
    if not configs:
        return None

    user_depts, primary = get_mitarbeiter_abteilung_ids(conn, mitarbeiter_id)
    specific_candidates = []
    fallback_candidates = []

    for c in configs:
        dept_ids = get_abteilung_ids_for_konfig(conn, c['id'])
        if dept_ids:
            inter = user_depts & dept_ids
            if not inter:
                continue
            pri_match = 1 if (primary is not None and primary in inter) else 0
            specific_candidates.append((c['prioritaet'], pri_match, c['id'], c))
        else:
            fallback_candidates.append((c['prioritaet'], c['id'], c))

    if specific_candidates:
        specific_candidates.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        return specific_candidates[0][3]
    if fallback_candidates:
        fallback_candidates.sort(key=lambda x: (-x[0], -x[1]))
        return fallback_candidates[0][2]
    return None


def load_etikett_mit_format(conn, etikett_id):
    return conn.execute(
        '''
        SELECT e.id, e.bezeichnung, e.druckbefehle, e.etikettformat_id, lf.zpl_header
        FROM Etikett e
        JOIN label_formats lf ON e.etikettformat_id = lf.id
        WHERE e.id = ?
        ''',
        (etikett_id,),
    ).fetchone()


def resolve_printer_ip(conn, drucker_id):
    if not drucker_id:
        return None
    r = conn.execute(
        'SELECT ip_address FROM zebra_printers WHERE id = ? AND active = 1', (drucker_id,)
    ).fetchone()
    return r['ip_address'] if r else None


def resolve_printer_agent_id(conn, drucker_id):
    """Liefert die agent_id eines Druckers (oder None bei Direkt-Druck/unbekannt)."""
    if not drucker_id:
        return None
    r = conn.execute(
        'SELECT agent_id FROM zebra_printers WHERE id = ? AND active = 1', (drucker_id,)
    ).fetchone()
    if not r:
        return None
    return r['agent_id']


def get_active_printers_list(conn):
    """
    Liste aller aktiven Drucker fuer UI/Modal.
    Enthaelt zusaetzlich agent_id und agent_name (NULL bei Direkt-Druck) und einen
    vorbereiteten ``modus_label``-Suffix (z. B. ``Direkt`` / ``Agent: standort-a``).
    """
    return conn.execute(
        '''
        SELECT p.id, p.name, p.ip_address, p.ort, p.agent_id,
               a.name AS agent_name
        FROM zebra_printers p
        LEFT JOIN print_agents a ON p.agent_id = a.id
        WHERE p.active = 1
        ORDER BY COALESCE(p.ort, ''), p.name
        '''
    ).fetchall()


def _printer_to_dict(p):
    """Drucker-Zeile zu serialisierbarem Dict (inkl. Hybrid-Modus-Label)."""
    agent_name = p['agent_name'] if 'agent_name' in p.keys() else None
    agent_id = p['agent_id'] if 'agent_id' in p.keys() else None
    if agent_id and agent_name:
        modus_label = f'Agent: {agent_name}'
    elif agent_id:
        modus_label = f'Agent #{agent_id}'
    else:
        modus_label = 'Direkt'
    return {
        'id': p['id'],
        'name': p['name'],
        'ip_address': p['ip_address'],
        'ort': p['ort'] or '',
        'agent_id': agent_id,
        'agent_name': agent_name or '',
        'modus_label': modus_label,
    }


def build_print_resolution(conn, funktion_code, mitarbeiter_id, drucker_id_override=None):
    """
    Ergebnis-Dict:
      ok: bool
      error_message: str | None
      needs_printer_choice: bool
      printers: list[dict] (fuer Modal; inkl. agent_id, agent_name, modus_label)
      etikett: Row | None (mit zpl_header, druckbefehle)
      printer_ip: str | None
      drucker_id: int | None
      agent_id: int | None  (None = Direkt-Druck vom Server)
    """
    k = resolve_konfig_row(conn, funktion_code, mitarbeiter_id)
    if not k:
        return {
            'ok': False,
            'error_message': 'Keine passende Druckkonfiguration. Bitte im Admin unter Etikettendrucker anlegen.',
            'needs_printer_choice': False,
            'printers': [],
            'etikett': None,
            'printer_ip': None,
            'drucker_id': None,
            'agent_id': None,
        }

    et = load_etikett_mit_format(conn, k['etikett_id'])
    if not et:
        return {
            'ok': False,
            'error_message': 'Etiketten-Template nicht gefunden.',
            'needs_printer_choice': False,
            'printers': [],
            'etikett': None,
            'printer_ip': None,
            'drucker_id': None,
            'agent_id': None,
        }

    eff_drucker = drucker_id_override if drucker_id_override is not None else k['drucker_id']

    if eff_drucker is not None:
        row = conn.execute(
            '''SELECT id, ip_address, agent_id
               FROM zebra_printers WHERE id = ? AND active = 1''',
            (eff_drucker,),
        ).fetchone()
        if not row:
            return {
                'ok': False,
                'error_message': 'Drucker nicht gefunden oder inaktiv.',
                'needs_printer_choice': False,
                'printers': [],
                'etikett': et,
                'printer_ip': None,
                'drucker_id': eff_drucker,
                'agent_id': None,
            }
        return {
            'ok': True,
            'error_message': None,
            'needs_printer_choice': False,
            'printers': [],
            'etikett': et,
            'printer_ip': row['ip_address'],
            'drucker_id': eff_drucker,
            'agent_id': row['agent_id'],
        }

    printers = [_printer_to_dict(p) for p in get_active_printers_list(conn)]
    if not printers:
        return {
            'ok': False,
            'error_message': 'Kein Standarddrucker gesetzt und kein aktiver Zebradrucker vorhanden.',
            'needs_printer_choice': False,
            'printers': [],
            'etikett': et,
            'printer_ip': None,
            'drucker_id': None,
            'agent_id': None,
        }
    return {
        'ok': True,
        'error_message': None,
        'needs_printer_choice': True,
        'printers': printers,
        'etikett': et,
        'printer_ip': None,
        'drucker_id': None,
        'agent_id': None,
    }
