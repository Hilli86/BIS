"""
Import Routes
Routes für Datei-Import-Funktionalität
"""

from flask import request, session, jsonify, current_app, send_from_directory, abort
import os
import re
import mimetypes
from werkzeug.utils import secure_filename
from . import import_bp
from utils.file_handling import get_file_list, move_file_safe, speichere_in_import_ordner
from utils import get_db_connection
from utils.auth_guards import is_authenticated_user
from utils.security import resolve_under_base, PathTraversalError
from utils.import_personal import (
    pfad_personlicher_import,
    resolve_import_dateipfad,
    resolve_import_dateipfad_auto,
)
from modules.ersatzteile.services import get_datei_typ_aus_dateiname


# Allowlist erlaubter ziel_ordner-Muster fuer /api/import/verschieben.
# Es werden ausschliesslich diese Muster akzeptiert (kein Pfad-Traversal,
# nur numerische IDs, keine Sonderzeichen ausser den unten angegebenen).
_ZIEL_ORDNER_MUSTER = tuple(
    re.compile(p) for p in (
        r'^Schichtbuch/Themen/\d+$',
        r'^Bestellwesen/Angebote/\d+$',
        r'^Bestellwesen/Lieferscheine/\d+$',
        r'^Bestellwesen/Auftragsbest[^/]+/\d+$',
        r'^Bestellwesen/Rechnungen/\d+$',
        r'^Angebote/Bestellungen/\d+$',
        r'^Ersatzteile/\d+/(bilder|dokumente)$',
        r'^Wartungen/\d+/(bilder|dokumente)$',
        r'^Wartungen/durchfuehrung/\d+/serviceberichte$',
    )
)


def _ziel_ordner_erlaubt(pfad):
    if not pfad or not isinstance(pfad, str):
        return False
    normalisiert = pfad.replace('\\', '/').strip().strip('/')
    if '..' in normalisiert.split('/'):
        return False
    return any(muster.match(normalisiert) for muster in _ZIEL_ORDNER_MUSTER)


def _ensure_session_personalnummer():
    """Füllt user_personalnummer nach (z. B. bestehende Session vor Deploy)."""
    if session.get('user_personalnummer'):
        return session['user_personalnummer']
    uid = session.get('user_id')
    if not uid:
        return None
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                'SELECT Personalnummer FROM Mitarbeiter WHERE ID = ? AND Aktiv = 1',
                (uid,),
            ).fetchone()
        if row and row['Personalnummer']:
            session['user_personalnummer'] = row['Personalnummer']
            return row['Personalnummer']
    except Exception:
        pass
    return None


@import_bp.route('/dateien', methods=['GET'])
def import_dateien_liste():
    """Liste Dateien im gemeinsamen Import-Ordner und optional im persönlichen Unterordner."""
    if not is_authenticated_user(session):
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401

    import_folder = current_app.config['IMPORT_FOLDER']

    if not os.path.exists(import_folder):
        return jsonify({'success': True, 'dateien': [], 'dateien_personal': []})

    try:
        dateien = get_file_list(import_folder, include_size=True)
        dateien_personal = []
        pn = _ensure_session_personalnummer()
        if pn:
            pdir = pfad_personlicher_import(import_folder, pn)
            if pdir and os.path.isdir(pdir):
                dateien_personal = get_file_list(pdir, include_size=True)
        return jsonify({'success': True, 'dateien': dateien, 'dateien_personal': dateien_personal})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Lesen des Import-Ordners: {str(e)}'}), 500


@import_bp.route('/anzeigen/<filename>')
def import_datei_anzeigen(filename):
    """
    Liefert eine Datei aus dem Import-Ordner (Vorschau im Browser, nur angemeldete Nutzer).
    Kein Pfad in der URL; Traversal wird abgewiesen.
    Optional: ?quelle=personal — Datei aus dem persönlichen Unterordner des angemeldeten Nutzers.
    """
    if not is_authenticated_user(session):
        abort(401)

    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        abort(400)

    import_folder = current_app.config['IMPORT_FOLDER']
    import_abs = os.path.abspath(import_folder)
    quelle = (request.args.get('quelle') or '').strip().lower()
    personalnummer = _ensure_session_personalnummer()

    if quelle == 'personal':
        if not personalnummer:
            abort(403)
        path_abs = resolve_import_dateipfad(import_folder, filename, 'personal', personalnummer)
        if not path_abs:
            abort(404)
        directory = os.path.dirname(path_abs)
        return send_from_directory(
            directory,
            os.path.basename(path_abs),
            mimetype=mimetypes.guess_type(filename)[0] or 'application/octet-stream',
            max_age=0,
            conditional=True,
        )

    path = os.path.join(import_folder, filename)
    path_abs = os.path.abspath(path)
    if not path_abs.startswith(import_abs + os.sep):
        abort(403)
    if not os.path.isfile(path_abs):
        abort(404)

    mt, _ = mimetypes.guess_type(filename)
    return send_from_directory(
        import_folder,
        filename,
        mimetype=mt or 'application/octet-stream',
        max_age=0,
        conditional=True,
    )


