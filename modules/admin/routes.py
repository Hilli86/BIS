"""
Admin Routes - Stammdaten-Verwaltung
Mitarbeiter, Abteilungen, Bereiche, Gewerke, Tätigkeiten, Status
"""

import logging

from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash
from . import admin_bp
from utils import get_db_connection, admin_required, menue_zugriff_erforderlich
from utils.zebra_client import (
    dispatch_print,
    send_zpl_to_printer,
    build_test_label,
    zpl_header_from_dimensions,
    merge_zpl_header_base_and_extra,
    zpl_test_label_preview_segments,
)
from utils.etikett_druck import FUNKTIONEN_ADMIN
from utils.helpers import row_to_dict
from utils.menue_definitions import get_alle_menue_definitionen, get_menue_sichtbarkeit_fuer_mitarbeiter
from utils.auth_redirect import LOGIN_STARTSEITEN_AUSWAHL, normalisiere_startseite_endpunkt
from utils.db_sql import upsert_ignore
from modules.wartungen import services as wartungen_services

_log_admin_mqtt = logging.getLogger('bis.admin.mqtt')


def ajax_response(message, success=True, status_code=None, **extra):
    """Hilfsfunktion für AJAX/Standard-Responses (optional zusätzliche JSON-Felder via **extra)."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if status_code is None:
            status_code = 200 if success else 400
        payload = {'success': success, 'message': message}
        payload.update(extra)
        return jsonify(payload), status_code
    else:
        flash(message, 'success' if success else 'danger')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/')
@admin_required
@menue_zugriff_erforderlich('admin')
def dashboard():
    """Admin Dashboard - Übersicht aller Stammdaten"""
    with get_db_connection() as conn:
        mitarbeiter = conn.execute('''
            SELECT m.ID, m.Personalnummer, m.Vorname, m.Nachname, m.Email, m.Handynummer, m.Aktiv,
                   a.Bezeichnung AS PrimaerAbteilung, m.PrimaerAbteilungID,
                   m.StartseiteNachLoginEndpunkt
            FROM Mitarbeiter m
            LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID
            ORDER BY m.Nachname, m.Vorname
        ''').fetchall()
        
        # Alle zusätzlichen Abteilungen in einer Query laden
        mitarbeiter_abteilungen = {}
        if mitarbeiter:
            mitarbeiter_ids = [m['ID'] for m in mitarbeiter]
            placeholders = ','.join(['?'] * len(mitarbeiter_ids))
            abteilungen_rows = conn.execute(f'''
                SELECT MitarbeiterID, AbteilungID
                FROM MitarbeiterAbteilung
                WHERE MitarbeiterID IN ({placeholders})
            ''', mitarbeiter_ids).fetchall()
            
            for row in abteilungen_rows:
                mid = row['MitarbeiterID']
                if mid not in mitarbeiter_abteilungen:
                    mitarbeiter_abteilungen[mid] = []
                mitarbeiter_abteilungen[mid].append(row['AbteilungID'])
        
        # Alle Berechtigungen in einer Query laden
        mitarbeiter_berechtigungen = {}
        if mitarbeiter:
            mitarbeiter_ids = [m['ID'] for m in mitarbeiter]
            placeholders = ','.join(['?'] * len(mitarbeiter_ids))
            berechtigungen_rows = conn.execute(f'''
                SELECT MitarbeiterID, BerechtigungID
                FROM MitarbeiterBerechtigung
                WHERE MitarbeiterID IN ({placeholders})
            ''', mitarbeiter_ids).fetchall()
            
            for row in berechtigungen_rows:
                mid = row['MitarbeiterID']
                if mid not in mitarbeiter_berechtigungen:
                    mitarbeiter_berechtigungen[mid] = []
                mitarbeiter_berechtigungen[mid].append(row['BerechtigungID'])
        
        # Abteilungen hierarchisch laden
        abteilungen = conn.execute('''
            SELECT a.ID, a.Bezeichnung, a.ParentAbteilungID, a.Aktiv, a.Sortierung,
                   p.Bezeichnung AS ParentBezeichnung
            FROM Abteilung a
            LEFT JOIN Abteilung p ON a.ParentAbteilungID = p.ID
            ORDER BY COALESCE(p.Bezeichnung, a.Bezeichnung), a.Bezeichnung
        ''').fetchall()
        
        bereiche = conn.execute('SELECT ID, Bezeichnung, Aktiv FROM Bereich ORDER BY Bezeichnung').fetchall()
        gewerke = conn.execute('''
            SELECT G.ID, G.Bezeichnung, B.Bezeichnung AS Bereich, G.BereichID, G.Aktiv
            FROM Gewerke G
            JOIN Bereich B ON G.BereichID = B.ID
            ORDER BY B.Bezeichnung, G.Bezeichnung
        ''').fetchall()
        taetigkeiten = conn.execute('SELECT ID, Bezeichnung, Sortierung, Aktiv FROM Taetigkeit ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        status = conn.execute('SELECT ID, Bezeichnung, Farbe, Sortierung, Aktiv FROM Status ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        
        # Ersatzteil-Verwaltung
        ersatzteil_kategorien = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM ErsatzteilKategorie ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lieferanten = conn.execute('SELECT ID, Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Website, CsvExportReihenfolge, Aktiv FROM Lieferant WHERE Gelöscht = 0 ORDER BY Name').fetchall()
        fremdfirmen = wartungen_services.list_fremdfirmen(conn, nur_aktiv=False)
        kostenstellen = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Kostenstelle ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lagerorte = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Lagerort ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lagerplaetze = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Lagerplatz ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        
        # Firmendaten laden (nur erste Zeile, sollte nur eine geben)
        firmendaten_row = conn.execute('SELECT * FROM Firmendaten LIMIT 1').fetchone()
        firmendaten = row_to_dict(firmendaten_row) if firmendaten_row else None
        
        # Berechtigungen laden
        berechtigungen = conn.execute('SELECT ID, Schluessel, Bezeichnung, Beschreibung, Aktiv FROM Berechtigung ORDER BY Bezeichnung').fetchall()

        # Menü-Sichtbarkeit pro Mitarbeiter laden
        mitarbeiter_menue_sichtbarkeit = {}
        if mitarbeiter:
            placeholders = ','.join(['?'] * len([m['ID'] for m in mitarbeiter]))
            mitarbeiter_ids = [m['ID'] for m in mitarbeiter]
            sichtbarkeit_rows = conn.execute(f'''
                SELECT MitarbeiterID, MenueSchluessel, Sichtbar
                FROM MitarbeiterMenueSichtbarkeit
                WHERE MitarbeiterID IN ({placeholders})
            ''', mitarbeiter_ids).fetchall()
            for row in sichtbarkeit_rows:
                mid = row['MitarbeiterID']
                if mid not in mitarbeiter_menue_sichtbarkeit:
                    mitarbeiter_menue_sichtbarkeit[mid] = {}
                mitarbeiter_menue_sichtbarkeit[mid][row['MenueSchluessel']] = bool(row['Sichtbar'])
            # Sicherstellen, dass jeder Mitarbeiter einen Eintrag hat (leeres Dict = alles Standard)
            for m in mitarbeiter:
                if m['ID'] not in mitarbeiter_menue_sichtbarkeit:
                    mitarbeiter_menue_sichtbarkeit[m['ID']] = {}

        # Effektive Menü-Sichtbarkeit (wie in der Sidebar) pro Mitarbeiter
        mitarbeiter_menue_effektiv = {}
        for m in mitarbeiter:
            mitarbeiter_menue_effektiv[m['ID']] = get_menue_sichtbarkeit_fuer_mitarbeiter(m['ID'], conn)

        # Zebra-Drucker und Etikettenformate laden
        zebra_printers = conn.execute('''
            SELECT p.id, p.name, p.ip_address, p.description, p.ort, p.active,
                   p.agent_id, a.name AS agent_name
            FROM zebra_printers p
            LEFT JOIN print_agents a ON p.agent_id = a.id
            ORDER BY COALESCE(p.ort, ''), p.name
        ''').fetchall()
        print_agents_list = conn.execute('''
            SELECT id, name, standort, active
            FROM print_agents
            ORDER BY name
        ''').fetchall()
        label_formats = conn.execute('''
            SELECT id, name, description, width_mm, height_mm, orientation, zpl_header, zpl_zusatz
            FROM label_formats
            ORDER BY name
        ''').fetchall()
        
        # Etiketten laden mit zpl_header aus label_formats
        etiketten = conn.execute('''
            SELECT e.id, e.bezeichnung, e.etikettformat_id, e.druckbefehle,
                   lf.zpl_header
            FROM Etikett e
            LEFT JOIN label_formats lf ON e.etikettformat_id = lf.id
            ORDER BY e.bezeichnung
        ''').fetchall()

        druck_konfig_rows = conn.execute('''
            SELECT k.id, k.funktion_code, k.etikett_id, k.drucker_id, k.prioritaet, k.aktiv,
                   e.bezeichnung AS etikett_bezeichnung
            FROM etikett_druck_konfig k
            JOIN Etikett e ON e.id = k.etikett_id
            ORDER BY k.funktion_code, k.prioritaet DESC, k.id
        ''').fetchall()
        konfig_abt = {}
        for row in conn.execute(
            'SELECT konfig_id, abteilung_id FROM etikett_druck_konfig_abteilung'
        ):
            konfig_abt.setdefault(row['konfig_id'], []).append(row['abteilung_id'])
        etikett_druck_konfigen = []
        for r in druck_konfig_rows:
            d = dict(r)
            d['abteilung_ids'] = konfig_abt.get(r['id'], [])
            etikett_druck_konfigen.append(d)

    menue_definitionen = get_alle_menue_definitionen()

    return render_template('admin.html',
                           mitarbeiter=mitarbeiter,
                           mitarbeiter_abteilungen=mitarbeiter_abteilungen,
                           mitarbeiter_berechtigungen=mitarbeiter_berechtigungen,
                           mitarbeiter_menue_sichtbarkeit=mitarbeiter_menue_sichtbarkeit,
                           mitarbeiter_menue_effektiv=mitarbeiter_menue_effektiv,
                           menue_definitionen=menue_definitionen,
                           abteilungen=abteilungen,
                           bereiche=bereiche,
                           gewerke=gewerke,
                           taetigkeiten=taetigkeiten,
                           status=status,
                           ersatzteil_kategorien=ersatzteil_kategorien,
                           lieferanten=lieferanten,
                           fremdfirmen=fremdfirmen,
                           kostenstellen=kostenstellen,
                           lagerorte=lagerorte,
                           lagerplaetze=lagerplaetze,
                           firmendaten=firmendaten,
                           berechtigungen=berechtigungen,
                           zebra_printers=zebra_printers,
                           print_agents_list=print_agents_list,
                           label_formats=label_formats,
                           etiketten=etiketten,
                           etikett_druck_konfigen=etikett_druck_konfigen,
                           druck_funktionen=FUNKTIONEN_ADMIN,
                           login_startseiten_auswahl=LOGIN_STARTSEITEN_AUSWAHL)


# ========== Zebra-Drucker Verwaltung ==========

@admin_bp.route('/zebra/printers', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_printer_save():
    """
    Zebra-Drucker anlegen oder aktualisieren.
    Wenn eine ID übergeben wird, wird aktualisiert, sonst neu angelegt.
    """
    printer_id = request.form.get('id')
    name = request.form.get('name', '').strip()
    ip_address = request.form.get('ip_address', '').strip()
    description = request.form.get('description', '').strip() or None
    ort = request.form.get('ort', '').strip() or None
    active = 1 if request.form.get('active') == 'on' else 0
    agent_raw = (request.form.get('agent_id') or '').strip()
    agent_id = int(agent_raw) if agent_raw else None

    if not name or not ip_address:
        return ajax_response('Bitte Name und IP-Adresse ausfüllen.', success=False)

    try:
        with get_db_connection() as conn:
            if agent_id is not None:
                ag = conn.execute(
                    'SELECT id FROM print_agents WHERE id = ?', (agent_id,)
                ).fetchone()
                if not ag:
                    return ajax_response('Druck-Agent nicht gefunden.', success=False)
            if printer_id:
                conn.execute('''
                    UPDATE zebra_printers
                    SET name = ?, ip_address = ?, description = ?, ort = ?, active = ?,
                        agent_id = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (name, ip_address, description, ort, active, agent_id, printer_id))
            else:
                conn.execute('''
                    INSERT INTO zebra_printers
                        (name, ip_address, description, ort, active, agent_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (name, ip_address, description, ort, active, agent_id))
            conn.commit()
        return ajax_response('Zebra-Drucker gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern des Druckers: {str(e)}', success=False, status_code=500)


@admin_bp.route('/zebra/printers/toggle/<int:pid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_printer_toggle(pid):
    """Aktiv-Status eines Zebra-Druckers umschalten."""
    try:
        with get_db_connection() as conn:
            row = conn.execute('SELECT active FROM zebra_printers WHERE id = ?', (pid,)).fetchone()
            if not row:
                return ajax_response('Drucker nicht gefunden.', success=False, status_code=404)
            new_active = 0 if row['active'] else 1
            conn.execute('UPDATE zebra_printers SET active = ?, updated_at = datetime(\'now\') WHERE id = ?', (new_active, pid))
            conn.commit()
        return ajax_response('Zebra-Drucker-Status aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Aktualisieren des Druckerstatus: {str(e)}', success=False, status_code=500)


# ========== Druck-Agents Verwaltung ==========

@admin_bp.route('/druck-agents', methods=['GET'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_agents')
def druck_agents_uebersicht():
    """Verwaltung der Druck-Agents (Cloudflare-Tunnel-Helfer pro Standort)."""
    from utils.zebra_client import generate_agent_token  # noqa: F401 (dokumentation)
    one_time_token = request.args.get('neuer_token') or None
    one_time_token_for_id = request.args.get('neuer_token_id', type=int)
    with get_db_connection() as conn:
        agents = conn.execute('''
            SELECT a.id, a.name, a.standort, a.active, a.last_seen_at, a.last_ip,
                   a.created_at, a.updated_at,
                   (SELECT COUNT(*) FROM zebra_printers p WHERE p.agent_id = a.id) AS drucker_anzahl,
                   (SELECT COUNT(*) FROM print_jobs j WHERE j.agent_id = a.id AND j.status = 'pending') AS jobs_pending,
                   (SELECT COUNT(*) FROM print_jobs j WHERE j.agent_id = a.id AND j.status = 'leased') AS jobs_leased
            FROM print_agents a
            ORDER BY a.name
        ''').fetchall()
    return render_template(
        'admin_druck_agents.html',
        agents=agents,
        neuer_token=one_time_token,
        neuer_token_id=one_time_token_for_id,
    )


@admin_bp.route('/druck-agents/save', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_agents')
def druck_agents_save():
    """Druck-Agent anlegen oder aktualisieren. Beim Anlegen wird ein Token erzeugt."""
    from utils.zebra_client import generate_agent_token, hash_agent_token

    aid = request.form.get('id', type=int)
    name = (request.form.get('name') or '').strip()
    standort = (request.form.get('standort') or '').strip() or None
    active = 1 if request.form.get('active') == 'on' else 0

    if not name:
        flash('Bitte einen Namen für den Agent angeben.', 'danger')
        return redirect(url_for('admin.druck_agents_uebersicht'))

    try:
        with get_db_connection() as conn:
            doppelt = conn.execute(
                'SELECT id FROM print_agents WHERE name = ? AND id IS NOT ?',
                (name, aid),
            ).fetchone()
            if doppelt:
                flash(f'Es existiert bereits ein Agent mit dem Namen "{name}".', 'danger')
                return redirect(url_for('admin.druck_agents_uebersicht'))
            if aid:
                conn.execute(
                    '''UPDATE print_agents
                          SET name = ?, standort = ?, active = ?, updated_at = datetime('now')
                        WHERE id = ?''',
                    (name, standort, active, aid),
                )
                conn.commit()
                flash(f'Druck-Agent "{name}" aktualisiert.', 'success')
                return redirect(url_for('admin.druck_agents_uebersicht'))
            new_token = generate_agent_token()
            cur = conn.execute(
                '''INSERT INTO print_agents
                       (name, standort, token_hash, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))''',
                (name, standort, hash_agent_token(new_token), active),
            )
            conn.commit()
            new_id = cur.lastrowid
            flash(
                f'Druck-Agent "{name}" angelegt. Bitte Token JETZT sichern '
                f'(wird nur einmal angezeigt).',
                'success',
            )
            return redirect(url_for(
                'admin.druck_agents_uebersicht',
                neuer_token=new_token,
                neuer_token_id=new_id,
            ))
    except Exception as e:
        flash(f'Fehler beim Speichern des Agents: {e}', 'danger')
        return redirect(url_for('admin.druck_agents_uebersicht'))


@admin_bp.route('/druck-agents/<int:aid>/rotate-token', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_agents')
def druck_agents_rotate_token(aid):
    """Erzeugt einen neuen Token (alter wird ungueltig). Token wird einmalig angezeigt."""
    from utils.zebra_client import generate_agent_token, hash_agent_token
    try:
        with get_db_connection() as conn:
            row = conn.execute('SELECT id, name FROM print_agents WHERE id = ?', (aid,)).fetchone()
            if not row:
                flash('Agent nicht gefunden.', 'danger')
                return redirect(url_for('admin.druck_agents_uebersicht'))
            new_token = generate_agent_token()
            conn.execute(
                '''UPDATE print_agents
                      SET token_hash = ?, updated_at = datetime('now')
                    WHERE id = ?''',
                (hash_agent_token(new_token), aid),
            )
            conn.commit()
            flash(f'Neuer Token fuer "{row["name"]}" erzeugt.', 'success')
            return redirect(url_for(
                'admin.druck_agents_uebersicht',
                neuer_token=new_token,
                neuer_token_id=aid,
            ))
    except Exception as e:
        flash(f'Fehler beim Rotieren des Tokens: {e}', 'danger')
        return redirect(url_for('admin.druck_agents_uebersicht'))


@admin_bp.route('/druck-agents/<int:aid>/toggle', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_agents')
def druck_agents_toggle(aid):
    """Aktiviert/Deaktiviert einen Druck-Agent."""
    try:
        with get_db_connection() as conn:
            row = conn.execute('SELECT active FROM print_agents WHERE id = ?', (aid,)).fetchone()
            if not row:
                flash('Agent nicht gefunden.', 'danger')
                return redirect(url_for('admin.druck_agents_uebersicht'))
            conn.execute(
                '''UPDATE print_agents
                      SET active = ?, updated_at = datetime('now')
                    WHERE id = ?''',
                (0 if row['active'] else 1, aid),
            )
            conn.commit()
        return redirect(url_for('admin.druck_agents_uebersicht'))
    except Exception as e:
        flash(f'Fehler: {e}', 'danger')
        return redirect(url_for('admin.druck_agents_uebersicht'))


# ========== Druck-Queue (Auftragsuebersicht) ==========

@admin_bp.route('/druck-queue', methods=['GET'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_queue')
def druck_queue_uebersicht():
    """Uebersicht der Druckauftraege (offene, fehlerhafte, erledigte)."""
    from utils.zebra_client import recover_expired_leases
    status_filter = (request.args.get('status') or 'aktiv').strip()
    agent_filter = request.args.get('agent_id', type=int)

    where = []
    params = []
    if status_filter == 'aktiv':
        where.append("j.status IN ('pending', 'leased', 'error')")
    elif status_filter and status_filter != 'alle':
        where.append('j.status = ?')
        params.append(status_filter)
    if agent_filter:
        where.append('j.agent_id = ?')
        params.append(agent_filter)
    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''

    with get_db_connection() as conn:
        recover_expired_leases(conn)
        agents = conn.execute(
            'SELECT id, name, standort FROM print_agents ORDER BY name'
        ).fetchall()
        jobs = conn.execute(f'''
            SELECT j.id, j.agent_id, j.drucker_id, j.status, j.attempts, j.lease_until,
                   j.error_message, j.created_at, j.completed_at,
                   a.name AS agent_name, p.name AS drucker_name, p.ip_address AS drucker_ip,
                   m.Personalnummer AS erstellt_von_pn, m.Vorname AS erstellt_von_vn, m.Nachname AS erstellt_von_nn
              FROM print_jobs j
              JOIN print_agents a ON j.agent_id = a.id
              JOIN zebra_printers p ON j.drucker_id = p.id
              LEFT JOIN Mitarbeiter m ON m.ID = j.created_by_mitarbeiter_id
            {where_sql}
             ORDER BY j.created_at DESC
             LIMIT 500
        ''', params).fetchall()
    return render_template(
        'admin_druck_queue.html',
        jobs=jobs,
        agents=agents,
        status_filter=status_filter,
        agent_filter=agent_filter,
    )


@admin_bp.route('/druck-queue/<int:job_id>/requeue', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_queue')
def druck_queue_requeue(job_id):
    """Setzt einen Auftrag zurueck auf pending (z. B. nach Fehler)."""
    try:
        with get_db_connection() as conn:
            cur = conn.execute(
                '''UPDATE print_jobs
                      SET status = 'pending', error_message = NULL,
                          lease_until = NULL, completed_at = NULL
                    WHERE id = ? AND status IN ('error', 'leased', 'expired')''',
                (job_id,),
            )
            conn.commit()
        if cur.rowcount == 0:
            flash('Auftrag konnte nicht erneut zugestellt werden.', 'warning')
        else:
            flash('Auftrag wurde erneut in die Warteschlange gestellt.', 'success')
    except Exception as e:
        flash(f'Fehler: {e}', 'danger')
    return redirect(url_for(
        'admin.druck_queue_uebersicht',
        status=request.args.get('status') or 'aktiv',
    ))


@admin_bp.route('/druck-queue/<int:job_id>/abbrechen', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_druck_queue')
def druck_queue_abbrechen(job_id):
    """Bricht einen wartenden Auftrag ab (Status = expired)."""
    try:
        with get_db_connection() as conn:
            cur = conn.execute(
                '''UPDATE print_jobs
                      SET status = 'expired', completed_at = datetime('now'),
                          error_message = COALESCE(error_message, 'Manuell abgebrochen')
                    WHERE id = ? AND status IN ('pending', 'leased', 'error')''',
                (job_id,),
            )
            conn.commit()
        if cur.rowcount == 0:
            flash('Auftrag konnte nicht abgebrochen werden.', 'warning')
        else:
            flash('Auftrag wurde abgebrochen.', 'success')
    except Exception as e:
        flash(f'Fehler: {e}', 'danger')
    return redirect(url_for(
        'admin.druck_queue_uebersicht',
        status=request.args.get('status') or 'aktiv',
    ))


# ========== Etikettenformate Verwaltung ==========

@admin_bp.route('/zebra/labels', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_label_save():
    """
    Etikettenformat anlegen oder aktualisieren.
    Wenn eine ID übergeben wird, wird aktualisiert, sonst neu angelegt.
    """
    label_id = request.form.get('id')
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip() or None
    width_mm = request.form.get('width_mm', type=int)
    height_mm = request.form.get('height_mm', type=int)
    zpl_zusatz = request.form.get('zpl_zusatz', '').strip() or None
    orientation = 'portrait'

    if not name or not width_mm or not height_mm:
        return ajax_response('Bitte Name, Breite und Höhe ausfüllen.', success=False)

    base = zpl_header_from_dimensions(width_mm, height_mm)
    zpl_header = merge_zpl_header_base_and_extra(base, zpl_zusatz)

    try:
        with get_db_connection() as conn:
            if label_id:
                conn.execute('''
                    UPDATE label_formats
                    SET name = ?, description = ?, width_mm = ?, height_mm = ?, orientation = ?, zpl_header = ?, zpl_zusatz = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (name, description, width_mm, height_mm, orientation, zpl_header, zpl_zusatz, label_id))
            else:
                conn.execute('''
                    INSERT INTO label_formats (name, description, width_mm, height_mm, orientation, zpl_header, zpl_zusatz, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (name, description, width_mm, height_mm, orientation, zpl_header, zpl_zusatz))
            conn.commit()
        return ajax_response('Etikettenformat gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern des Etikettenformats: {str(e)}', success=False, status_code=500)


@admin_bp.route('/zebra/label-format/preview', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_label_format_preview():
    """Vorschau-ZPL für ein Etikettenformat aus Maßen und optionalem ZPL-Zusatz (ohne DB-Zugriff)."""
    width_mm = request.form.get('width_mm', type=int)
    height_mm = request.form.get('height_mm', type=int)
    zpl_zusatz = request.form.get('zpl_zusatz', '').strip() or None
    label_name = request.form.get('name', '').strip() or None
    if not width_mm or not height_mm:
        return ajax_response('Breite und Höhe sind erforderlich.', success=False)
    try:
        base = zpl_header_from_dimensions(width_mm, height_mm)
        header = merge_zpl_header_base_and_extra(base, zpl_zusatz)
        segs = zpl_test_label_preview_segments(header, label_name)
        return ajax_response(
            'OK',
            zpl=segs['full'],
            zpl_xa=segs['xa'],
            zpl_format_teil=segs['format'],
            zpl_vorschau_teil=segs['demo'],
        )
    except Exception as e:
        return ajax_response(f'Vorschau nicht möglich: {str(e)}', success=False, status_code=500)


# ========== Zebra-Testdruck ==========

@admin_bp.route('/zebra/test', methods=['GET', 'POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_test():
    """
    Testseite für Zebra-Drucker:
    - GET: Formular mit Auswahl Drucker + Etikettenformat
    - POST: Testetikett drucken
    """
    with get_db_connection() as conn:
        printers = conn.execute('''
            SELECT id, name, ip_address, active
            FROM zebra_printers
            ORDER BY name
        ''').fetchall()
        labels = conn.execute('''
            SELECT id, name, zpl_header
            FROM label_formats
            ORDER BY name
        ''').fetchall()

        if request.method == 'POST':
            printer_id = request.form.get('printer_id', type=int)
            label_id = request.form.get('label_id', type=int)

            if not printer_id or not label_id:
                flash('Bitte Drucker und Etikettenformat auswählen.', 'danger')
                return redirect(url_for('admin.zebra_test'))

            printer = conn.execute('SELECT * FROM zebra_printers WHERE id = ?', (printer_id,)).fetchone()
            label = conn.execute('SELECT * FROM label_formats WHERE id = ?', (label_id,)).fetchone()

            if not printer or not label:
                flash('Ausgewählter Drucker oder Etikettenformat nicht gefunden.', 'danger')
                return redirect(url_for('admin.zebra_test'))

            zpl = build_test_label(label['zpl_header'], label['name'])

            try:
                d = dispatch_print(conn, int(printer['id']), zpl)
                if d['ok']:
                    if d['mode'] == 'agent' and d['status'] != 'done':
                        flash(
                            f"Testetikett '{label['name']}' an Druckwarteschlange "
                            f"uebergeben (Auftrag #{d['job_id']}).",
                            'success',
                        )
                    else:
                        flash(
                            f"Testetikett '{label['name']}' an Drucker "
                            f"'{printer['name']}' gesendet.",
                            'success',
                        )
                else:
                    flash(
                        f"Fehler beim Senden an den Drucker: "
                        f"{d.get('error_message') or 'unbekannt'}",
                        'danger',
                    )
            except Exception as e:
                flash(f"Fehler beim Senden an den Drucker: {e}", 'danger')

            return redirect(url_for('admin.zebra_test'))

    return render_template('admin_zebra_test.html', printers=printers, labels=labels)


# ========== Etiketten-Verwaltung ==========

@admin_bp.route('/zebra/etiketten/save', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_etikett_save():
    """
    Etikett anlegen oder aktualisieren.
    Wenn eine ID übergeben wird, wird aktualisiert, sonst neu angelegt.
    """
    etikett_id = request.form.get('id')
    bezeichnung = request.form.get('bezeichnung', '').strip()
    etikettformat_id = request.form.get('etikettformat_id', type=int)
    druckbefehle = request.form.get('druckbefehle', '').strip()

    if not bezeichnung or not etikettformat_id or not druckbefehle:
        return ajax_response('Bitte Bezeichnung, Format und Druckbefehle ausfüllen.', success=False)

    try:
        with get_db_connection() as conn:
            label_format = conn.execute('SELECT id FROM label_formats WHERE id = ?', (etikettformat_id,)).fetchone()
            if not label_format:
                return ajax_response('Ausgewähltes Etikettenformat nicht gefunden.', success=False)

            if not etikett_id:
                existing = conn.execute(
                    'SELECT id FROM Etikett WHERE bezeichnung = ? LIMIT 1',
                    (bezeichnung,)
                ).fetchone()
                if existing:
                    etikett_id = existing['id']

            if etikett_id:
                conn.execute('''
                    UPDATE Etikett
                    SET bezeichnung = ?, etikettformat_id = ?, druckbefehle = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (bezeichnung, etikettformat_id, druckbefehle, etikett_id))
            else:
                conn.execute('''
                    INSERT INTO Etikett (bezeichnung, etikettformat_id, druckbefehle, created_at, updated_at)
                    VALUES (?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (bezeichnung, etikettformat_id, druckbefehle))
            conn.commit()
        return ajax_response('Etikett gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern des Etiketts: {str(e)}', success=False, status_code=500)


@admin_bp.route('/zebra/druck_konfig/save', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_druck_konfig_save():
    """Druckfunktion-Konfiguration anlegen oder aktualisieren."""
    kid = request.form.get('id', type=int)
    funktion_code = request.form.get('funktion_code', '').strip()
    etikett_id = request.form.get('etikett_id', type=int)
    drucker_raw = request.form.get('drucker_id', '').strip()
    drucker_id = int(drucker_raw) if drucker_raw else None
    prioritaet = request.form.get('prioritaet', type=int)
    if prioritaet is None:
        prioritaet = 0
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    abteilung_ids = []
    for x in request.form.getlist('abteilung_ids'):
        try:
            abteilung_ids.append(int(x))
        except (TypeError, ValueError):
            pass

    if not funktion_code or not etikett_id:
        return ajax_response('Funktion und Etikett sind erforderlich.', success=False)

    try:
        with get_db_connection() as conn:
            et = conn.execute('SELECT id FROM Etikett WHERE id = ?', (etikett_id,)).fetchone()
            if not et:
                return ajax_response('Etikett nicht gefunden.', success=False)
            if drucker_id is not None:
                pr = conn.execute('SELECT id FROM zebra_printers WHERE id = ?', (drucker_id,)).fetchone()
                if not pr:
                    return ajax_response('Drucker nicht gefunden.', success=False)

            if kid:
                conn.execute('''
                    UPDATE etikett_druck_konfig
                    SET funktion_code = ?, etikett_id = ?, drucker_id = ?, prioritaet = ?, aktiv = ?,
                        updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (funktion_code, etikett_id, drucker_id, prioritaet, aktiv, kid))
            else:
                ins = conn.execute('''
                    INSERT INTO etikett_druck_konfig (funktion_code, etikett_id, drucker_id, prioritaet, aktiv, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (funktion_code, etikett_id, drucker_id, prioritaet, aktiv))
                kid = ins.lastrowid

            conn.execute('DELETE FROM etikett_druck_konfig_abteilung WHERE konfig_id = ?', (kid,))
            for aid in abteilung_ids:
                conn.execute('''
                    INSERT INTO etikett_druck_konfig_abteilung (konfig_id, abteilung_id) VALUES (?, ?)
                ''', (kid, aid))
            conn.commit()
        return ajax_response('Druckkonfiguration gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern: {str(e)}', success=False, status_code=500)


@admin_bp.route('/zebra/druck_konfig/delete/<int:kid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_druck_konfig_delete(kid):
    try:
        with get_db_connection() as conn:
            conn.execute('DELETE FROM etikett_druck_konfig_abteilung WHERE konfig_id = ?', (kid,))
            conn.execute('DELETE FROM etikett_druck_konfig WHERE id = ?', (kid,))
            conn.commit()
        return ajax_response('Druckkonfiguration gelöscht.')
    except Exception as e:
        return ajax_response(f'Fehler beim Löschen: {str(e)}', success=False, status_code=500)


@admin_bp.route('/zebra/etiketten/testdruck', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def zebra_etikett_testdruck():
    """
    Testdruck eines Etiketts - sendet ZPL ueber Hybrid-Dispatch (Drucker mit
    agent_id gehen ueber die Queue, sonst Direkt-TCP).
    """
    try:
        data = request.get_json()
        zpl = data.get('zpl', '').strip()
        ip_address = data.get('ip_address', '').strip()
        
        if not zpl:
            return ajax_response('Kein ZPL-Code übermittelt.', success=False)
        
        if not ip_address:
            return ajax_response('Keine Drucker-IP-Adresse übermittelt.', success=False)

        with get_db_connection() as conn:
            row = conn.execute(
                'SELECT id FROM zebra_printers WHERE ip_address = ? AND active = 1 LIMIT 1',
                (ip_address,),
            ).fetchone()
            if row:
                d = dispatch_print(conn, int(row['id']), zpl)
                if not d['ok']:
                    return ajax_response(
                        f"Fehler beim Drucken: {d.get('error_message') or 'unbekannt'}",
                        success=False, status_code=500,
                    )
                if d['mode'] == 'agent' and d['status'] != 'done':
                    return ajax_response(
                        f"Etikett an Druckwarteschlange uebergeben (Auftrag #{d['job_id']})."
                    )
                return ajax_response('Etikett erfolgreich gedruckt.')

        send_zpl_to_printer(ip_address, zpl)
        return ajax_response('Etikett erfolgreich gedruckt.')
    except Exception as e:
        return ajax_response(f'Fehler beim Drucken: {str(e)}', success=False, status_code=500)


# ========== Mitarbeiter-Verwaltung ==========

@admin_bp.route('/mitarbeiter/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_add():
    """Mitarbeiter anlegen"""
    personalnummer = request.form.get('personalnummer')
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    email = request.form.get('email', '').strip() or None
    handynummer = request.form.get('handynummer', '').strip() or None
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    startseite_ep = normalisiere_startseite_endpunkt(request.form.get('startseite_nach_login'))
    
    if not personalnummer or not vorname or not nachname:
        return ajax_response('Bitte Personalnummer, Vorname und Nachname ausfüllen.', success=False)
    
    from utils.security import validate_passwort_policy, generiere_zufalls_passwort
    try:
        if passwort:
            policy_fehler = validate_passwort_policy(passwort)
            if policy_fehler:
                return ajax_response(policy_fehler, success=False)
            initial_passwort = passwort
            wechsel_erforderlich = 1
            passwort_hinweis = 'Das Passwort muss beim ersten Login geändert werden.'
        else:
            initial_passwort = generiere_zufalls_passwort()
            wechsel_erforderlich = 1
            passwort_hinweis = (
                f'Initial-Passwort (einmalig): {initial_passwort} – '
                'muss beim ersten Login geändert werden.'
            )

        passwort_hash = generate_password_hash(initial_passwort)
        with get_db_connection() as conn:
            try:
                conn.execute(
                    '''INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Email, Handynummer, Aktiv, Passwort,
                       StartseiteNachLoginEndpunkt, PasswortWechselErforderlich) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (personalnummer, vorname, nachname, email, handynummer, aktiv, passwort_hash, startseite_ep, wechsel_erforderlich),
                )
            except Exception:
                conn.execute(
                    '''INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Email, Handynummer, Aktiv, Passwort,
                       StartseiteNachLoginEndpunkt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (personalnummer, vorname, nachname, email, handynummer, aktiv, passwort_hash, startseite_ep),
                )
            conn.commit()
        return ajax_response(f'Mitarbeiter erfolgreich angelegt. {passwort_hinweis}')
    except Exception as e:
        return ajax_response(f'Fehler beim Anlegen: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/update/<int:mid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_update(mid):
    """Mitarbeiter aktualisieren"""
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    email = request.form.get('email', '').strip() or None
    handynummer = request.form.get('handynummer', '').strip() or None
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    startseite_ep = normalisiere_startseite_endpunkt(request.form.get('startseite_nach_login'))
    from utils.security import validate_passwort_policy
    try:
        if passwort:
            policy_fehler = validate_passwort_policy(passwort)
            if policy_fehler:
                return ajax_response(policy_fehler, success=False)
        with get_db_connection() as conn:
            conn.execute(
                '''UPDATE Mitarbeiter SET Vorname = ?, Nachname = ?, Email = ?, Handynummer = ?, Aktiv = ?,
                   StartseiteNachLoginEndpunkt = ? WHERE ID = ?''',
                (vorname, nachname, email, handynummer, aktiv, startseite_ep, mid),
            )
            if passwort:
                passwort_hash = generate_password_hash(passwort)
                try:
                    conn.execute(
                        'UPDATE Mitarbeiter SET Passwort = ?, PasswortWechselErforderlich = 1 WHERE ID = ?',
                        (passwort_hash, mid),
                    )
                except Exception:
                    conn.execute(
                        'UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?',
                        (passwort_hash, mid),
                    )
            conn.commit()
        return ajax_response('Mitarbeiter aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/deactivate/<int:mid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_deactivate(mid):
    """Mitarbeiter deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Mitarbeiter SET Aktiv = 0 WHERE ID = ?', (mid,))
            conn.commit()
        return ajax_response('Mitarbeiter deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/reset-password/<int:mid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_reset_password(mid):
    """Passwort des Mitarbeiters auf ein Zufalls-Passwort zuruecksetzen (Wechsel-Zwang)."""
    from utils.security import generiere_zufalls_passwort
    try:
        with get_db_connection() as conn:
            mitarbeiter = conn.execute(
                'SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?',
                (mid,)
            ).fetchone()

            if not mitarbeiter:
                return ajax_response('Mitarbeiter nicht gefunden.', success=False, status_code=404)

            vorname = mitarbeiter['Vorname']
            nachname = mitarbeiter['Nachname']

            neues_passwort = generiere_zufalls_passwort()
            neues_passwort_hash = generate_password_hash(neues_passwort)
            try:
                conn.execute(
                    'UPDATE Mitarbeiter SET Passwort = ?, PasswortWechselErforderlich = 1 WHERE ID = ?',
                    (neues_passwort_hash, mid),
                )
            except Exception:
                conn.execute(
                    'UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?',
                    (neues_passwort_hash, mid),
                )
            conn.commit()

        return ajax_response(
            f'Passwort für {vorname} {nachname} zurückgesetzt. '
            f'Einmal-Passwort: {neues_passwort} – muss beim nächsten Login geändert werden.'
        )
    except Exception as e:
        return ajax_response(f'Fehler beim Zurücksetzen: {str(e)}', success=False, status_code=500)


# ========== Abteilungs-Verwaltung ==========

@admin_bp.route('/abteilung/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def abteilung_add():
    """Abteilung anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    parent_id = request.form.get('parent_abteilung_id')
    sortierung = request.form.get('sortierung', type=int) or 0
    
    if parent_id == '' or parent_id is None:
        parent_id = None
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) VALUES (?, ?, 1, ?)', 
                         (bezeichnung, parent_id, sortierung))
            conn.commit()
        return ajax_response('Abteilung erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/abteilung/update/<int:aid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def abteilung_update(aid):
    """Abteilung aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    parent_id = request.form.get('parent_abteilung_id')
    sortierung = request.form.get('sortierung', type=int) or 0
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if parent_id == '' or parent_id is None:
        parent_id = None
    
    # Verhindern, dass eine Abteilung ihr eigener Parent wird
    if parent_id and int(parent_id) == aid:
        return ajax_response('Eine Abteilung kann nicht ihre eigene Überabteilung sein.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Abteilung SET Bezeichnung = ?, ParentAbteilungID = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', 
                         (bezeichnung, parent_id, sortierung, aktiv, aid))
            conn.commit()
        return ajax_response('Abteilung aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/abteilung/delete/<int:aid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def abteilung_delete(aid):
    """Abteilung deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Abteilung SET Aktiv = 0 WHERE ID = ?', (aid,))
            conn.commit()
        return ajax_response('Abteilung deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Mitarbeiter-Abteilungen Verwaltung ==========

@admin_bp.route('/mitarbeiter/<int:mid>/abteilungen', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_abteilungen(mid):
    """Mitarbeiter-Abteilungen zuweisen"""
    primaer_abteilung_id = request.form.get('primaer_abteilung_id')
    zusaetzliche_ids = request.form.getlist('zusaetzliche_abteilungen')
    
    # Leere Strings in None konvertieren
    if primaer_abteilung_id == '' or primaer_abteilung_id is None:
        primaer_abteilung_id = None
    
    try:
        with get_db_connection() as conn:
            # Primärabteilung setzen
            conn.execute('UPDATE Mitarbeiter SET PrimaerAbteilungID = ? WHERE ID = ?', 
                         (primaer_abteilung_id, mid))
            
            # Alte zusätzliche Abteilungen löschen
            conn.execute('DELETE FROM MitarbeiterAbteilung WHERE MitarbeiterID = ?', (mid,))

            # Neue zusätzliche Abteilungen hinzufügen (Duplikate werden per UNIQUE-Constraint ignoriert)
            abteilung_upsert_sql = upsert_ignore(
                'MitarbeiterAbteilung',
                ('MitarbeiterID', 'AbteilungID'),
                ('MitarbeiterID', 'AbteilungID'),
            )
            for abt_id in zusaetzliche_ids:
                if abt_id and abt_id != '' and abt_id != str(primaer_abteilung_id):
                    conn.execute(abteilung_upsert_sql, (mid, abt_id))
            
            conn.commit()
        return ajax_response('Mitarbeiter-Abteilungen aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Bereich-Verwaltung ==========

@admin_bp.route('/bereich/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def bereich_add():
    """Bereich anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Bereich (Bezeichnung, Aktiv) VALUES (?, 1)', (bezeichnung,))
            conn.commit()
        return ajax_response('Bereich erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/bereich/update/<int:bid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def bereich_update(bid):
    """Bereich aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Bereich SET Bezeichnung = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, aktiv, bid))
            conn.commit()
        return ajax_response('Bereich aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/bereich/delete/<int:bid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def bereich_delete(bid):
    """Bereich deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Bereich SET Aktiv = 0 WHERE ID = ?', (bid,))
            conn.commit()
        return ajax_response('Bereich deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Gewerk-Verwaltung ==========

@admin_bp.route('/gewerk/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def gewerk_add():
    """Gewerk anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    bereich_id = request.form.get('bereich_id')
    if not bezeichnung or not bereich_id:
        return ajax_response('Bezeichnung und Bereich erforderlich.', success=False)
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Gewerke (Bezeichnung, BereichID, Aktiv) VALUES (?, ?, 1)', (bezeichnung, bereich_id))
            conn.commit()
        return ajax_response('Gewerk erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/gewerk/update/<int:gid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def gewerk_update(gid):
    """Gewerk aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    bereich_id = request.form.get('bereich_id')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Gewerke SET Bezeichnung = ?, BereichID = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, bereich_id, aktiv, gid))
            conn.commit()
        return ajax_response('Gewerk aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/gewerk/delete/<int:gid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def gewerk_delete(gid):
    """Gewerk deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Gewerke SET Aktiv = 0 WHERE ID = ?', (gid,))
            conn.commit()
        return ajax_response('Gewerk deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Tätigkeit-Verwaltung ==========

@admin_bp.route('/taetigkeit/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def taetigkeit_add():
    """Tätigkeit anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    sortierung = request.form.get('sortierung', type=int)
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Taetigkeit (Bezeichnung, Sortierung, Aktiv) VALUES (?, ?, 1)', (bezeichnung, sortierung))
            conn.commit()
        return ajax_response('Tätigkeit erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/taetigkeit/update/<int:tid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def taetigkeit_update(tid):
    """Tätigkeit aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    sortierung = request.form.get('sortierung', type=int)
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Taetigkeit SET Bezeichnung = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, sortierung, aktiv, tid))
            conn.commit()
        return ajax_response('Tätigkeit aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/taetigkeit/delete/<int:tid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def taetigkeit_delete(tid):
    """Tätigkeit deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Taetigkeit SET Aktiv = 0 WHERE ID = ?', (tid,))
            conn.commit()
        return ajax_response('Tätigkeit deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Status-Verwaltung ==========

@admin_bp.route('/status/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def status_add():
    """Status anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    farbe = request.form.get('farbe')
    sortierung = request.form.get('sortierung', type=int)
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Status (Bezeichnung, Farbe, Sortierung, Aktiv) VALUES (?, ?, ?, 1)', (bezeichnung, farbe, sortierung))
            conn.commit()
        return ajax_response('Status erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/status/update/<int:sid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def status_update(sid):
    """Status aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    farbe = request.form.get('farbe')
    sortierung = request.form.get('sortierung', type=int)
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Status SET Bezeichnung = ?, Farbe = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, farbe, sortierung, aktiv, sid))
            conn.commit()
        return ajax_response('Status aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/status/delete/<int:sid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def status_delete(sid):
    """Status deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Status SET Aktiv = 0 WHERE ID = ?', (sid,))
            conn.commit()
        return ajax_response('Status deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== ErsatzteilKategorie-Verwaltung ==========

@admin_bp.route('/ersatzteil-kategorie/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def ersatzteil_kategorie_add():
    """ErsatzteilKategorie anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO ErsatzteilKategorie (Bezeichnung, Beschreibung, Aktiv, Sortierung) VALUES (?, ?, 1, ?)', 
                         (bezeichnung, beschreibung, sortierung))
            conn.commit()
        return ajax_response('Kategorie erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/ersatzteil-kategorie/update/<int:kid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def ersatzteil_kategorie_update(kid):
    """ErsatzteilKategorie aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE ErsatzteilKategorie SET Bezeichnung = ?, Beschreibung = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', 
                         (bezeichnung, beschreibung, sortierung, aktiv, kid))
            conn.commit()
        return ajax_response('Kategorie aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/ersatzteil-kategorie/delete/<int:kid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def ersatzteil_kategorie_delete(kid):
    """ErsatzteilKategorie deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE ErsatzteilKategorie SET Aktiv = 0 WHERE ID = ?', (kid,))
            conn.commit()
        return ajax_response('Kategorie deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Kostenstelle-Verwaltung ==========

@admin_bp.route('/kostenstelle/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def kostenstelle_add():
    """Kostenstelle anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Kostenstelle (Bezeichnung, Beschreibung, Aktiv, Sortierung) VALUES (?, ?, 1, ?)', 
                         (bezeichnung, beschreibung, sortierung))
            conn.commit()
        return ajax_response('Kostenstelle erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/kostenstelle/update/<int:kid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def kostenstelle_update(kid):
    """Kostenstelle aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Kostenstelle SET Bezeichnung = ?, Beschreibung = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', 
                         (bezeichnung, beschreibung, sortierung, aktiv, kid))
            conn.commit()
        return ajax_response('Kostenstelle aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/kostenstelle/delete/<int:kid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def kostenstelle_delete(kid):
    """Kostenstelle deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Kostenstelle SET Aktiv = 0 WHERE ID = ?', (kid,))
            conn.commit()
        return ajax_response('Kostenstelle deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Lagerort-Verwaltung ==========

@admin_bp.route('/lagerort/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lagerort_add():
    """Lagerort anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Lagerort (Bezeichnung, Beschreibung, Aktiv, Sortierung) VALUES (?, ?, 1, ?)', 
                         (bezeichnung, beschreibung, sortierung))
            conn.commit()
        return ajax_response('Lagerort erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lagerort/update/<int:lid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lagerort_update(lid):
    """Lagerort aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lagerort SET Bezeichnung = ?, Beschreibung = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', 
                         (bezeichnung, beschreibung, sortierung, aktiv, lid))
            conn.commit()
        return ajax_response('Lagerort aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lagerort/delete/<int:lid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lagerort_delete(lid):
    """Lagerort deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lagerort SET Aktiv = 0 WHERE ID = ?', (lid,))
            conn.commit()
        return ajax_response('Lagerort deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Lagerplatz-Verwaltung ==========

@admin_bp.route('/lagerplatz/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lagerplatz_add():
    """Lagerplatz anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Lagerplatz (Bezeichnung, Beschreibung, Aktiv, Sortierung) VALUES (?, ?, 1, ?)', 
                         (bezeichnung, beschreibung, sortierung))
            conn.commit()
        return ajax_response('Lagerplatz erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lagerplatz/update/<int:lid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lagerplatz_update(lid):
    """Lagerplatz aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    beschreibung = request.form.get('beschreibung', '')
    sortierung = request.form.get('sortierung', type=int) or 0
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not bezeichnung:
        return ajax_response('Bezeichnung erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lagerplatz SET Bezeichnung = ?, Beschreibung = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', 
                         (bezeichnung, beschreibung, sortierung, aktiv, lid))
            conn.commit()
        return ajax_response('Lagerplatz aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lagerplatz/delete/<int:lid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lagerplatz_delete(lid):
    """Lagerplatz deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lagerplatz SET Aktiv = 0 WHERE ID = ?', (lid,))
            conn.commit()
        return ajax_response('Lagerplatz deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Lieferant-Verwaltung ==========

@admin_bp.route('/lieferant/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lieferant_add():
    """Lieferant anlegen"""
    name = request.form.get('name')
    kontaktperson = request.form.get('kontaktperson', '')
    telefon = request.form.get('telefon', '')
    email = request.form.get('email', '')
    strasse = request.form.get('strasse', '')
    plz = request.form.get('plz', '')
    ort = request.form.get('ort', '')
    website = request.form.get('website', '') or ''
    
    if not name:
        return ajax_response('Name erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Lieferant (Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Website, Aktiv) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)', 
                         (name, kontaktperson, telefon, email, strasse, plz, ort, website))
            conn.commit()
        return ajax_response('Lieferant erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lieferant/update/<int:lid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lieferant_update(lid):
    """Lieferant aktualisieren"""
    name = request.form.get('name')
    kontaktperson = request.form.get('kontaktperson', '')
    telefon = request.form.get('telefon', '')
    email = request.form.get('email', '')
    strasse = request.form.get('strasse', '')
    plz = request.form.get('plz', '')
    ort = request.form.get('ort', '')
    website = request.form.get('website', '') or ''
    csv_export_reihenfolge = (request.form.get('csv_export_reihenfolge') or '').strip() or None
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not name:
        return ajax_response('Name erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lieferant SET Name = ?, Kontaktperson = ?, Telefon = ?, Email = ?, Strasse = ?, PLZ = ?, Ort = ?, Website = ?, CsvExportReihenfolge = ?, Aktiv = ? WHERE ID = ?', 
                         (name, kontaktperson, telefon, email, strasse, plz, ort, website, csv_export_reihenfolge, aktiv, lid))
            conn.commit()
        return ajax_response('Lieferant aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lieferant/delete/<int:lid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def lieferant_delete(lid):
    """Lieferant soft-delete"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lieferant SET Gelöscht = 1 WHERE ID = ?', (lid,))
            conn.commit()
        return ajax_response('Lieferant gelöscht.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Fremdfirmen (Wartungen) ==========

@admin_bp.route('/fremdfirma/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def fremdfirma_add():
    """Fremdfirma anlegen (nur Admin)."""
    name = (request.form.get('firmenname') or '').strip()
    adr = request.form.get('adresse', '')
    tb = request.form.get('taetigkeitsbereich', '')
    if not name:
        return ajax_response('Firmenname erforderlich.', success=False)
    try:
        with get_db_connection() as conn:
            wartungen_services.create_fremdfirma(conn, name, adr, tb)
            conn.commit()
        return ajax_response('Fremdfirma angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/fremdfirma/update/<int:fid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def fremdfirma_update(fid):
    """Fremdfirma aktualisieren."""
    name = (request.form.get('firmenname') or '').strip()
    adr = request.form.get('adresse', '')
    tb = request.form.get('taetigkeitsbereich', '')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    if not name:
        return ajax_response('Firmenname erforderlich.', success=False)
    try:
        with get_db_connection() as conn:
            wartungen_services.update_fremdfirma(conn, fid, name, adr, tb, bool(aktiv))
            conn.commit()
        return ajax_response('Fremdfirma gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Datenbank-Verwaltung ==========

# Datenbankschema-Definition (basierend auf init_database.py)
DATABASE_SCHEMA = {
    'Mitarbeiter': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Personalnummer': 'TEXT NOT NULL UNIQUE',
            'Vorname': 'TEXT',
            'Nachname': 'TEXT NOT NULL',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1',
            'Passwort': 'TEXT NOT NULL',
            'PrimaerAbteilungID': 'INTEGER'
        },
        'indexes': [
            'idx_mitarbeiter_aktiv',
            'idx_mitarbeiter_personalnummer'
        ]
    },
    'Abteilung': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'ParentAbteilungID': 'INTEGER NULL',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1',
            'Sortierung': 'INTEGER DEFAULT 0'
        },
        'indexes': [
            'idx_abteilung_parent',
            'idx_abteilung_aktiv'
        ]
    },
    'MitarbeiterAbteilung': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'MitarbeiterID': 'INTEGER NOT NULL',
            'AbteilungID': 'INTEGER NOT NULL'
        },
        'indexes': [
            'idx_mitarbeiter_abteilung_ma',
            'idx_mitarbeiter_abteilung_abt'
        ]
    },
    'Bereich': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1'
        },
        'indexes': [
            'idx_bereich_aktiv'
        ]
    },
    'Gewerke': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'BereichID': 'INTEGER NOT NULL',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1'
        },
        'indexes': [
            'idx_gewerke_bereich',
            'idx_gewerke_aktiv'
        ]
    },
    'Status': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'Farbe': 'TEXT',
            'Sortierung': 'INTEGER DEFAULT 0',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1'
        },
        'indexes': [
            'idx_status_aktiv'
        ]
    },
    'Taetigkeit': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'Sortierung': 'INTEGER DEFAULT 0',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1'
        },
        'indexes': [
            'idx_taetigkeit_aktiv'
        ]
    },
    'SchichtbuchThema': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'GewerkID': 'INTEGER NOT NULL',
            'StatusID': 'INTEGER NOT NULL',
            'ErstellerAbteilungID': 'INTEGER',
            'Gelöscht': 'INTEGER NOT NULL DEFAULT 0',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
        },
        'indexes': [
            'idx_thema_gewerk',
            'idx_thema_status',
            'idx_thema_abteilung',
            'idx_thema_geloescht'
        ]
    },
    'SchichtbuchBemerkungen': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'ThemaID': 'INTEGER NOT NULL',
            'MitarbeiterID': 'INTEGER NOT NULL',
            'Datum': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            'TaetigkeitID': 'INTEGER',
            'Bemerkung': 'TEXT',
            'Gelöscht': 'INTEGER NOT NULL DEFAULT 0'
        },
        'indexes': [
            'idx_bemerkung_thema',
            'idx_bemerkung_mitarbeiter',
            'idx_bemerkung_geloescht'
        ]
    },
    'SchichtbuchThemaSichtbarkeit': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'ThemaID': 'INTEGER NOT NULL',
            'AbteilungID': 'INTEGER NOT NULL',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
        },
        'indexes': [
            'idx_sichtbarkeit_thema',
            'idx_sichtbarkeit_abteilung'
        ]
    },
    'Aufgabenliste': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'Beschreibung': 'TEXT',
            'ErstellerMitarbeiterID': 'INTEGER NOT NULL',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1'
        },
        'indexes': [
            'idx_aufgabenliste_ersteller',
            'idx_aufgabenliste_aktiv'
        ]
    },
    'AufgabenlisteSichtbarkeitAbteilung': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'AufgabenlisteID': 'INTEGER NOT NULL',
            'AbteilungID': 'INTEGER NOT NULL'
        },
        'indexes': [
            'idx_aufgsicht_abt_liste',
            'idx_aufgsicht_abt_abt'
        ]
    },
    'AufgabenlisteSichtbarkeitMitarbeiter': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'AufgabenlisteID': 'INTEGER NOT NULL',
            'MitarbeiterID': 'INTEGER NOT NULL'
        },
        'indexes': [
            'idx_aufgsicht_ma_liste',
            'idx_aufgsicht_ma_ma'
        ]
    },
    'AufgabenlisteThema': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'AufgabenlisteID': 'INTEGER NOT NULL',
            'ThemaID': 'INTEGER NOT NULL',
            'Sortierung': 'INTEGER NOT NULL DEFAULT 0',
            'HinzugefuegtAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            'HinzugefuegtVonMitarbeiterID': 'INTEGER'
        },
        'indexes': [
            'idx_aufgthema_liste',
            'idx_aufgthema_thema'
        ]
    },
    'Benachrichtigung': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'MitarbeiterID': 'INTEGER NOT NULL',
            'ThemaID': 'INTEGER NOT NULL',
            'BemerkungID': 'INTEGER NULL',
            'Typ': 'TEXT NOT NULL',
            'Titel': 'TEXT NOT NULL',
            'Nachricht': 'TEXT NOT NULL',
            'Gelesen': 'INTEGER NOT NULL DEFAULT 0',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
        },
        'indexes': [
            'idx_benachrichtigung_mitarbeiter',
            'idx_benachrichtigung_thema',
            'idx_benachrichtigung_gelesen'
        ]
    },
    'ErsatzteilKategorie': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'Beschreibung': 'TEXT',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1',
            'Sortierung': 'INTEGER DEFAULT 0'
        },
        'indexes': [
            'idx_ersatzteil_kategorie_aktiv',
            'idx_ersatzteil_kategorie_sortierung'
        ]
    },
    'Kostenstelle': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bezeichnung': 'TEXT NOT NULL',
            'Beschreibung': 'TEXT',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1',
            'Sortierung': 'INTEGER DEFAULT 0'
        },
        'indexes': [
            'idx_kostenstelle_aktiv',
            'idx_kostenstelle_sortierung'
        ]
    },
    'Lieferant': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Name': 'TEXT NOT NULL',
            'Kontaktperson': 'TEXT',
            'Telefon': 'TEXT',
            'Email': 'TEXT',
            'Strasse': 'TEXT',
            'PLZ': 'TEXT',
            'Ort': 'TEXT',
            'Website': 'TEXT',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1',
            'Gelöscht': 'INTEGER NOT NULL DEFAULT 0'
        },
        'indexes': [
            'idx_lieferant_aktiv',
            'idx_lieferant_geloescht'
        ]
    },
    'Ersatzteil': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'Bestellnummer': 'TEXT NOT NULL UNIQUE',
            'Bezeichnung': 'TEXT NOT NULL',
            'Beschreibung': 'TEXT',
            'KategorieID': 'INTEGER',
            'Hersteller': 'TEXT',
            'LieferantID': 'INTEGER',
            'Preis': 'REAL',
            'Waehrung': 'TEXT DEFAULT \'EUR\'',
            'Lagerort': 'TEXT',
            'Mindestbestand': 'INTEGER DEFAULT 0',
            'AktuellerBestand': 'INTEGER DEFAULT 0',
            'Einheit': 'TEXT DEFAULT \'Stück\'',
            'Aktiv': 'INTEGER NOT NULL DEFAULT 1',
            'Gelöscht': 'INTEGER NOT NULL DEFAULT 0',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            'ErstelltVonID': 'INTEGER'
        },
        'indexes': [
            'idx_ersatzteil_bestellnummer',
            'idx_ersatzteil_kategorie',
            'idx_ersatzteil_lieferant',
            'idx_ersatzteil_aktiv',
            'idx_ersatzteil_geloescht',
            'idx_ersatzteil_bestand'
        ]
    },
    'ErsatzteilBild': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'ErsatzteilID': 'INTEGER NOT NULL',
            'Dateiname': 'TEXT NOT NULL',
            'Dateipfad': 'TEXT NOT NULL',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
        },
        'indexes': [
            'idx_ersatzteil_bild_ersatzteil'
        ]
    },
    'ErsatzteilDokument': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'ErsatzteilID': 'INTEGER NOT NULL',
            'Dateiname': 'TEXT NOT NULL',
            'Dateipfad': 'TEXT NOT NULL',
            'Typ': 'TEXT',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
        },
        'indexes': [
            'idx_ersatzteil_dokument_ersatzteil'
        ]
    },
    'Lagerbuchung': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'ErsatzteilID': 'INTEGER NOT NULL',
            'Typ': 'TEXT NOT NULL',
            'Menge': 'INTEGER NOT NULL',
            'Grund': 'TEXT',
            'ThemaID': 'INTEGER NULL',
            'KostenstelleID': 'INTEGER',
            'VerwendetVonID': 'INTEGER NOT NULL',
            'Buchungsdatum': 'DATETIME DEFAULT CURRENT_TIMESTAMP',
            'Bemerkung': 'TEXT',
            'ErstelltAm': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
        },
        'indexes': [
            'idx_lagerbuchung_ersatzteil',
            'idx_lagerbuchung_thema',
            'idx_lagerbuchung_kostenstelle',
            'idx_lagerbuchung_verwendet_von',
            'idx_lagerbuchung_buchungsdatum'
        ]
    },
    'ErsatzteilAbteilungZugriff': {
        'columns': {
            'ID': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'ErsatzteilID': 'INTEGER NOT NULL',
            'AbteilungID': 'INTEGER NOT NULL'
        },
        'indexes': [
            'idx_ersatzteil_abteilung_ersatzteil',
            'idx_ersatzteil_abteilung_abteilung'
        ]
    }
}


