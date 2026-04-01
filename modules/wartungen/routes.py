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
    originale_loeschen_aus_formular,
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
    kann_wartung_protokollieren,
    is_admin,
)


def _dateien_display_fuer_wartung(wartung_id, conn, upload_base_folder):
    """Datei-Zeilen für Templates (wie Ersatzteil-Detail)."""
    rows = get_dateien_fuer_bereich('Wartung', wartung_id, conn)
    dateien = []
    for d in rows:
        filepath = os.path.join(upload_base_folder, d['Dateipfad'].replace('/', os.sep))
        file_size = 0
        modified = None
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            modified = datetime.fromtimestamp(os.path.getmtime(filepath))
        datei_dict = dict(d)
        datei_dict.update({
            'name': d['Dateiname'],
            'path': d['Dateipfad'],
            'size': file_size,
            'modified': modified,
            'id': d['ID'],
            'beschreibung': d['Beschreibung'] or '',
        })
        dateien.append(datei_dict)
    return dateien


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


def _query_int_arg(name):
    """Positives Integer aus request.args oder None (fehlt/ungültig)."""
    raw = (request.args.get(name) or '').strip()
    if not raw or not raw.isdigit():
        return None
    return int(raw)


def _prefill_durchgefuehrt_am_datetime_local():
    """Wert für datetime-local-Feld: jetzt oder letzter POST nach Validierungsfehler."""
    raw = (request.form.get('durchgefuehrt_am') or '').strip()
    if raw:
        return raw
    return datetime.now().strftime('%Y-%m-%dT%H:%M')


PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT = 'jahresuebersicht'


def _jahresuebersicht_protokoll_query_args(jahr, bereich_id, gewerk_id):
    """Query-Parameter für durchfuehrung_neu, wenn der Aufruf von der Jahresübersicht kommt."""
    q = {'herkunft': PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT, 'jahr': jahr}
    if bereich_id is not None:
        q['bereich_id'] = bereich_id
    if gewerk_id is not None:
        q['gewerk_id'] = gewerk_id
    return q


def _parse_protokoll_kontext_args(args):
    """Herkunft + Filter aus GET-Query (werkzeug MultiDict)."""
    h = (args.get('protokoll_herkunft') or args.get('herkunft') or '').strip()
    if h != PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT:
        return {'herkunft': '', 'jahr': None, 'bereich_id': None, 'gewerk_id': None}
    cy = datetime.now().year
    jahr = args.get('jahr', type=int)
    if jahr is None or jahr < 1990 or jahr > 2100:
        jahr = cy
    bid = args.get('bereich_id', type=int)
    gid = args.get('gewerk_id', type=int)
    return {'herkunft': h, 'jahr': jahr, 'bereich_id': bid, 'gewerk_id': gid}


def _parse_protokoll_kontext_form(form):
    """Herkunft + Filter aus POST (versteckte Felder)."""
    h = (form.get('protokoll_herkunft') or '').strip()
    if h != PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT:
        return {'herkunft': '', 'jahr': None, 'bereich_id': None, 'gewerk_id': None}
    cy = datetime.now().year
    try:
        jahr = int(form.get('jahr') or cy)
    except (TypeError, ValueError):
        jahr = cy
    if jahr < 1990 or jahr > 2100:
        jahr = cy
    bid = form.get('bereich_id')
    gid = form.get('gewerk_id')
    try:
        bid = int(bid) if bid not in (None, '') else None
    except (TypeError, ValueError):
        bid = None
    try:
        gid = int(gid) if gid not in (None, '') else None
    except (TypeError, ValueError):
        gid = None
    return {'herkunft': h, 'jahr': jahr, 'bereich_id': bid, 'gewerk_id': gid}


def _url_jahresuebersicht_mit_protokoll_kontext(kontext):
    """Redirect/Zurück-Link zur Jahresmatrix inkl. Filter."""
    if kontext.get('herkunft') != PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT:
        return url_for('wartungen.jahresuebersicht')
    q = {'jahr': kontext['jahr']}
    if kontext.get('bereich_id') is not None:
        q['bereich_id'] = kontext['bereich_id']
    if kontext.get('gewerk_id') is not None:
        q['gewerk_id'] = kontext['gewerk_id']
    return url_for('wartungen.jahresuebersicht', **q)