@import_bp.route('/hochladen', methods=['POST'])
def import_hochladen():
    """Datei in den Import-Ordner speichern; mit personal=1 im persönlichen Unterordner (Personalnummer)."""
    if not is_authenticated_user(session):
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401

    file = request.files.get('file')
    name_form = (
        request.args.get('filename')
        or request.args.get('dateiname')
        or request.form.get('filename')
        or request.form.get('dateiname')
        or ''
    ).strip()
    personal_flag = (request.args.get('personal') or request.form.get('personal') or '').strip().lower() in (
        '1', 'true', 'yes', 'on',
    )
    unterordner_pn = None
    if personal_flag:
        unterordner_pn = _ensure_session_personalnummer()
        if not unterordner_pn:
            return jsonify({
                'success': False,
                'message': 'Persönlicher Import-Ordner nicht verfügbar (keine Personalnummer in der Sitzung).',
            }), 400

    success, filename, error_message = speichere_in_import_ordner(
        file,
        dateiname_vorgabe=name_form if name_form else None,
        unterordner_personalnummer=unterordner_pn,
    )
    if not success:
        return jsonify({'success': False, 'message': error_message or 'Speichern fehlgeschlagen'}), 400

    if personal_flag:
        msg = f'Datei "{filename}" wurde in Ihrem persönlichen Import-Ordner gespeichert.'
    else:
        msg = f'Datei "{filename}" wurde im Import-Ordner gespeichert.'
    return jsonify({'success': True, 'message': msg, 'filename': filename, 'personal': bool(personal_flag)})


@import_bp.route('/personal/umbenennen', methods=['POST'])
def import_personal_umbenennen():
    """Datei im persönlichen Import-Unterordner umbenennen."""
    if not is_authenticated_user(session):
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    pn = _ensure_session_personalnummer()
    if not pn:
        return jsonify({'success': False, 'message': 'Keine Personalnummer'}), 400

    data = request.get_json() or {}
    alt = (data.get('alt') or data.get('old') or '').strip()
    neu = (data.get('neu') or data.get('new') or '').strip()
    if not alt or not neu:
        return jsonify({'success': False, 'message': 'Alt- und Neuname erforderlich'}), 400
    if '..' in alt or '/' in alt or '\\' in alt or '..' in neu or '/' in neu or '\\' in neu:
        return jsonify({'success': False, 'message': 'Ungültiger Dateiname'}), 400

    import_folder = current_app.config['IMPORT_FOLDER']
    src = resolve_import_dateipfad(import_folder, alt, 'personal', pn)
    if not src:
        return jsonify({'success': False, 'message': 'Quelldatei nicht gefunden'}), 404

    neu_safe = secure_filename(neu)
    if not neu_safe:
        return jsonify({'success': False, 'message': 'Ungültiger neuer Dateiname'}), 400

    dest_dir = os.path.dirname(src)
    dest = os.path.join(dest_dir, neu_safe)
    if os.path.exists(dest):
        return jsonify({'success': False, 'message': 'Eine Datei mit diesem Namen existiert bereits'}), 400
    try:
        os.rename(src, dest)
    except OSError as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'message': 'Umbenannt', 'filename': neu_safe})


@import_bp.route('/personal/loeschen', methods=['POST'])
def import_personal_loeschen():
    """Datei im persönlichen Import-Unterordner löschen."""
    if not is_authenticated_user(session):
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    pn = _ensure_session_personalnummer()
    if not pn:
        return jsonify({'success': False, 'message': 'Keine Personalnummer'}), 400

    data = request.get_json() or {}
    fn = (data.get('filename') or '').strip()
    if not fn or '..' in fn or '/' in fn or '\\' in fn:
        return jsonify({'success': False, 'message': 'Ungültiger Dateiname'}), 400

    import_folder = current_app.config['IMPORT_FOLDER']
    path_abs = resolve_import_dateipfad(import_folder, fn, 'personal', pn)
    if not path_abs:
        return jsonify({'success': False, 'message': 'Datei nicht gefunden'}), 404
    try:
        os.remove(path_abs)
    except OSError as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'message': 'Datei gelöscht'})