@admin_bp.route('/database/check', methods=['GET'])
@admin_required
@menue_zugriff_erforderlich('admin')
def database_check():
    """Überprüft die Datenbankstruktur"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            missing_tables = []
            missing_columns = {}
            missing_indexes = []
            
            # Prüfe jede Tabelle im Schema
            for table_name, table_schema in DATABASE_SCHEMA.items():
                # Prüfe ob Tabelle existiert
                cursor.execute('''
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                ''', (table_name,))
                
                if not cursor.fetchone():
                    missing_tables.append(table_name)
                    continue
                
                # Tabelle existiert, prüfe Spalten
                cursor.execute(f'PRAGMA table_info({table_name})')
                existing_columns = {row[1] for row in cursor.fetchall()}
                
                required_columns = set(table_schema['columns'].keys())
                table_missing_columns = required_columns - existing_columns
                
                if table_missing_columns:
                    missing_columns[table_name] = list(table_missing_columns)
                
                # Prüfe Indizes
                cursor.execute(f'PRAGMA index_list({table_name})')
                existing_indexes = {row[1] for row in cursor.fetchall()}
                
                for index_name in table_schema.get('indexes', []):
                    if index_name not in existing_indexes:
                        missing_indexes.append(index_name)
            
            has_issues = bool(missing_tables or missing_columns or missing_indexes)
            
            return jsonify({
                'success': True,
                'has_issues': has_issues,
                'missing_tables': missing_tables,
                'missing_columns': missing_columns,
                'missing_indexes': missing_indexes
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Fehler bei der Datenbankprüfung: {str(e)}'
        }), 500


@admin_bp.route('/benachrichtigungen/cleanup', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def benachrichtigungen_cleanup():
    """Manuelles Auslösen der Bereinigung alter Benachrichtigungen"""
    try:
        from utils.benachrichtigungen_cleanup import bereinige_benachrichtigungen_automatisch
        from flask import current_app
        
        gelöscht_count, fehler = bereinige_benachrichtigungen_automatisch(current_app)
        
        if fehler:
            return ajax_response(f'Fehler beim Cleanup: {fehler}', success=False)
        
        if gelöscht_count > 0:
            return ajax_response(f'{gelöscht_count} alte Benachrichtigungen wurden gelöscht.', success=True)
        else:
            return ajax_response('Keine alten Benachrichtigungen gefunden.', success=True)
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False)


@admin_bp.route('/database/repair', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def database_repair():
    """Fügt fehlende Tabellen, Spalten und Indizes zur Datenbank hinzu"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            added_tables = []
            added_columns = {}
            added_indexes = []
            errors = []
            
            # Prüfe jede Tabelle im Schema
            for table_name, table_schema in DATABASE_SCHEMA.items():
                # Prüfe ob Tabelle existiert
                cursor.execute('''
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                ''', (table_name,))
                
                if not cursor.fetchone():
                    # Tabelle fehlt - erstelle sie
                    try:
                        columns_def = ', '.join([
                            f'{col_name} {col_type}' 
                            for col_name, col_type in table_schema['columns'].items()
                        ])
                        create_sql = f'CREATE TABLE {table_name} ({columns_def})'
                        cursor.execute(create_sql)
                        added_tables.append(table_name)
                        
                        # Erstelle Indizes für neue Tabelle
                        for index_name in table_schema.get('indexes', []):
                            try:
                                # Versuche Index-Name auf Spalte abzubilden
                                table_prefix = f'idx_{table_name.lower()}_'
                                if index_name.startswith(table_prefix):
                                    column_name = index_name[len(table_prefix):]
                                elif index_name.startswith(f'idx_{table_name.lower()}'):
                                    column_name = index_name[len(f'idx_{table_name.lower()}'):].lstrip('_')
                                else:
                                    column_name = index_name.replace('idx_', '').replace('_', '')
                                
                                # Prüfe ob Spalte direkt existiert
                                if column_name in table_schema['columns']:
                                    cursor.execute(f'CREATE INDEX {index_name} ON {table_name}({column_name})')
                                    added_indexes.append(index_name)
                                else:
                                    # Versuche gängige Spaltennamen-Mappings
                                    possible_columns = {
                                        'aktiv': 'Aktiv',
                                        'geloescht': 'Gelöscht',
                                        'parent': 'ParentAbteilungID',
                                        'bereich': 'BereichID',
                                        'gewerk': 'GewerkID',
                                        'status': 'StatusID',
                                        'thema': 'ThemaID',
                                        'mitarbeiter': 'MitarbeiterID',
                                        'abteilung': 'AbteilungID',
                                        'personalnummer': 'Personalnummer',
                                        'ma': 'MitarbeiterID',
                                        'abt': 'AbteilungID',
                                        'kategorie': 'KategorieID',
                                        'lieferant': 'LieferantID',
                                        'bestellnummer': 'Bestellnummer',
                                        'bestand': 'AktuellerBestand',
                                        'ersatzteil': 'ErsatzteilID',
                                        'kostenstelle': 'KostenstelleID',
                                        'verwendetvon': 'VerwendetVonID',
                                        'verwendet_von': 'VerwendetVonID',
                                        'buchungsdatum': 'Buchungsdatum',
                                        'sortierung': 'Sortierung',
                                        'kategorieaktiv': 'Aktiv',
                                        'kategoriesortierung': 'Sortierung',
                                        'kostenstelleaktiv': 'Aktiv',
                                        'kostenstellesortierung': 'Sortierung'
                                    }
                                    
                                    # Prüfe verschiedene Varianten
                                    column_found = False
                                    for key, col in possible_columns.items():
                                        if key in column_name.lower() or column_name.lower() in key:
                                            if col in table_schema['columns']:
                                                cursor.execute(f'CREATE INDEX {index_name} ON {table_name}({col})')
                                                added_indexes.append(index_name)
                                                column_found = True
                                                break
                                    
                                    if not column_found:
                                        # Versuche alle Spalten durchzugehen und nach Übereinstimmungen suchen
                                        for col in table_schema['columns'].keys():
                                            if col.lower() in column_name.lower() or column_name.lower() in col.lower():
                                                cursor.execute(f'CREATE INDEX {index_name} ON {table_name}({col})')
                                                added_indexes.append(index_name)
                                                column_found = True
                                                break
                                    
                                    if not column_found:
                                        errors.append(f'Index {index_name}: Spalte für "{column_name}" nicht gefunden')
                            except Exception as e:
                                errors.append(f'Index {index_name}: {str(e)}')
                    except Exception as e:
                        errors.append(f'Tabelle {table_name}: {str(e)}')
                    continue
                
                # Tabelle existiert, prüfe fehlende Spalten
                cursor.execute(f'PRAGMA table_info({table_name})')
                existing_columns = {row[1] for row in cursor.fetchall()}
                
                table_added_columns = []
                for col_name, col_type in table_schema['columns'].items():
                    if col_name not in existing_columns and col_name != 'ID':
                        # Spalte fehlt - füge sie hinzu
                        try:
                            # Bei SQLite kann man nur Spalten mit DEFAULT oder NULL hinzufügen
                            # Entferne NOT NULL ohne DEFAULT für ALTER TABLE
                            col_def = col_type.replace('NOT NULL', '').strip()
                            if 'DEFAULT' not in col_def.upper() and 'NULL' not in col_def.upper():
                                col_def += ' NULL'
                            
                            cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}')
                            table_added_columns.append(col_name)
                        except Exception as e:
                            errors.append(f'Spalte {table_name}.{col_name}: {str(e)}')
                
                if table_added_columns:
                    added_columns[table_name] = table_added_columns
                
                # Prüfe fehlende Indizes
                cursor.execute(f'PRAGMA index_list({table_name})')
                existing_indexes = {row[1] for row in cursor.fetchall()}
                
                for index_name in table_schema.get('indexes', []):
                    if index_name not in existing_indexes:
                        try:
                            # Versuche Index-Name auf Spalte abzubilden
                            # Entferne Präfix "idx_tablename_" oder "idx_tablename"
                            table_prefix = f'idx_{table_name.lower()}_'
                            if index_name.startswith(table_prefix):
                                column_name = index_name[len(table_prefix):]
                            elif index_name.startswith(f'idx_{table_name.lower()}'):
                                column_name = index_name[len(f'idx_{table_name.lower()}'):].lstrip('_')
                            else:
                                column_name = index_name.replace('idx_', '').replace('_', '')
                            
                            # Prüfe ob Spalte direkt existiert
                            if column_name in table_schema['columns']:
                                cursor.execute(f'CREATE INDEX {index_name} ON {table_name}({column_name})')
                                added_indexes.append(index_name)
                            else:
                                # Versuche gängige Spaltennamen-Mappings
                                possible_columns = {
                                    'aktiv': 'Aktiv',
                                    'geloescht': 'Gelöscht',
                                    'parent': 'ParentAbteilungID',
                                    'bereich': 'BereichID',
                                    'gewerk': 'GewerkID',
                                    'status': 'StatusID',
                                    'thema': 'ThemaID',
                                    'mitarbeiter': 'MitarbeiterID',
                                    'abteilung': 'AbteilungID',
                                    'personalnummer': 'Personalnummer',
                                    'ma': 'MitarbeiterID',
                                    'abt': 'AbteilungID',
                                    'kategorie': 'KategorieID',
                                    'lieferant': 'LieferantID',
                                    'bestellnummer': 'Bestellnummer',
                                    'bestand': 'AktuellerBestand',
                                    'ersatzteil': 'ErsatzteilID',
                                    'kostenstelle': 'KostenstelleID',
                                    'verwendetvon': 'VerwendetVonID',
                                    'verwendet_von': 'VerwendetVonID',
                                    'buchungsdatum': 'Buchungsdatum',
                                    'sortierung': 'Sortierung',
                                    'kategorieaktiv': 'Aktiv',
                                    'kategoriesortierung': 'Sortierung',
                                    'kostenstelleaktiv': 'Aktiv',
                                    'kostenstellesortierung': 'Sortierung'
                                }
                                
                                # Prüfe verschiedene Varianten
                                column_found = False
                                for key, col in possible_columns.items():
                                    if key in column_name.lower() or column_name.lower() in key:
                                        if col in table_schema['columns']:
                                            cursor.execute(f'CREATE INDEX {index_name} ON {table_name}({col})')
                                            added_indexes.append(index_name)
                                            column_found = True
                                            break
                                
                                if not column_found:
                                    # Versuche alle Spalten durchzugehen und nach Übereinstimmungen suchen
                                    for col in table_schema['columns'].keys():
                                        if col.lower() in column_name.lower() or column_name.lower() in col.lower():
                                            cursor.execute(f'CREATE INDEX {index_name} ON {table_name}({col})')
                                            added_indexes.append(index_name)
                                            column_found = True
                                            break
                                
                                if not column_found:
                                    errors.append(f'Index {index_name}: Spalte für "{column_name}" nicht gefunden')
                        except Exception as e:
                            errors.append(f'Index {index_name}: {str(e)}')
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'added_tables': added_tables,
                'added_columns': added_columns,
                'added_indexes': added_indexes,
                'errors': errors if errors else None
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Fehler bei der Datenbankreparatur: {str(e)}'
        }), 500