def _query_iso_date_arg(name):
    """YYYY-MM-DD aus request.args oder None."""
    raw = (request.args.get(name) or '').strip()[:10]
    if not raw or len(raw) != 10:
        return None
    try:
        datetime.strptime(raw, '%Y-%m-%d')
        return raw
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
    bereich_id = _query_int_arg('bereich_id')
    gewerk_id = _query_int_arg('gewerk_id')

    with get_db_connection() as conn:
        bereiche = services.list_bereiche_fuer_wartungen_sichtbar(conn, mitarbeiter_id, adm)
        valid_bereich_ids = {b['ID'] for b in bereiche}
        if bereich_id is not None and bereich_id not in valid_bereich_ids:
            bereich_id = None
        gewerke = services.list_gewerke_fuer_wartung_liste_filter(
            conn, mitarbeiter_id, adm, bereich_id,
        )
        valid_gewerk_ids = {g['ID'] for g in gewerke}
        if gewerk_id is not None and gewerk_id not in valid_gewerk_ids:
            gewerk_id = None
        rows = services.list_wartungen(
            conn, mitarbeiter_id, adm, bereich_id=bereich_id, gewerk_id=gewerk_id,
        )
    return render_template(
        'wartungen/wartung_liste.html',
        wartungen=rows,
        bereiche=bereiche,
        gewerke=gewerke,
        bereich_id=bereich_id,
        gewerk_id=gewerk_id,
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
        title='Neue Wartung',
    )