@import_bp.route('/verschieben', methods=['POST'])
def import_datei_verschieben():
    """Verschiebe eine Datei aus dem Import-Ordner zu einem Zielordner und erstelle Datenbankeintrag"""
    if not is_authenticated_user(session):
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401

    mitarbeiter_id = session.get('user_id')
    data = request.get_json()
    original_filename = data.get('filename')
    ziel_ordner = data.get('ziel_ordner')
    bereich_typ = data.get('bereich_typ')
    bereich_id = data.get('bereich_id')
    beschreibung = data.get('beschreibung', '').strip()
    typ_freitext = (data.get('typ') or '').strip()
    import_quelle = (data.get('import_quelle') or data.get('quelle') or '').strip().lower()

    if not original_filename or not ziel_ordner:
        return jsonify({'success': False, 'message': 'Fehlende Parameter'}), 400

    if '..' in original_filename or '/' in original_filename or '\\' in original_filename:
        return jsonify({'success': False, 'message': 'Ungültiger Dateiname'}), 400

    if not _ziel_ordner_erlaubt(ziel_ordner):
        return jsonify({'success': False, 'message': 'Ungültiger Zielordner'}), 400
    ziel_ordner = ziel_ordner.replace('\\', '/').strip().strip('/')

    import_folder = current_app.config['IMPORT_FOLDER']
    upload_base = current_app.config['UPLOAD_BASE_FOLDER']
    personalnummer = _ensure_session_personalnummer()

    if import_quelle == 'personal':
        if not personalnummer:
            return jsonify({'success': False, 'message': 'Persönlicher Import nicht verfügbar'}), 400
        quelle = resolve_import_dateipfad(import_folder, original_filename, 'personal', personalnummer)
        if not quelle:
            return jsonify({'success': False, 'message': f'Datei nicht gefunden: {original_filename}'}), 404
    elif import_quelle == 'import':
        try:
            quelle = resolve_under_base(import_folder, original_filename)
        except PathTraversalError:
            return jsonify({'success': False, 'message': 'Ungültiger Dateipfad'}), 403
        if not os.path.isfile(quelle):
            return jsonify({'success': False, 'message': f'Datei nicht gefunden: {original_filename}'}), 404
    else:
        quelle, _gefunden_in = resolve_import_dateipfad_auto(
            import_folder, original_filename, personalnummer
        )
        if not quelle:
            return jsonify({'success': False, 'message': f'Datei nicht gefunden: {original_filename}'}), 404

    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    safe_filename = timestamp + secure_filename(original_filename)

    try:
        ziel = resolve_under_base(upload_base, f'{ziel_ordner}/{safe_filename}')
    except PathTraversalError:
        return jsonify({'success': False, 'message': 'Ungültiger Zielpfad'}), 403

    os.makedirs(os.path.dirname(ziel), exist_ok=True)

    success, final_filename, error_message = move_file_safe(
        quelle, ziel, create_unique_name=False
    )

    if success:
        if bereich_typ and bereich_id:
            try:
                with get_db_connection() as conn:
                    relativer_pfad = f"{ziel_ordner}/{final_filename}".replace('\\', '/')
                    typ = typ_freitext if typ_freitext else get_datei_typ_aus_dateiname(original_filename)

                    from modules.ersatzteile.services import speichere_datei
                    speichere_datei(
                        bereich_typ=bereich_typ,
                        bereich_id=bereich_id,
                        dateiname=original_filename,
                        dateipfad=relativer_pfad,
                        beschreibung=beschreibung,
                        typ=typ,
                        mitarbeiter_id=mitarbeiter_id,
                        conn=conn
                    )
            except Exception as e:
                return jsonify({
                    'success': True,
                    'message': f'Datei "{final_filename}" verschoben, aber Datenbankeintrag fehlgeschlagen: {str(e)}',
                    'filename': final_filename,
                    'warning': True
                })

        return jsonify({
            'success': True,
            'message': f'Datei "{final_filename}" erfolgreich verschoben',
            'filename': final_filename
        })
    else:
        return jsonify({'success': False, 'message': error_message}), 500
