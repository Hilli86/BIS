"""Routen Modul Wartungen."""

import os
from datetime import datetime

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from utils import get_db_connection, login_required
from utils.file_handling import (
    save_uploaded_file,
    create_upload_folder,
    validate_file_extension,
    loesche_import_kopie_nach_upload,
)
from modules.ersatzteile.services.datei_services import (
    get_dateien_fuer_bereich,
    speichere_datei,
    loesche_datei,
    get_datei_typ_aus_dateiname,
)

from . import wartungen_bp
from . import services
from .helpers import (
    hat_wartung_zugriff,
    hat_wartung_stamm_bearbeiten,
    hat_wartungsplan_zugriff,
    hat_wartungsdurchfuehrung_zugriff,
    kann_wartung_stamm_anlegen,
    kann_wartungsplan_pflegen,
    is_admin,
)


def _parse_datetime_local(s):
    s = (s or '').strip()
    if not s:
        return None
    try:
        if 'T' in s:
            return datetime.strptime(s, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:00')
        return datetime.strptime(s, '%Y-%m-%d').strftime('%Y-%m-%d 00:00:00')
    except ValueError:
        return None


BEREICH_TYP_WARTUNGSDURCHFUEHRUNG = 'Wartungsdurchfuehrung'

_SERVICE_BERICHT_EXT = frozenset({'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'})


def _save_serviceberichte_files(conn, durchfuehrung_id, mitarbeiter_id, files, beschreibung='', typ_form=''):
    """
    Speichert Serviceberichte (Liste von FileStorage), gleiche Typregeln wie Ersatzteil-Dokumente.
    Rückgabe: (anzahl_ok, fehler_liste)
    """
    if not files:
        return 0, []
    beschreibung = (beschreibung or '').strip()
    typ_form = (typ_form or '').strip()
    base = current_app.config['WARTUNG_UPLOAD_FOLDER']
    sub = os.path.join(base, 'durchfuehrung', str(durchfuehrung_id), 'serviceberichte')
    n_ok = 0
    fehler = []
    for file in files:
        if not file or not file.filename:
            continue
        orig = file.filename
        if not validate_file_extension(orig, _SERVICE_BERICHT_EXT):
            fehler.append(f'{orig}: Dateityp nicht erlaubt')
            continue
        create_upload_folder(sub)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_')
        file.filename = ts + secure_filename(orig)
        ok, fname, err = save_uploaded_file(file, sub, allowed_extensions=None)
        if not ok or err:
            fehler.append(f'{orig}: {err or "Speichern fehlgeschlagen"}')
            continue
        rel = f'Wartungen/durchfuehrung/{durchfuehrung_id}/serviceberichte/{fname}'
        inferred = get_datei_typ_aus_dateiname(orig)
        typ_final = typ_form if typ_form else (inferred or 'Servicebericht')
        speichere_datei(
            BEREICH_TYP_WARTUNGSDURCHFUEHRUNG,
            durchfuehrung_id,
            orig,
            rel,
            beschreibung,
            typ_final,
            mitarbeiter_id,
            conn,
        )
        loesche_import_kopie_nach_upload(orig, current_app.config['IMPORT_FOLDER'])
        n_ok += 1
    return n_ok, fehler


def _collect_fremdfirma_zeilen_from_form():
    ids = request.form.getlist('fremdfirma_id[]')
    techs = request.form.getlist('techniker[]')
    tels = request.form.getlist('telefon[]')
    rows = []
    n = max(len(ids), len(techs), len(tels))
    for i in range(n):
        fid = ids[i] if i < len(ids) else ''
        rows.append({
            'fremdfirma_id': fid,
            'techniker': techs[i] if i < len(techs) else '',
            'telefon': tels[i] if i < len(tels) else '',
        })
    return rows


@wartungen_bp.route('/')
@login_required
def wartung_liste():
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    with get_db_connection() as conn:
        rows = services.list_wartungen(conn, mitarbeiter_id, adm)
    return render_template(
        'wartungen/wartung_liste.html',
        wartungen=rows,
        kann_neu=kann_wartung_stamm_anlegen(),
    )


@wartungen_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def wartung_neu():
    if not kann_wartung_stamm_anlegen():
        flash('Keine Berechtigung zum Anlegen von Wartungen.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        gewerke = conn.execute('''
            SELECT g.ID, g.Bezeichnung, b.Bezeichnung AS Bereich
            FROM Gewerke g JOIN Bereich b ON g.BereichID = b.ID
            WHERE g.Aktiv = 1 AND b.Aktiv = 1
            ORDER BY b.Bezeichnung, g.Bezeichnung
        ''').fetchall()
        abteilungen = conn.execute(
            'SELECT ID, Bezeichnung FROM Abteilung WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung'
        ).fetchall()
        if request.method == 'POST':
            gewerk_id = request.form.get('gewerk_id', type=int)
            bez = request.form.get('bezeichnung', '')
            besch = request.form.get('beschreibung', '')
            sab = request.form.getlist('sichtbare_abteilungen')
            if not gewerk_id or not bez.strip():
                flash('Gewerk und Bezeichnung sind Pflichtfelder.', 'danger')
            else:
                try:
                    wid = services.create_wartung(conn, gewerk_id, bez, besch, mitarbeiter_id, sab)
                    # Datei-Uploads
                    upload_files = request.files.getlist('dateien')
                    if upload_files:
                        base = current_app.config['WARTUNG_UPLOAD_FOLDER']
                        allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
                        for file in upload_files:
                            if not file or not file.filename:
                                continue
                            sub = os.path.join(base, str(wid), 'dokumente')
                            create_upload_folder(sub)
                            orig = file.filename
                            ts = datetime.now().strftime('%Y%m%d_%H%M%S_')
                            file.filename = ts + secure_filename(orig)
                            ok, fname, err = save_uploaded_file(file, sub, allowed_extensions=None)
                            if ok:
                                rel = f'Wartungen/{wid}/dokumente/{fname}'
                                typ = get_datei_typ_aus_dateiname(orig)
                                speichere_datei(
                                    'Wartung', wid, orig, rel, '', typ, mitarbeiter_id, conn
                                )
                    conn.commit()
                    flash('Wartung angelegt.', 'success')
                    aktion = request.form.get('speichern_aktion', 'liste')
                    if aktion == 'naechste':
                        return redirect(url_for('wartungen.wartung_neu'))
                    return redirect(url_for('wartungen.wartung_liste'))
                except Exception as e:
                    flash(f'Fehler: {e}', 'danger')
    return render_template(
        'wartungen/wartung_form.html',
        gewerke=gewerke,
        abteilungen=abteilungen,
        wartung=None,
        gewaehlte_abteilungen=[],
        dateien=[],
        title='Neue Wartung',
    )


@wartungen_bp.route('/<int:wartung_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def wartung_bearbeiten(wartung_id):
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        w = services.get_wartung(conn, wartung_id)
        if not w:
            flash('Wartung nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        if not hat_wartung_zugriff(mitarbeiter_id, wartung_id, conn):
            flash('Kein Zugriff auf diese Wartung.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        kann_edit = hat_wartung_stamm_bearbeiten(mitarbeiter_id, wartung_id, conn)
        gewerke = conn.execute('''
            SELECT g.ID, g.Bezeichnung, b.Bezeichnung AS Bereich
            FROM Gewerke g JOIN Bereich b ON g.BereichID = b.ID
            WHERE g.Aktiv = 1 AND b.Aktiv = 1
            ORDER BY b.Bezeichnung, g.Bezeichnung
        ''').fetchall()
        abteilungen = conn.execute(
            'SELECT ID, Bezeichnung FROM Abteilung WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung'
        ).fetchall()
        ga = [r['ID'] for r in services.get_wartung_abteilungen(conn, wartung_id)]
        dateien = get_dateien_fuer_bereich('Wartung', wartung_id, conn)
        if request.method == 'POST':
            if not kann_edit:
                flash('Keine Berechtigung zum Bearbeiten des Stamms.', 'danger')
                return redirect(url_for('wartungen.wartung_bearbeiten', wartung_id=wartung_id))
            gewerk_id = request.form.get('gewerk_id', type=int)
            bez = request.form.get('bezeichnung', '')
            besch = request.form.get('beschreibung', '')
            aktiv = request.form.get('aktiv') == '1'
            sab = request.form.getlist('sichtbare_abteilungen')
            if not gewerk_id or not bez.strip():
                flash('Gewerk und Bezeichnung sind Pflichtfelder.', 'danger')
            else:
                services.update_wartung(conn, wartung_id, gewerk_id, bez, besch, aktiv, sab)
                upload_files = request.files.getlist('dateien')
                if upload_files:
                    base = current_app.config['WARTUNG_UPLOAD_FOLDER']
                    for file in upload_files:
                        if not file or not file.filename:
                            continue
                        sub = os.path.join(base, str(wartung_id), 'dokumente')
                        create_upload_folder(sub)
                        orig = file.filename
                        if not validate_file_extension(orig, current_app.config.get('ALLOWED_EXTENSIONS')):
                            flash(f'Dateityp nicht erlaubt: {orig}', 'warning')
                            continue
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S_')
                        file.filename = ts + secure_filename(orig)
                        ok, fname, err = save_uploaded_file(file, sub, allowed_extensions=None)
                        if ok:
                            rel = f'Wartungen/{wartung_id}/dokumente/{fname}'
                            typ = get_datei_typ_aus_dateiname(orig)
                            speichere_datei(
                                'Wartung', wartung_id, orig, rel, '', typ, mitarbeiter_id, conn,
                            )
                        else:
                            flash(err or 'Upload fehlgeschlagen', 'warning')
                conn.commit()
                flash('Gespeichert.', 'success')
                return redirect(url_for('wartungen.wartung_bearbeiten', wartung_id=wartung_id))
        plaene = services.list_plaene_fuer_wartung(conn, wartung_id)
    return render_template(
        'wartungen/wartung_form.html',
        gewerke=gewerke,
        abteilungen=abteilungen,
        wartung=w,
        gewaehlte_abteilungen=ga,
        dateien=dateien,
        kann_edit=kann_edit,
        plaene=plaene,
        kann_plan=kann_wartungsplan_pflegen(),
        title='Wartung bearbeiten',
    )


@wartungen_bp.route('/plaene')
@login_required
def plaene_uebersicht():
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        rows = services.list_plaene_sichtbar(conn, mitarbeiter_id, is_admin())
    return render_template('wartungen/plan_uebersicht.html', plaene=rows)


def _format_durchfuehrung_datum_anzeige(durchgefuehrt_am):
    if not durchgefuehrt_am:
        return ''
    s = str(durchgefuehrt_am).strip()
    if ' ' in s:
        d, rest = s.split(' ', 1)
        t = rest[:5] if len(rest) >= 5 else rest
        if rest.startswith('00:00:00') or t == '00:00':
            return d
        return f'{d} {t}'
    return s


@wartungen_bp.route('/jahresuebersicht')
@login_required
def jahresuebersicht():
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    cy = datetime.now().year
    jahre = list(range(cy - 10, cy + 2))
    jahre.sort(reverse=True)

    monatsnamen = [
        'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
        'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez',
    ]

    with get_db_connection() as conn:
        bereiche = services.list_bereiche_fuer_wartungen_sichtbar(conn, mitarbeiter_id, adm)
        if not bereiche:
            return render_template(
                'wartungen/jahresuebersicht.html',
                bereiche=[],
                gewerke=[],
                bereich_id=None,
                gewerk_id=None,
                jahr=cy,
                jahre=jahre,
                monatsnamen=monatsnamen,
                matrix_rows=[],
                title='Wartungen – Jahresübersicht',
            )

        bereich_id = request.args.get('bereich_id', type=int)
        if bereich_id is None or not any(b['ID'] == bereich_id for b in bereiche):
            bereich_id = bereiche[0]['ID']

        gewerke = services.list_gewerke_fuer_bereich_sichtbar(conn, bereich_id, mitarbeiter_id, adm)
        if not gewerke:
            jahr_empty = request.args.get('jahr', type=int)
            if jahr_empty is None or jahr_empty < 1990 or jahr_empty > 2100:
                jahr_empty = cy
            return render_template(
                'wartungen/jahresuebersicht.html',
                bereiche=bereiche,
                gewerke=[],
                bereich_id=bereich_id,
                gewerk_id=None,
                jahr=jahr_empty,
                jahre=jahre,
                monatsnamen=monatsnamen,
                matrix_rows=[],
                title='Wartungen – Jahresübersicht',
            )

        gewerk_id = request.args.get('gewerk_id', type=int)
        if gewerk_id is None or not any(g['ID'] == gewerk_id for g in gewerke):
            gewerk_id = gewerke[0]['ID']

        jahr = request.args.get('jahr', type=int)
        if jahr is None or jahr < 1990 or jahr > 2100:
            jahr = cy
        if jahr not in jahre:
            jahre = sorted(set(jahre + [jahr]), reverse=True)

        wartungen = services.list_wartungen_fuer_gewerk_sichtbar(conn, gewerk_id, mitarbeiter_id, adm)
        drows = services.list_durchfuehrungen_fuer_gewerk_jahr(conn, gewerk_id, jahr, mitarbeiter_id, adm)

    by_cell = {}
    for r in drows:
        key = (r['WartungID'], r['Monat'])
        by_cell.setdefault(key, []).append(r)

    matrix_rows = []
    for w in wartungen:
        cells = []
        for m in range(1, 13):
            items = by_cell.get((w['ID'], m), [])
            payload = []
            for it in items:
                payload.append({
                    'id': it['ID'],
                    'datum_anzeige': _format_durchfuehrung_datum_anzeige(it['DurchgefuehrtAm']),
                    'bemerkung_kurz': ((it['Bemerkung'] or '').strip()[:200]),
                    'intervall': f"{it['IntervallAnzahl']} {it['IntervallEinheit']}(e)",
                    'detail_url': url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=it['ID']),
                })
            cells.append(payload)
        matrix_rows.append({'wartung': w, 'cells': cells})

    return render_template(
        'wartungen/jahresuebersicht.html',
        bereiche=bereiche,
        gewerke=gewerke,
        bereich_id=bereich_id,
        gewerk_id=gewerk_id,
        jahr=jahr,
        jahre=jahre,
        monatsnamen=monatsnamen,
        matrix_rows=matrix_rows,
        title='Wartungen – Jahresübersicht',
    )


@wartungen_bp.route('/<int:wartung_id>/plan/neu', methods=['GET', 'POST'])
@login_required
def plan_neu(wartung_id):
    if not kann_wartungsplan_pflegen():
        flash('Keine Berechtigung für Wartungspläne.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartung_zugriff(mitarbeiter_id, wartung_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        w = services.get_wartung(conn, wartung_id)
        if request.method == 'POST':
            einheit = request.form.get('intervall_einheit', '')
            anzahl = request.form.get('intervall_anzahl', 1)
            naechste = request.form.get('naechste_faelligkeit', '')
            try:
                pid = services.create_wartungsplan(conn, wartung_id, einheit, anzahl, naechste)
                conn.commit()
                flash('Wartungsplan angelegt.', 'success')
                return redirect(url_for('wartungen.plan_detail', plan_id=pid))
            except ValueError as e:
                flash(str(e), 'danger')
    return render_template(
        'wartungen/plan_form.html',
        wartung=w,
        plan=None,
        title='Neuer Wartungsplan',
    )


@wartungen_bp.route('/plan/<int:plan_id>', methods=['GET'])
@login_required
def plan_detail(plan_id):
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartungsplan_zugriff(mitarbeiter_id, plan_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        p = services.get_plan(conn, plan_id)
        w = services.get_wartung(conn, p['WartungID'])
        durch = services.list_durchfuehrungen_fuer_plan(conn, plan_id)
    return render_template(
        'wartungen/plan_detail.html',
        plan=p,
        wartung=w,
        durchfuehrungen=durch,
        kann_plan_edit=kann_wartungsplan_pflegen(),
    )


@wartungen_bp.route('/plan/<int:plan_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def plan_bearbeiten(plan_id):
    if not kann_wartungsplan_pflegen():
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartungsplan_zugriff(mitarbeiter_id, plan_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        p = services.get_plan(conn, plan_id)
        w = services.get_wartung(conn, p['WartungID'])
        if request.method == 'POST':
            einheit = request.form.get('intervall_einheit', '')
            anzahl = request.form.get('intervall_anzahl', 1)
            naechste = request.form.get('naechste_faelligkeit', '')
            aktiv = request.form.get('aktiv') == '1'
            try:
                services.update_wartungsplan(conn, plan_id, einheit, anzahl, naechste, aktiv)
                conn.commit()
                flash('Gespeichert.', 'success')
                return redirect(url_for('wartungen.plan_detail', plan_id=plan_id))
            except ValueError as e:
                flash(str(e), 'danger')
    return render_template(
        'wartungen/plan_form.html',
        wartung=w,
        plan=p,
        title='Wartungsplan bearbeiten',
    )


@wartungen_bp.route('/plan/<int:plan_id>/durchfuehrung/neu', methods=['GET', 'POST'])
@login_required
def durchfuehrung_neu(plan_id):
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartungsplan_zugriff(mitarbeiter_id, plan_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        p = services.get_plan(conn, plan_id)
        w = services.get_wartung(conn, p['WartungID'])
        mitarbeiter = conn.execute('''
            SELECT ID, Vorname, Nachname, Personalnummer FROM Mitarbeiter
            WHERE Aktiv = 1 ORDER BY Nachname, Vorname
        ''').fetchall()
        fremdfirmen = services.list_fremdfirmen(conn, nur_aktiv=True)
        if request.method == 'POST':
            dt = _parse_datetime_local(request.form.get('durchgefuehrt_am'))
            if not dt:
                flash('Datum/Zeit der Durchführung ist erforderlich.', 'danger')
            else:
                mit_ids = request.form.getlist('mitarbeiter_id[]')
                ff_rows = _collect_fremdfirma_zeilen_from_form()
                teil, err = services.validate_teilnehmer(mit_ids, ff_rows)
                if err:
                    flash(err, 'danger')
                else:
                    try:
                        dfid = services.insert_wartungsdurchfuehrung(
                            conn, plan_id, dt, request.form.get('bemerkung', ''), teil, mitarbeiter_id,
                        )
                        sb_files = [f for f in request.files.getlist('file') if f and f.filename]
                        sb_besch = request.form.get('servicebericht_beschreibung', '')
                        sb_typ = request.form.get('servicebericht_typ', '')
                        n_sb, sb_errs = _save_serviceberichte_files(
                            conn, dfid, mitarbeiter_id, sb_files, sb_besch, sb_typ,
                        )
                        for e in sb_errs:
                            flash(e, 'warning')
                        conn.commit()
                        msg = 'Durchführung protokolliert.'
                        if n_sb:
                            msg += f' {n_sb} Servicebericht(e) gespeichert.'
                        flash(msg, 'success')
                        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=dfid))
                    except Exception as e:
                        flash(f'Fehler: {e}', 'danger')
    return render_template(
        'wartungen/durchfuehrung_form.html',
        plan=p,
        wartung=w,
        mitarbeiter=mitarbeiter,
        fremdfirmen=fremdfirmen,
        batch=False,
        plan_optionen=[],
    )


@wartungen_bp.route('/durchfuehrung/mehrere', methods=['GET', 'POST'])
@login_required
def durchfuehrung_mehrere():
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    with get_db_connection() as conn:
        plan_optionen = services.plaene_options_fuer_select(conn, mitarbeiter_id, adm)
        mitarbeiter = conn.execute('''
            SELECT ID, Vorname, Nachname, Personalnummer FROM Mitarbeiter
            WHERE Aktiv = 1 ORDER BY Nachname, Vorname
        ''').fetchall()
        fremdfirmen = services.list_fremdfirmen(conn, nur_aktiv=True)
        if request.method == 'POST':
            dt = _parse_datetime_local(request.form.get('durchgefuehrt_am'))
            if not dt:
                flash('Datum/Zeit ist erforderlich.', 'danger')
            else:
                mit_ids = request.form.getlist('mitarbeiter_id[]')
                ff_rows = _collect_fremdfirma_zeilen_from_form()
                teil, err = services.validate_teilnehmer(mit_ids, ff_rows)
                if err:
                    flash(err, 'danger')
                else:
                    pids = request.form.getlist('plan_id[]')
                    bems = request.form.getlist('plan_bemerkung[]')
                    pairs = []
                    for i, raw in enumerate(pids):
                        raw = (raw or '').strip()
                        if not raw:
                            continue
                        try:
                            pid = int(raw)
                        except ValueError:
                            continue
                        bem = bems[i].strip() if i < len(bems) else ''
                        pairs.append((pid, bem))
                    if not pairs:
                        flash('Mindestens einen Wartungsplan auswählen.', 'danger')
                    else:
                        if len({x[0] for x in pairs}) != len(pairs):
                            flash('Jeder Wartungsplan nur einmal pro Eintrag.', 'danger')
                        else:
                            ok_all = True
                            for pid, _ in pairs:
                                if not hat_wartungsplan_zugriff(mitarbeiter_id, pid, conn):
                                    flash('Kein Zugriff auf einen der gewählten Pläne.', 'danger')
                                    ok_all = False
                                    break
                            if ok_all:
                                try:
                                    for pid, bem in pairs:
                                        services.insert_wartungsdurchfuehrung(
                                            conn, pid, dt, bem, teil, mitarbeiter_id,
                                        )
                                    conn.commit()
                                    flash(f'{len(pairs)} Durchführungen gespeichert.', 'success')
                                    return redirect(url_for('wartungen.plaene_uebersicht'))
                                except Exception as e:
                                    flash(f'Fehler: {e}', 'danger')
    return render_template(
        'wartungen/durchfuehrung_form.html',
        plan=None,
        wartung=None,
        mitarbeiter=mitarbeiter,
        fremdfirmen=fremdfirmen,
        batch=True,
        plan_optionen=plan_optionen,
    )


@wartungen_bp.route('/durchfuehrung/<int:durchfuehrung_id>', methods=['GET', 'POST'])
@login_required
def durchfuehrung_detail(durchfuehrung_id):
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    with get_db_connection() as conn:
        if not hat_wartungsdurchfuehrung_zugriff(mitarbeiter_id, durchfuehrung_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        if request.method == 'POST':
            eids = request.form.getlist('ersatzteil_id[]')
            mengen = request.form.getlist('ersatzteil_menge[]')
            bems = request.form.getlist('ersatzteil_bemerkung[]')
            ks = request.form.getlist('ersatzteil_kostenstelle[]')
            n = services.process_ersatzteile_fuer_wartungsdurchfuehrung(
                durchfuehrung_id, eids, mengen, bems, mitarbeiter_id, conn,
                is_admin=adm, ersatzteil_kostenstellen=ks,
            )
            conn.commit()
            flash(f'{n} Lagerbuchung(en) ausgeführt.', 'success')
            return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))
        d, mit, ff, lager = services.get_durchfuehrung_detail(conn, durchfuehrung_id)
        if not d:
            flash('Nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        serviceberichte = get_dateien_fuer_bereich(
            BEREICH_TYP_WARTUNGSDURCHFUEHRUNG, durchfuehrung_id, conn
        )
        ersatzteile = services.get_verfuegbare_ersatzteile(conn, mitarbeiter_id, adm)
        kostenstellen = conn.execute(
            'SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung'
        ).fetchall()
    return render_template(
        'wartungen/durchfuehrung_detail.html',
        d=d,
        mitarbeitende=mit,
        fremd=ff,
        lagerbuchungen=lager,
        serviceberichte=serviceberichte,
        ersatzteile=ersatzteile,
        kostenstellen=kostenstellen,
    )


@wartungen_bp.route('/durchfuehrung-datei/<path:filepath>')
@login_required
def durchfuehrung_datei(filepath):
    filepath = filepath.replace('\\', '/')
    if not filepath.startswith('Wartungen/durchfuehrung/'):
        flash('Ungültiger Pfad.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    parts = filepath.split('/')
    if len(parts) < 5 or parts[3] != 'serviceberichte':
        flash('Ungültiger Pfad.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    try:
        dfid = int(parts[2])
    except ValueError:
        flash('Ungültiger Pfad.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartungsdurchfuehrung_zugriff(mitarbeiter_id, dfid, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        row = conn.execute(
            '''SELECT 1 FROM Datei WHERE BereichTyp = ? AND BereichID = ? AND Dateipfad = ?''',
            (BEREICH_TYP_WARTUNGSDURCHFUEHRUNG, dfid, filepath),
        ).fetchone()
        if not row:
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=dfid))
    fs = filepath.replace('/', os.sep)
    full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], fs)
    if not os.path.exists(full_path):
        flash('Datei nicht gefunden.', 'danger')
        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=dfid))
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))


@wartungen_bp.route(
    '/durchfuehrung/<int:durchfuehrung_id>/servicebericht/<int:datei_id>/loeschen',
    methods=['POST'],
)
@login_required
def durchfuehrung_servicebericht_loeschen(durchfuehrung_id, datei_id):
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartungsdurchfuehrung_zugriff(mitarbeiter_id, durchfuehrung_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        row = conn.execute(
            '''SELECT Dateipfad FROM Datei WHERE ID = ? AND BereichTyp = ? AND BereichID = ?''',
            (datei_id, BEREICH_TYP_WARTUNGSDURCHFUEHRUNG, durchfuehrung_id),
        ).fetchone()
        if not row:
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))
        fp = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], row['Dateipfad'].replace('/', os.sep))
        loesche_datei(datei_id, conn)
        conn.commit()
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
        flash('Servicebericht gelöscht.', 'success')
        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))


@wartungen_bp.route('/durchfuehrung/<int:durchfuehrung_id>/servicebericht/upload', methods=['POST'])
@login_required
def durchfuehrung_servicebericht_upload(durchfuehrung_id):
    mitarbeiter_id = session.get('user_id')
    files = [f for f in request.files.getlist('file') if f and f.filename]
    if not files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))
    besch = request.form.get('beschreibung', '')
    typ_f = request.form.get('typ', '')
    with get_db_connection() as conn:
        if not hat_wartungsdurchfuehrung_zugriff(mitarbeiter_id, durchfuehrung_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        n_ok, errs = _save_serviceberichte_files(
            conn, durchfuehrung_id, mitarbeiter_id, files, besch, typ_f,
        )
        conn.commit()
    for e in errs:
        flash(e, 'warning')
    if n_ok:
        flash(f'{n_ok} Datei(en) hochgeladen.', 'success')
    return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))


@wartungen_bp.route('/datei/<path:filepath>')
@login_required
def wartung_datei(filepath):
    filepath = filepath.replace('\\', '/')
    if not filepath.startswith('Wartungen/'):
        flash('Ungültiger Pfad.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    parts = filepath.split('/')
    mitarbeiter_id = session.get('user_id')
    if len(parts) >= 2:
        try:
            wid = int(parts[1])
            with get_db_connection() as conn:
                if not hat_wartung_zugriff(mitarbeiter_id, wid, conn):
                    flash('Kein Zugriff.', 'danger')
                    return redirect(url_for('wartungen.wartung_liste'))
        except ValueError:
            pass
    fs = filepath.replace('/', os.sep)
    full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], fs)
    if not os.path.exists(full_path):
        flash('Datei nicht gefunden.', 'danger')
        return redirect(url_for('wartungen.wartung_liste'))
    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))


@wartungen_bp.route('/datei-loeschen/<int:datei_id>', methods=['POST'])
@login_required
def wartung_datei_loeschen(datei_id):
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT BereichID, Dateipfad FROM Datei WHERE ID = ? AND BereichTyp = ?',
            (datei_id, 'Wartung'),
        ).fetchone()
        if not row:
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        wid = row['BereichID']
        if not hat_wartung_stamm_bearbeiten(mitarbeiter_id, wid, conn):
            flash('Keine Berechtigung zum Löschen.', 'danger')
            return redirect(url_for('wartungen.wartung_bearbeiten', wartung_id=wid))
        fp = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], row['Dateipfad'].replace('/', os.sep))
        loesche_datei(datei_id, conn)
        conn.commit()
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
        flash('Datei gelöscht.', 'success')
        return redirect(url_for('wartungen.wartung_bearbeiten', wartung_id=wid))