@wartungen_bp.route('/<int:wartung_id>')
@login_required
def wartung_detail(wartung_id):
    mitarbeiter_id = session.get('user_id')
    adm = 'admin' in session.get('user_berechtigungen', [])
    upload_base = current_app.config['UPLOAD_BASE_FOLDER']
    with get_db_connection() as conn:
        w = services.get_wartung(conn, wartung_id)
        if not w:
            flash('Wartung nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        if not hat_wartung_zugriff(mitarbeiter_id, wartung_id, conn):
            flash('Kein Zugriff auf diese Wartung.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        highlight_plan_id = request.args.get('plan_id', type=int)
        if highlight_plan_id is not None:
            pl_row = services.get_plan(conn, highlight_plan_id)
            if not pl_row or pl_row['WartungID'] != wartung_id:
                highlight_plan_id = None
        kann_edit = hat_wartung_stamm_bearbeiten(mitarbeiter_id, wartung_id, conn)
        dateien = _dateien_display_fuer_wartung(wartung_id, conn, upload_base)
        plaene = services.list_plaene_fuer_wartung(conn, wartung_id)
        durchfuehrungen = services.list_durchfuehrungen_fuer_wartung(conn, wartung_id)
        abt_rows = services.get_wartung_abteilungen(conn, wartung_id)
    sichtbar_labels = ', '.join(a['Bezeichnung'] for a in abt_rows) or '–'
    return render_template(
        'wartungen/wartung_detail.html',
        wartung=w,
        dateien=dateien,
        plaene=plaene,
        durchfuehrungen=durchfuehrungen,
        kann_edit=kann_edit,
        kann_plan=kann_wartungsplan_pflegen(),
        kann_protokollieren=kann_wartung_protokollieren(),
        sichtbare_abteilungen_text=sichtbar_labels,
        is_admin=adm,
        highlight_plan_id=highlight_plan_id,
    )


@wartungen_bp.route('/<int:wartung_id>/datei/upload', methods=['POST'])
@login_required
def wartung_datei_upload(wartung_id):
    mitarbeiter_id = session.get('user_id')
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('wartungen.wartung_detail', wartung_id=wartung_id))
    files = [f for f in request.files.getlist('file') if f and f.filename]
    beschreibung = request.form.get('beschreibung', '').strip()
    typ = request.form.get('typ', '').strip()
    if not files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('wartungen.wartung_detail', wartung_id=wartung_id))
    allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    allowed_document_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    try:
        with get_db_connection() as conn:
            if not hat_wartung_stamm_bearbeiten(mitarbeiter_id, wartung_id, conn):
                flash('Keine Berechtigung zum Hochladen.', 'danger')
                return redirect(url_for('wartungen.wartung_liste'))
            w = services.get_wartung(conn, wartung_id)
            if not w:
                flash('Wartung nicht gefunden.', 'danger')
                return redirect(url_for('wartungen.wartung_liste'))
            erfolgreich = 0
            fehler = []
            for file in files:
                try:
                    original_filename = file.filename
                    datei_typ = get_datei_typ_aus_dateiname(original_filename)
                    if datei_typ == 'Bild' or any(
                        original_filename.lower().endswith(f'.{ext}') for ext in allowed_image_extensions
                    ):
                        upload_folder = os.path.join(
                            current_app.config['WARTUNG_UPLOAD_FOLDER'], str(wartung_id), 'bilder',
                        )
                        subfolder = 'bilder'
                        allowed_extensions = allowed_image_extensions
                    else:
                        upload_folder = os.path.join(
                            current_app.config['WARTUNG_UPLOAD_FOLDER'], str(wartung_id), 'dokumente',
                        )
                        subfolder = 'dokumente'
                        allowed_extensions = allowed_document_extensions
                    if not validate_file_extension(original_filename, allowed_extensions):
                        fehler.append(f'{original_filename}: Dateityp nicht erlaubt')
                        continue
                    create_upload_folder(upload_folder)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    file.filename = timestamp + secure_filename(original_filename)
                    success_upload, filename, error_message = save_uploaded_file(
                        file, upload_folder, allowed_extensions=None,
                    )
                    if not success_upload or error_message:
                        fehler.append(f'{original_filename}: {error_message}')
                        continue
                    relative_path = f'Wartungen/{wartung_id}/{subfolder}/{filename}'
                    datei_typ_final = typ if typ else datei_typ
                    speichere_datei(
                        bereich_typ='Wartung',
                        bereich_id=wartung_id,
                        dateiname=original_filename,
                        dateipfad=relative_path,
                        beschreibung=beschreibung,
                        typ=datei_typ_final,
                        mitarbeiter_id=mitarbeiter_id,
                        conn=conn,
                    )
                    loesche_import_kopie_nach_upload(
                        original_filename,
                        current_app.config['IMPORT_FOLDER'],
                        originale_loeschen_aus_formular(),
                    )
                    erfolgreich += 1
                except Exception as e:
                    fehler.append(f'{getattr(file, "filename", "?")}: {e}')
            conn.commit()
            if erfolgreich > 0:
                flash(
                    'Datei erfolgreich hochgeladen.' if erfolgreich == 1
                    else f'{erfolgreich} Datei(en) erfolgreich hochgeladen.',
                    'success',
                )
            if fehler:
                fehler_text = '; '.join(fehler[:5])
                if len(fehler) > 5:
                    fehler_text += f' … und {len(fehler) - 5} weitere'
                flash(f'Fehler beim Hochladen: {fehler_text}', 'danger')
    except Exception as e:
        flash(f'Fehler beim Hochladen: {e}', 'danger')
    ziel_plan_id = request.form.get('ziel_plan_id', type=int)
    if ziel_plan_id:
        try:
            with get_db_connection() as conn:
                pl = services.get_plan(conn, ziel_plan_id)
                if (
                    pl
                    and pl['WartungID'] == wartung_id
                    and hat_wartungsplan_zugriff(mitarbeiter_id, ziel_plan_id, conn)
                ):
                    return redirect(
                        url_for(
                            'wartungen.wartung_detail',
                            wartung_id=wartung_id,
                            plan_id=ziel_plan_id,
                        )
                    )
        except Exception:
            pass
    return redirect(url_for('wartungen.wartung_detail', wartung_id=wartung_id))


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
        if request.method == 'POST':
            if not kann_edit:
                flash('Keine Berechtigung zum Bearbeiten des Stamms.', 'danger')
                return redirect(url_for('wartungen.wartung_detail', wartung_id=wartung_id))
            gewerk_id = request.form.get('gewerk_id', type=int)
            bez = request.form.get('bezeichnung', '')
            besch = request.form.get('beschreibung', '')
            aktiv = request.form.get('aktiv') == '1'
            sab = request.form.getlist('sichtbare_abteilungen')
            if not gewerk_id or not bez.strip():
                flash('Gewerk und Bezeichnung sind Pflichtfelder.', 'danger')
            else:
                services.update_wartung(conn, wartung_id, gewerk_id, bez, besch, aktiv, sab)
                conn.commit()
                flash('Gespeichert.', 'success')
                return redirect(url_for('wartungen.wartung_detail', wartung_id=wartung_id))
    return render_template(
        'wartungen/wartung_form.html',
        gewerke=gewerke,
        abteilungen=abteilungen,
        wartung=w,
        gewaehlte_abteilungen=ga,
        kann_edit=kann_edit,
        title='Wartung bearbeiten',
    )