# ========== Login-Log-Verwaltung ==========

@admin_bp.route('/login-logs')
@admin_required
@menue_zugriff_erforderlich('admin')
def login_logs():
    """Anzeige der Login-Logs"""
    # Filter-Parameter
    personalnummer_filter = request.args.get('personalnummer', '')
    erfolgreich_filter = request.args.get('erfolgreich', '')
    datum_von = request.args.get('datum_von', '')
    datum_bis = request.args.get('datum_bis', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    with get_db_connection() as conn:
        # Query aufbauen
        query = '''
            SELECT 
                l.ID,
                l.Personalnummer,
                l.MitarbeiterID,
                l.Erfolgreich,
                l.IPAdresse,
                l.UserAgent,
                l.Fehlermeldung,
                l.Zeitpunkt,
                m.Vorname,
                m.Nachname
            FROM LoginLog l
            LEFT JOIN Mitarbeiter m ON l.MitarbeiterID = m.ID
            WHERE 1=1
        '''
        params = []
        
        if personalnummer_filter:
            query += ' AND l.Personalnummer LIKE ?'
            params.append(f'%{personalnummer_filter}%')
        
        if erfolgreich_filter != '':
            query += ' AND l.Erfolgreich = ?'
            params.append(1 if erfolgreich_filter == '1' else 0)
        
        if datum_von:
            query += ' AND DATE(l.Zeitpunkt) >= ?'
            params.append(datum_von)
        
        if datum_bis:
            query += ' AND DATE(l.Zeitpunkt) <= ?'
            params.append(datum_bis)
        
        query += ' ORDER BY l.Zeitpunkt DESC LIMIT ? OFFSET ?'
        params.extend([per_page, (page - 1) * per_page])
        
        logs = conn.execute(query, params).fetchall()
        
        # Gesamtanzahl für Pagination
        count_query = '''
            SELECT COUNT(*) as count
            FROM LoginLog l
            WHERE 1=1
        '''
        count_params = []
        
        if personalnummer_filter:
            count_query += ' AND l.Personalnummer LIKE ?'
            count_params.append(f'%{personalnummer_filter}%')
        
        if erfolgreich_filter != '':
            count_query += ' AND l.Erfolgreich = ?'
            count_params.append(1 if erfolgreich_filter == '1' else 0)
        
        if datum_von:
            count_query += ' AND DATE(l.Zeitpunkt) >= ?'
            count_params.append(datum_von)
        
        if datum_bis:
            count_query += ' AND DATE(l.Zeitpunkt) <= ?'
            count_params.append(datum_bis)
        
        total_count = conn.execute(count_query, count_params).fetchone()['count']
        total_pages = (total_count + per_page - 1) // per_page
        
        # Statistiken
        stats = {}
        stats['gesamt'] = conn.execute('SELECT COUNT(*) as count FROM LoginLog').fetchone()['count']
        stats['erfolgreich'] = conn.execute('SELECT COUNT(*) as count FROM LoginLog WHERE Erfolgreich = 1').fetchone()['count']
        stats['fehlgeschlagen'] = conn.execute('SELECT COUNT(*) as count FROM LoginLog WHERE Erfolgreich = 0').fetchone()['count']
        stats['heute'] = conn.execute('SELECT COUNT(*) as count FROM LoginLog WHERE DATE(Zeitpunkt) = DATE("now")').fetchone()['count']
    
    return render_template('admin_login_logs.html',
                         logs=logs,
                         stats=stats,
                         personalnummer_filter=personalnummer_filter,
                         erfolgreich_filter=erfolgreich_filter,
                         datum_von=datum_von,
                         datum_bis=datum_bis,
                         page=page,
                         total_pages=total_pages,
                         total_count=total_count)


# ========== Firmendaten-Verwaltung ==========

@admin_bp.route('/firmendaten', methods=['GET', 'POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def firmendaten():
    """Firmendaten anzeigen und bearbeiten"""
    if request.method == 'POST':
        firmenname = request.form.get('firmenname', '').strip()
        strasse = request.form.get('strasse', '').strip() or None
        plz = request.form.get('plz', '').strip() or None
        ort = request.form.get('ort', '').strip() or None
        lieferstrasse = request.form.get('lieferstrasse', '').strip() or None
        lieferplz = request.form.get('lieferplz', '').strip() or None
        lieferort = request.form.get('lieferort', '').strip() or None
        telefon = request.form.get('telefon', '').strip() or None
        fax = request.form.get('fax', '').strip() or None
        email = request.form.get('email', '').strip() or None
        website = request.form.get('website', '').strip() or None
        steuernummer = request.form.get('steuernummer', '').strip() or None
        ust_idnr = request.form.get('ust_idnr', '').strip() or None
        geschaeftsfuehrer = request.form.get('geschaeftsfuehrer', '').strip() or None
        logopfad = request.form.get('logopfad', '').strip() or None
        bankname = request.form.get('bankname', '').strip() or None
        iban = request.form.get('iban', '').strip() or None
        bic = request.form.get('bic', '').strip() or None
        
        if not firmenname:
            return ajax_response('Firmenname ist erforderlich.', success=False)
        
        try:
            with get_db_connection() as conn:
                # Prüfe ob bereits Datensatz existiert
                vorhanden = conn.execute('SELECT ID FROM Firmendaten LIMIT 1').fetchone()
                
                if vorhanden:
                    # Aktualisieren
                    conn.execute('''
                        UPDATE Firmendaten SET
                            Firmenname = ?,
                            Strasse = ?,
                            PLZ = ?,
                            Ort = ?,
                            LieferStrasse = ?,
                            LieferPLZ = ?,
                            LieferOrt = ?,
                            Telefon = ?,
                            Fax = ?,
                            Email = ?,
                            Website = ?,
                            Steuernummer = ?,
                            UStIdNr = ?,
                            Geschaeftsfuehrer = ?,
                            LogoPfad = ?,
                            BankName = ?,
                            IBAN = ?,
                            BIC = ?,
                            GeaendertAm = datetime("now")
                        WHERE ID = ?
                    ''', (firmenname, strasse, plz, ort, lieferstrasse, lieferplz, lieferort,
                          telefon, fax, email, website, steuernummer, ust_idnr, geschaeftsfuehrer, 
                          logopfad, bankname, iban, bic, vorhanden['ID']))
                else:
                    # Neu anlegen
                    conn.execute('''
                        INSERT INTO Firmendaten (
                            Firmenname, Strasse, PLZ, Ort, LieferStrasse, LieferPLZ, LieferOrt,
                            Telefon, Fax, Email, Website,
                            Steuernummer, UStIdNr, Geschaeftsfuehrer, LogoPfad,
                            BankName, IBAN, BIC
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (firmenname, strasse, plz, ort, lieferstrasse, lieferplz, lieferort,
                          telefon, fax, email, website, steuernummer, ust_idnr, geschaeftsfuehrer, 
                          logopfad, bankname, iban, bic))
                
                conn.commit()
                return ajax_response('Firmendaten erfolgreich gespeichert.')
        except Exception as e:
            print(f"Firmendaten speichern Fehler: {e}")
            import traceback
            traceback.print_exc()
            return ajax_response(f'Fehler beim Speichern: {str(e)}', success=False, status_code=500)
    
    return redirect(url_for('admin.dashboard'))


# ========== Berechtigungs-Verwaltung ==========

@admin_bp.route('/berechtigung/add', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def berechtigung_add():
    """Berechtigung anlegen"""
    schluessel = request.form.get('schluessel', '').strip()
    bezeichnung = request.form.get('bezeichnung', '').strip()
    beschreibung = request.form.get('beschreibung', '').strip()
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not schluessel or not bezeichnung:
        return ajax_response('Bitte Schlüssel und Bezeichnung ausfüllen.', success=False)
    
    try:
        with get_db_connection() as conn:
            existing = conn.execute(
                'SELECT ID FROM Berechtigung WHERE Schluessel = ?',
                (schluessel,),
            ).fetchone()
            if existing:
                return ajax_response(
                    'Eine Berechtigung mit diesem Schlüssel existiert bereits.',
                    success=False,
                    status_code=400,
                )
            conn.execute(
                'INSERT INTO Berechtigung (Schluessel, Bezeichnung, Beschreibung, Aktiv) VALUES (?, ?, ?, ?)',
                (schluessel, bezeichnung, beschreibung, aktiv)
            )
            conn.commit()
        return ajax_response('Berechtigung erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler beim Anlegen: {str(e)}', success=False, status_code=500)


@admin_bp.route('/berechtigung/update/<int:bid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def berechtigung_update(bid):
    """Berechtigung aktualisieren"""
    bezeichnung = request.form.get('bezeichnung', '').strip()
    beschreibung = request.form.get('beschreibung', '').strip()
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not bezeichnung:
        return ajax_response('Bitte Bezeichnung ausfüllen.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute(
                'UPDATE Berechtigung SET Bezeichnung = ?, Beschreibung = ?, Aktiv = ? WHERE ID = ?',
                (bezeichnung, beschreibung, aktiv, bid)
            )
            conn.commit()
        return ajax_response('Berechtigung aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/berechtigung/toggle/<int:bid>', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def berechtigung_toggle(bid):
    """Berechtigung aktivieren/deaktivieren"""
    try:
        with get_db_connection() as conn:
            berechtigung = conn.execute('SELECT Aktiv FROM Berechtigung WHERE ID = ?', (bid,)).fetchone()
            if not berechtigung:
                return ajax_response('Berechtigung nicht gefunden.', success=False, status_code=404)
            
            neuer_status = 0 if berechtigung['Aktiv'] == 1 else 1
            conn.execute('UPDATE Berechtigung SET Aktiv = ? WHERE ID = ?', (neuer_status, bid))
            conn.commit()
        
        status_text = 'aktiviert' if neuer_status == 1 else 'deaktiviert'
        return ajax_response(f'Berechtigung {status_text}.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/<int:mid>/berechtigungen', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_berechtigungen(mid):
    """Mitarbeiter-Berechtigungen zuweisen (alle auf einmal)"""
    berechtigung_ids = request.form.getlist('berechtigungen')
    
    # IDs in Integer konvertieren
    berechtigung_ids = [int(bid) for bid in berechtigung_ids if bid and bid != '']
    
    try:
        with get_db_connection() as conn:
            # Prüfen ob Mitarbeiter existiert
            mitarbeiter = conn.execute('SELECT ID FROM Mitarbeiter WHERE ID = ?', (mid,)).fetchone()
            if not mitarbeiter:
                return ajax_response('Mitarbeiter nicht gefunden.', success=False, status_code=404)
            
            # Alle Berechtigungen für diesen Mitarbeiter löschen
            conn.execute('DELETE FROM MitarbeiterBerechtigung WHERE MitarbeiterID = ?', (mid,))

            # Neue Berechtigungen hinzufügen (Duplikate werden per UNIQUE-Constraint ignoriert)
            berechtigung_upsert_sql = upsert_ignore(
                'MitarbeiterBerechtigung',
                ('MitarbeiterID', 'BerechtigungID'),
                ('MitarbeiterID', 'BerechtigungID'),
            )
            for berechtigung_id in berechtigung_ids:
                # Prüfen ob Berechtigung existiert
                berechtigung = conn.execute('SELECT ID FROM Berechtigung WHERE ID = ?', (berechtigung_id,)).fetchone()
                if berechtigung:
                    conn.execute(berechtigung_upsert_sql, (mid, berechtigung_id))
            
            conn.commit()
        
        return ajax_response('Berechtigungen erfolgreich aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/<int:mid>/menue-sichtbarkeit', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin')
def mitarbeiter_menue_sichtbarkeit(mid):
    """Menü-Sichtbarkeit für einen Mitarbeiter speichern"""
    try:
        with get_db_connection() as conn:
            mitarbeiter = conn.execute('SELECT ID FROM Mitarbeiter WHERE ID = ?', (mid,)).fetchone()
            if not mitarbeiter:
                return ajax_response('Mitarbeiter nicht gefunden.', success=False, status_code=404)

            menue_defs = get_alle_menue_definitionen()

            for m in menue_defs:
                schluessel = m['schluessel']
                wert = request.form.get(f'm{mid}_menue_{schluessel}')
                conn.execute('''
                    DELETE FROM MitarbeiterMenueSichtbarkeit
                    WHERE MitarbeiterID = ? AND MenueSchluessel = ?
                ''', (mid, schluessel))
                if wert == '1':
                    conn.execute('''
                        INSERT INTO MitarbeiterMenueSichtbarkeit (MitarbeiterID, MenueSchluessel, Sichtbar)
                        VALUES (?, ?, 1)
                    ''', (mid, schluessel))
                elif wert == '0':
                    conn.execute('''
                        INSERT INTO MitarbeiterMenueSichtbarkeit (MitarbeiterID, MenueSchluessel, Sichtbar)
                        VALUES (?, ?, 0)
                    ''', (mid, schluessel))

            conn.commit()
        return ajax_response('Menü-Sichtbarkeit erfolgreich aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== MQTT (Technik / Beleuchtung) ==========


@admin_bp.route('/mqtt', methods=['GET'])
@admin_required
@menue_zugriff_erforderlich('admin_mqtt')
def mqtt_konfiguration():
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM MqttKonfiguration ORDER BY ID LIMIT 1').fetchone()
    if not row:
        flash('MqttKonfiguration fehlt in der Datenbank (Migration ausführen).', 'danger')
        return redirect(url_for('admin.dashboard'))
    d = dict(row)
    d['has_passwort'] = bool((d.get('PasswortKrypt') or '').strip())
    return render_template('admin_mqtt.html', cfg=d)


@admin_bp.route('/mqtt/save', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_mqtt')
def mqtt_konfiguration_save():
    from flask import current_app
    from utils.fernet_secrets import encrypt_text
    from modules.technik.mqtt_runtime import invalidate_mqtt_konfig_cache

    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    host = (request.form.get('broker_host') or '').strip() or None
    port = int(request.form.get('broker_port') or 1883)
    use_tls = 1 if request.form.get('use_tls') == 'on' else 0
    tls_insecure = 1 if request.form.get('tls_insecure') == 'on' else 0
    ca = (request.form.get('ca_pfad') or '').strip() or None
    user = (request.form.get('benutzername') or '').strip() or None
    pass_neu = (request.form.get('passwort') or '')
    topic_p = (request.form.get('topic_prefix_beleuchtung') or 'IPS/BM/Beleuchtung').strip()
    mcid = (request.form.get('mqtt_client_id') or '').strip() or None
    redis_u = (request.form.get('redis_url') or '').strip() or None

    with get_db_connection() as conn:
        cur = conn.execute('SELECT ID, PasswortKrypt FROM MqttKonfiguration ORDER BY ID LIMIT 1').fetchone()
        if not cur:
            flash('MqttKonfiguration nicht gefunden.', 'danger')
            return redirect(url_for('admin.mqtt_konfiguration'))
        if pass_neu:
            krypt = encrypt_text(pass_neu, current_app.config.get('SECRET_KEY'))
        else:
            krypt = cur['PasswortKrypt']
        conn.execute(
            '''
            UPDATE MqttKonfiguration SET
                Aktiv = ?,
                BrokerHost = ?,
                BrokerPort = ?,
                UseTls = ?,
                TlsInsecure = ?,
                CaPfad = ?,
                Benutzername = ?,
                PasswortKrypt = ?,
                TopicPrefixBeleuchtung = ?,
                MqttClientId = ?,
                RedisUrl = ?,
                GeaendertAm = CURRENT_TIMESTAMP
            WHERE ID = ?
            ''',
            (aktiv, host, port, use_tls, tls_insecure, ca, user, krypt, topic_p, mcid, redis_u, cur['ID']),
        )
    invalidate_mqtt_konfig_cache()
    flash('MQTT-Einstellungen gespeichert.', 'success')
    return redirect(url_for('admin.mqtt_konfiguration'))


@admin_bp.route('/mqtt/test', methods=['POST'])
@admin_required
@menue_zugriff_erforderlich('admin_mqtt')
def mqtt_konfiguration_test():
    from flask import current_app
    from utils.fernet_secrets import decrypt_text
    import paho.mqtt.client as mqtt
    import time
    import uuid

    c = None
    try:
        with get_db_connection() as conn:
            row = conn.execute('SELECT * FROM MqttKonfiguration ORDER BY ID LIMIT 1').fetchone()
        if not row:
            return jsonify({'ok': False, 'message': 'Kein Eintrag in MqttKonfiguration.'}), 400
        d = dict(row)
        if not (d.get('BrokerHost') or '').strip():
            return jsonify({'ok': False, 'message': 'Kein Broker-Host konfiguriert. Bitte zuerst speichern.'}), 400
        sk = current_app.config.get('SECRET_KEY')
        pw = ''
        if d.get('PasswortKrypt'):
            try:
                pw = decrypt_text(d.get('PasswortKrypt'), sk) or ''
            except Exception as de:
                return jsonify({'ok': False, 'message': f'Passwort entschlüsseln fehlgeschlagen: {de}'}), 400
        user = (d.get('Benutzername') or '').strip() or None
        use_tls = int(d.get('UseTls') or 0) == 1
        tls_insec = int(d.get('TlsInsecure') or 0) == 1
        ca = (d.get('CaPfad') or '').strip() or None
        host = (d.get('BrokerHost') or '').strip()
        port = int(d.get('BrokerPort') or 1883)
        result = {'ok': False, 'message': 'Unbekannter Fehler (kein CONNACK).'}
        event = {'done': False, 'err': None}

        def on_connect_cl(client, userdata, flags, reason_code, properties):
            if reason_code and getattr(reason_code, 'is_failure', False):
                result['ok'] = False
                result['message'] = f'Broker (CONNACK) meldet Fehler: {reason_code}'
            else:
                result['ok'] = True
                result['message'] = 'Test: Verbindung hergestellt (CONNACK).'
            event['done'] = True
            try:
                client.disconnect()
            except Exception:
                pass

        def on_connect_fail_cl(client, userdata):
            # Paho: Netz/TLS schlägt fehl, bevor CONNACK
            if not event.get('done'):
                result['ok'] = False
                result['message'] = 'Verbindungsaufbau abgebrochen (Netz/TLS, siehe Server-Log).'
                event['err'] = 'on_connect_fail'
            event['done'] = True

        c = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f'bis-mqtt-test-{uuid.uuid4().hex[:8]}',
            protocol=mqtt.MQTTv311,
        )
        c.on_connect = on_connect_cl
        c.on_connect_fail = on_connect_fail_cl
        if user:
            c.username_pw_set(user, pw)
        if use_tls:
            c.tls_set(ca_certs=ca)
            if tls_insec:
                c.tls_insecure_set(True)
        c.connect(host, port, keepalive=10)
        c.loop_start()
        t0 = time.time()
        while not event.get('done'):
            if time.time() - t0 > 8:
                result['ok'] = False
                result['message'] = (
                    f'Keine Antwort vom Broker binnen 8s ({host!r}:{port}, TLS={use_tls}). '
                    'Adresse/Firewall/Port prüfen oder länger warten, falls der Broker träge reagiert.'
                )
                break
            time.sleep(0.05)
    except OSError as e:
        return jsonify({'ok': False, 'message': f'Netzwerk: {e} (Host {host!r}, Port {port})'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'message': f'{type(e).__name__}: {e}'}), 400
    finally:
        if c is not None:
            try:
                c.loop_stop()
                c.disconnect()
            except Exception:
                pass
    msg = (result or {}).get('message', '')
    if (result or {}).get('ok'):
        _log_admin_mqtt.info('Admin MQTT-Test: OK — %s', msg)
    else:
        _log_admin_mqtt.warning('Admin MQTT-Test: fehlgeschlagen — %s', msg)
    return jsonify(result), 200 if result.get('ok') else 400