@wartungen_bp.route('/plaene')
@login_required
def plaene_uebersicht():
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    bereich_id = _query_int_arg('bereich_id')
    gewerk_id = _query_int_arg('gewerk_id')
    plan_order = (request.args.get('plan_order') or 'stamm').strip().lower()
    if plan_order == 'faelligkeit_asc':
        sort_mode, sort_dir = 'faelligkeit', 'asc'
    elif plan_order == 'faelligkeit_desc':
        sort_mode, sort_dir = 'faelligkeit', 'desc'
    else:
        plan_order = 'stamm'
        sort_mode, sort_dir = 'stamm', 'asc'
    with get_db_connection() as conn:
        bereiche = services.list_bereiche_fuer_plaene_sichtbar(conn, mitarbeiter_id, adm)
        valid_bereich_ids = {b['ID'] for b in bereiche}
        if bereich_id is not None and bereich_id not in valid_bereich_ids:
            bereich_id = None
        gewerke = services.list_gewerke_fuer_plan_liste_filter(
            conn, mitarbeiter_id, adm, bereich_id,
        )
        valid_gewerk_ids = {g['ID'] for g in gewerke}
        if gewerk_id is not None and gewerk_id not in valid_gewerk_ids:
            gewerk_id = None
        rows = services.list_plaene_sichtbar(
            conn,
            mitarbeiter_id,
            adm,
            bereich_id=bereich_id,
            gewerk_id=gewerk_id,
            sort_mode=sort_mode,
            sort_dir=sort_dir,
        )
    return render_template(
        'wartungen/plan_uebersicht.html',
        plaene=rows,
        bereiche=bereiche,
        gewerke=gewerke,
        bereich_id=bereich_id,
        gewerk_id=gewerk_id,
        plan_order=plan_order,
    )


@wartungen_bp.route('/durchfuehrungen')
@login_required
def durchfuehrungen_chronologisch():
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    bereich_id = _query_int_arg('bereich_id')
    gewerk_id = _query_int_arg('gewerk_id')
    wartung_id = _query_int_arg('wartung_id')
    datum_von = _query_iso_date_arg('datum_von')
    datum_bis = _query_iso_date_arg('datum_bis')
    if datum_von and datum_bis and datum_von > datum_bis:
        datum_von, datum_bis = datum_bis, datum_von

    with get_db_connection() as conn:
        bereiche = services.list_bereiche_fuer_wartungen_sichtbar(conn, mitarbeiter_id, adm)
        if not bereiche:
            return render_template(
                'wartungen/durchfuehrungen_chronologisch.html',
                bereiche=[],
                gewerke=[],
                wartungen_filter=[],
                durchfuehrungen=[],
                bereich_id=None,
                gewerk_id=None,
                wartung_id=None,
                datum_von=None,
                datum_bis=None,
                title='Protokollierte Wartungen',
            )

        valid_bereich_ids = {b['ID'] for b in bereiche}
        if bereich_id is not None and bereich_id not in valid_bereich_ids:
            bereich_id = None

        gewerke = services.list_gewerke_fuer_wartung_liste_filter(
            conn, mitarbeiter_id, adm, bereich_id,
        )
        valid_gewerk_ids = {g['ID'] for g in gewerke}
        if gewerk_id is not None and gewerk_id not in valid_gewerk_ids:
            gewerk_id = None

        wartungen_filter = services.list_wartungen(
            conn, mitarbeiter_id, adm, bereich_id=bereich_id, gewerk_id=gewerk_id,
        )
        valid_wartung_ids = {w['ID'] for w in wartungen_filter}
        if wartung_id is not None and wartung_id not in valid_wartung_ids:
            wartung_id = None

        rows = services.list_durchfuehrungen_chronologisch_sichtbar(
            conn,
            mitarbeiter_id,
            adm,
            bereich_id=bereich_id,
            gewerk_id=gewerk_id,
            wartung_id=wartung_id,
            datum_von=datum_von,
            datum_bis=datum_bis,
        )

    return render_template(
        'wartungen/durchfuehrungen_chronologisch.html',
        bereiche=bereiche,
        gewerke=gewerke,
        wartungen_filter=wartungen_filter,
        durchfuehrungen=rows,
        bereich_id=bereich_id,
        gewerk_id=gewerk_id,
        wartung_id=wartung_id,
        datum_von=datum_von,
        datum_bis=datum_bis,
        title='Protokollierte Wartungen',
    )


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


def _jahresmatrix_grouped(wartungen, drows):
    """Baut Zellen pro Wartung und gruppiert nach Bereich · Gewerk (Sortierung der Liste vorausgesetzt)."""
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
        matrix_rows.append({
            'wartung': w,
            'cells': cells,
            'bereich': w['Bereich'],
            'gewerk': w['Gewerk'],
        })

    groups = []
    cur_key = None
    bucket = []
    for row in matrix_rows:
        k = (row['bereich'], row['gewerk'])
        if cur_key is not None and k != cur_key:
            groups.append({'bereich': cur_key[0], 'gewerk': cur_key[1], 'rows': bucket})
            bucket = []
        cur_key = k
        bucket.append(row)
    if bucket and cur_key is not None:
        groups.append({'bereich': cur_key[0], 'gewerk': cur_key[1], 'rows': bucket})
    return groups


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

    jahr = request.args.get('jahr', type=int)
    if jahr is None or jahr < 1990 or jahr > 2100:
        jahr = cy
    if jahr not in jahre:
        jahre = sorted(set(jahre + [jahr]), reverse=True)

    with get_db_connection() as conn:
        bereiche = services.list_bereiche_fuer_wartungen_sichtbar(conn, mitarbeiter_id, adm)
        if not bereiche:
            return render_template(
                'wartungen/jahresuebersicht.html',
                bereiche=[],
                gewerke=[],
                bereich_id=None,
                gewerk_id=None,
                jahr=jahr,
                jahre=jahre,
                monatsnamen=monatsnamen,
                matrix_groups=[],
                kann_protokollieren=kann_wartung_protokollieren(),
                title='Wartungen – Jahresübersicht',
                jahresuebersicht_protokoll_query=_jahresuebersicht_protokoll_query_args(
                    jahr, _query_int_arg('bereich_id'), _query_int_arg('gewerk_id'),
                ),
            )

        bereich_id = _query_int_arg('bereich_id')
        valid_bereich_ids = {b['ID'] for b in bereiche}
        if bereich_id is not None and bereich_id not in valid_bereich_ids:
            bereich_id = None

        gewerke = services.list_gewerke_fuer_wartung_liste_filter(
            conn, mitarbeiter_id, adm, bereich_id,
        )
        gewerk_id = _query_int_arg('gewerk_id')
        valid_gewerk_ids = {g['ID'] for g in gewerke}
        if gewerk_id is not None and gewerk_id not in valid_gewerk_ids:
            gewerk_id = None

        matrix_groups = []
        if gewerke:
            wartungen = services.list_wartungen_jahresuebersicht(
                conn, mitarbeiter_id, adm, bereich_id=bereich_id, gewerk_id=gewerk_id,
            )
            drows = services.list_durchfuehrungen_jahresuebersicht(
                conn, jahr, mitarbeiter_id, adm, bereich_id=bereich_id, gewerk_id=gewerk_id,
            )
            matrix_groups = _jahresmatrix_grouped(wartungen, drows)
            wid_list = []
            for g in matrix_groups:
                for row in g['rows']:
                    wid_list.append(row['wartung']['ID'])
            plan_map = services.map_wartung_zu_aktiven_plan_ids(
                conn, wid_list, mitarbeiter_id, adm,
                bereich_id=bereich_id, gewerk_id=gewerk_id,
            )
            plan_meta_map = services.map_wartung_aktive_plaene_metadaten(
                conn, wid_list, mitarbeiter_id, adm,
                bereich_id=bereich_id, gewerk_id=gewerk_id,
            )
            for g in matrix_groups:
                for row in g['rows']:
                    wid = row['wartung']['ID']
                    row['aktive_plan_ids'] = plan_map.get(wid, [])
                    row['aktive_plaene_meta'] = plan_meta_map.get(wid, [])

    return render_template(
        'wartungen/jahresuebersicht.html',
        bereiche=bereiche,
        gewerke=gewerke,
        bereich_id=bereich_id,
        gewerk_id=gewerk_id,
        jahr=jahr,
        jahre=jahre,
        monatsnamen=monatsnamen,
        matrix_groups=matrix_groups,
        kann_protokollieren=kann_wartung_protokollieren(),
        title='Wartungen – Jahresübersicht',
        jahresuebersicht_protokoll_query=_jahresuebersicht_protokoll_query_args(
            jahr, bereich_id, gewerk_id,
        ),
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
            hat_fest = request.form.get('hat_festes_intervall') == '1'
            try:
                pid = services.create_wartungsplan(
                    conn, wartung_id, einheit, anzahl, naechste, hat_festes_intervall=hat_fest,
                )
                conn.commit()
                flash('Wartungsplan angelegt.', 'success')
                return redirect(
                    url_for('wartungen.wartung_detail', wartung_id=wartung_id, plan_id=pid)
                )
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
    """Kompatibilität: leitet auf die Wartungsdetailseite mit Hervorhebung des Plans weiter."""
    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        if not hat_wartungsplan_zugriff(mitarbeiter_id, plan_id, conn):
            flash('Kein Zugriff.', 'danger')
            return redirect(url_for('wartungen.wartung_liste'))
        p = services.get_plan(conn, plan_id)
        if not p:
            flash('Wartungsplan nicht gefunden.', 'danger')
            return redirect(url_for('wartungen.plaene_uebersicht'))
        wid = p['WartungID']
    return redirect(url_for('wartungen.wartung_detail', wartung_id=wid, plan_id=plan_id))


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
            hat_fest = request.form.get('hat_festes_intervall') == '1'
            try:
                services.update_wartungsplan(
                    conn, plan_id, einheit, anzahl, naechste, aktiv,
                    hat_festes_intervall=hat_fest,
                )
                conn.commit()
                flash('Gespeichert.', 'success')
                w_id = p['WartungID']
                return redirect(
                    url_for('wartungen.wartung_detail', wartung_id=w_id, plan_id=plan_id)
                )
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
    if not kann_wartung_protokollieren():
        flash('Keine Berechtigung zum Protokollieren von Wartungen.', 'danger')
        return redirect(url_for('wartungen.plaene_uebersicht'))
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    kontext = (
        _parse_protokoll_kontext_form(request.form)
        if request.method == 'POST'
        else _parse_protokoll_kontext_args(request.args)
    )
    zurueck_jahres_url = None
    if kontext.get('herkunft') == PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT:
        zurueck_jahres_url = _url_jahresuebersicht_mit_protokoll_kontext(kontext)
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
        kostenstellen = conn.execute(
            'SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung',
        ).fetchall()
        if request.method == 'POST':
            speichern_aktion = (request.form.get('speichern_aktion') or 'detail').strip()
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
                        dfid, naechste_plan = services.insert_wartungsdurchfuehrung(
                            conn, plan_id, dt, request.form.get('bemerkung', ''), teil, mitarbeiter_id,
                        )
                        sb_files = [f for f in request.files.getlist('file') if f and f.filename]
                        sb_besch = request.form.get('servicebericht_beschreibung', '')
                        sb_typ = request.form.get('servicebericht_typ', '')
                        n_sb, sb_errs = _save_serviceberichte_files(
                            conn, dfid, mitarbeiter_id, sb_files, sb_besch, sb_typ,
                        )
                        eids = request.form.getlist('ersatzteil_id[]')
                        mengen = request.form.getlist('ersatzteil_menge[]')
                        bems = request.form.getlist('ersatzteil_bemerkung[]')
                        ks = request.form.getlist('ersatzteil_kostenstelle[]')
                        n_lb = services.process_ersatzteile_fuer_wartungsdurchfuehrung(
                            dfid, eids, mengen, bems, mitarbeiter_id, conn,
                            is_admin=adm, ersatzteil_kostenstellen=ks,
                        )
                        conn.commit()
                        for e in sb_errs:
                            flash(e, 'warning')
                        msg = 'Durchführung protokolliert.'
                        if n_sb:
                            msg += f' {n_sb} Servicebericht(e) gespeichert.'
                        if n_lb:
                            msg += f' {n_lb} Lagerbuchung(en) ausgeführt.'
                        if naechste_plan:
                            try:
                                d_fmt = datetime.strptime(naechste_plan, '%Y-%m-%d').strftime('%d.%m.%Y')
                            except ValueError:
                                d_fmt = naechste_plan
                            msg += f' Nächste Fälligkeit des Plans auf {d_fmt} gesetzt.'
                        flash(msg, 'success')
                        if (
                            speichern_aktion == 'jahresuebersicht'
                            and kontext.get('herkunft') == PROTOKOLL_HERKUNFT_JAHRESUEBERSICHT
                        ):
                            return redirect(_url_jahresuebersicht_mit_protokoll_kontext(kontext))
                        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=dfid))
                    except Exception as e:
                        conn.rollback()
                        flash(f'Fehler: {e}', 'danger')
    return render_template(
        'wartungen/durchfuehrung_form.html',
        plan=p,
        wartung=w,
        mitarbeiter=mitarbeiter,
        fremdfirmen=fremdfirmen,
        kostenstellen=kostenstellen,
        batch=False,
        plan_optionen=[],
        protokoll_kontext=kontext,
        zurueck_jahres_url=zurueck_jahres_url,
        durchgefuehrt_am_value=_prefill_durchgefuehrt_am_datetime_local(),
    )


@wartungen_bp.route('/durchfuehrung/mehrere', methods=['GET', 'POST'])
@login_required
def durchfuehrung_mehrere():
    if not kann_wartung_protokollieren():
        flash('Keine Berechtigung zum Protokollieren von Wartungen.', 'danger')
        return redirect(url_for('wartungen.plaene_uebersicht'))
    mitarbeiter_id = session.get('user_id')
    adm = is_admin()
    with get_db_connection() as conn:
        plan_optionen = services.plaene_options_fuer_select(conn, mitarbeiter_id, adm)
        vorausgewaehlte_plan_ids = []
        if request.method == 'GET':
            gesehen = set()
            for raw in request.args.getlist('plan_id'):
                try:
                    pid = int(raw)
                except (TypeError, ValueError):
                    continue
                if pid in gesehen:
                    continue
                gesehen.add(pid)
                if hat_wartungsplan_zugriff(mitarbeiter_id, pid, conn):
                    vorausgewaehlte_plan_ids.append(pid)
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
                                    naechste_aktualisiert = False
                                    for pid, bem in pairs:
                                        _, naechste_plan = services.insert_wartungsdurchfuehrung(
                                            conn, pid, dt, bem, teil, mitarbeiter_id,
                                        )
                                        if naechste_plan:
                                            naechste_aktualisiert = True
                                    conn.commit()
                                    msg_batch = f'{len(pairs)} Durchführungen gespeichert.'
                                    if naechste_aktualisiert:
                                        msg_batch += (
                                            ' Nächste Fälligkeit wurde bei den betroffenen aktiven Plänen angepasst.'
                                        )
                                    flash(msg_batch, 'success')
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
        vorausgewaehlte_plan_ids=vorausgewaehlte_plan_ids,
        protokoll_kontext=None,
        zurueck_jahres_url=None,
        kostenstellen=[],
        durchgefuehrt_am_value=_prefill_durchgefuehrt_am_datetime_local(),
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
            if not kann_wartung_protokollieren():
                flash('Keine Berechtigung zum Verbuchen.', 'danger')
                return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))
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
        kann_protokollieren=kann_wartung_protokollieren(),
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
    if not kann_wartung_protokollieren():
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))
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
    if not kann_wartung_protokollieren():
        flash('Keine Berechtigung zum Hochladen.', 'danger')
        return redirect(url_for('wartungen.durchfuehrung_detail', durchfuehrung_id=durchfuehrung_id))
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
            return redirect(url_for('wartungen.wartung_detail', wartung_id=wid))
        fp = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], row['Dateipfad'].replace('/', os.sep))
        loesche_datei(datei_id, conn)
        conn.commit()
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
        flash('Datei gelöscht.', 'success')
        return redirect(url_for('wartungen.wartung_detail', wartung_id=wid))
