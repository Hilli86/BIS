"""
Schichtbuch Routes - Themenliste, Details, Bemerkungen
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app, Response, make_response
from datetime import datetime
import os
import sqlite3
from werkzeug.utils import secure_filename
from . import schichtbuch_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_sichtbarkeits_filter_query, row_to_dict
from utils.reports import generate_thema_pdf
from . import services
from . import aufgabenliste_services
from modules.ersatzteile.services import (
    get_dateien_fuer_bereich,
    speichere_datei,
    get_datei_typ_aus_dateiname,
    loesche_datei,
    rueckbuche_lager_fuer_geloeschtes_thema,
)
from utils.file_handling import save_uploaded_file, create_upload_folder, originale_loeschen_aus_formular, loesche_import_kopie_nach_upload
from utils.security import safe_redirect_target


def get_datei_anzahl(thema_id):
    """Ermittelt die Anzahl der Dateien für ein Thema"""
    thema_folder = os.path.join(current_app.config['SCHICHTBUCH_UPLOAD_FOLDER'], str(thema_id))
    if not os.path.exists(thema_folder):
        return 0
    try:
        files = os.listdir(thema_folder)
        return len([f for f in files if os.path.isfile(os.path.join(thema_folder, f))])
    except Exception as e:
        print(f"Fehler beim Ermitteln der Dateianzahl für Thema {thema_id}: {e}")
        return 0


@schichtbuch_bp.route('/themaliste')
@login_required
def themaliste():
    """Themenliste mit Filtern"""
    # Filterparameter aus der URL lesen
    status_filter_list = request.args.getlist('status')
    bereich_filter = request.args.get('bereich')
    gewerk_filter = request.args.get('gewerk')
    q_filter = request.args.get('q')
    nur_offen = request.args.get('nur_offen') == '1'

    items_per_page = 50

    with get_db_connection() as conn:
        # Abteilungsfilter: Nur Themen aus sichtbaren Abteilungen
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        auf_liste_rows = aufgabenliste_services.list_aufgabenlisten_fuer_mitarbeiter(
            mitarbeiter_id, conn, is_admin=is_admin
        )
        aufgabenliste_sichtbar_ids = [r['ID'] for r in auf_liste_rows] or None

        # Query mit Service-Funktion aufbauen
        query, params = services.build_themen_query(
            sichtbare_abteilungen,
            bereich_filter=bereich_filter,
            gewerk_filter=gewerk_filter,
            status_filter_list=status_filter_list,
            q_filter=q_filter,
            limit=items_per_page,
            mitarbeiter_id=mitarbeiter_id,
            aufgabenliste_sichtbar_ids=aufgabenliste_sichtbar_ids,
            exclude_erledigt_status=nur_offen,
        )

        themen = conn.execute(query, params).fetchall()

        # Bemerkungen für die aktuell angezeigten Themen laden
        thema_ids = [t['ID'] for t in themen] if themen else []
        themen_mit_lagerbuchungen = services.thema_ids_mit_lagerbuchungen(thema_ids, conn)
        bemerk_dict = services.get_bemerkungen_fuer_themen(thema_ids, conn)
        zusatz_gewerke_dict = services.get_zusatz_gewerke_fuer_themen(thema_ids, conn)

        # Werte für Dropdowns holen
        status_liste = conn.execute('SELECT ID, Bezeichnung FROM Status WHERE Aktiv = 1 ORDER BY Sortierung ASC').fetchall()
        bereich_liste = conn.execute('SELECT Bezeichnung FROM Bereich WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
        if bereich_filter:
            gewerke_liste = conn.execute('''
                SELECT G.ID, G.Bezeichnung
                FROM Gewerke G
                JOIN Bereich B ON G.BereichID = B.ID
                WHERE B.Bezeichnung = ? AND G.Aktiv = 1
                ORDER BY G.Bezeichnung
            ''', (bereich_filter,)).fetchall()
        else:
            gewerke_liste = conn.execute('SELECT ID, Bezeichnung FROM Gewerke WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
        taetigkeiten_liste = conn.execute('SELECT ID, Bezeichnung FROM Taetigkeit WHERE Aktiv = 1 ORDER BY Sortierung ASC').fetchall()

    perms = session.get('user_berechtigungen', [])
    kann_artikel_rueckbuchen = 'admin' in perms or 'artikel_buchen' in perms

    return render_template(
        'sbThemaListe.html',
        themen=themen,
        themen_mit_lagerbuchungen=themen_mit_lagerbuchungen,
        kann_artikel_rueckbuchen=kann_artikel_rueckbuchen,
        bemerk_dict=bemerk_dict,
        zusatz_gewerke_dict=zusatz_gewerke_dict,
        status_liste=status_liste,
        bereich_liste=bereich_liste,
        taetigkeiten_liste=taetigkeiten_liste,
        status_filter_list=status_filter_list,
        bereich_filter=bereich_filter,
        gewerk_filter=gewerk_filter,
        q_filter=q_filter,
        gewerke_liste=gewerke_liste,
        nur_offen=nur_offen,
    )


@schichtbuch_bp.route('/themaliste/load_more')
@login_required
def themaliste_load_more():
    """AJAX-Route zum Nachladen weiterer Themen"""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    status_filter_list = request.args.getlist('status')
    bereich_filter = request.args.get('bereich')
    gewerk_filter = request.args.get('gewerk')
    q_filter = request.args.get('q')
    nur_offen = request.args.get('nur_offen') == '1'

    with get_db_connection() as conn:
        # Abteilungsfilter auch hier anwenden
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        auf_liste_rows = aufgabenliste_services.list_aufgabenlisten_fuer_mitarbeiter(
            mitarbeiter_id, conn, is_admin=is_admin
        )
        aufgabenliste_sichtbar_ids = [r['ID'] for r in auf_liste_rows] or None

        # Query mit Service-Funktion aufbauen
        query, params = services.build_themen_query(
            sichtbare_abteilungen,
            bereich_filter=bereich_filter,
            gewerk_filter=gewerk_filter,
            status_filter_list=status_filter_list,
            q_filter=q_filter,
            limit=limit,
            offset=offset,
            mitarbeiter_id=mitarbeiter_id,
            aufgabenliste_sichtbar_ids=aufgabenliste_sichtbar_ids,
            exclude_erledigt_status=nur_offen,
        )

        themen = conn.execute(query, params).fetchall()

        # Bemerkungen für diese Themen laden
        thema_ids = [t['ID'] for t in themen] if themen else []
        themen_mit_lagerbuchungen = services.thema_ids_mit_lagerbuchungen(thema_ids, conn)
        bemerk_dict = services.get_bemerkungen_fuer_themen(thema_ids, conn)
        zusatz_gewerke_dict = services.get_zusatz_gewerke_fuer_themen(thema_ids, conn)

    # Als JSON zurückgeben
    themen_out = []
    for t in themen:
        d = dict(t)
        d['HatVerbuchteErsatzteile'] = 1 if t['ID'] in themen_mit_lagerbuchungen else 0
        d['ZusatzGewerke'] = zusatz_gewerke_dict.get(t['ID'], [])
        themen_out.append(d)

    return jsonify({
        'themen': themen_out,
        'bemerk_dict': {k: [dict(b) for b in v] for k, v in bemerk_dict.items()}
    })


@schichtbuch_bp.route('/api/gewerke')
@login_required
def api_gewerke():
    """API: Gewerke nach Bereich"""
    bereich = request.args.get('bereich')
    with get_db_connection() as conn:
        if bereich:
            rows = conn.execute('''
                SELECT G.ID, G.Bezeichnung
                FROM Gewerke G
                JOIN Bereich B ON G.BereichID = B.ID
                WHERE B.Bezeichnung = ? AND G.Aktiv = 1
                ORDER BY G.Bezeichnung
            ''', (bereich,)).fetchall()
        else:
            rows = conn.execute('SELECT ID, Bezeichnung FROM Gewerke WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
    return jsonify({'gewerke': [dict(r) for r in rows]})


@schichtbuch_bp.route('/themaliste/add', methods=['POST'])
@login_required
def add_bemerkung():
    """Bemerkung hinzufügen"""
    thema_id = request.form.get('thema_id')
    bemerkung_text = request.form.get('bemerkung')
    status_id = request.form.get('status_id')
    taetigkeit_id = request.form.get('taetigkeit_id')
    next_url = safe_redirect_target(request.form.get('next'), url_for('schichtbuch.themaliste'))


    if not thema_id or not bemerkung_text:
        flash("Fehler: Thema oder Bemerkung fehlt.", "danger")
        return redirect(next_url)

    mitarbeiter_id = session.get('user_id')
    datum = None  # Initialisierung für späteren Gebrauch

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Neue Bemerkung speichern
        cursor.execute("""
            INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Bemerkung, Datum, TaetigkeitID)
            VALUES (?, ?, ?, datetime('now', 'localtime'), ?)
            """, (thema_id, mitarbeiter_id, bemerkung_text, taetigkeit_id))
        
        bemerkung_id = cursor.lastrowid
        
        # Datum der neuen Bemerkung abrufen
        datum_row = conn.execute("SELECT Datum FROM SchichtbuchBemerkungen WHERE ID = ?", (bemerkung_id,)).fetchone()
        if datum_row:
            datum = datum_row[0]
        
        # Benachrichtigungen für andere Mitarbeiter erstellen
        from utils import erstelle_benachrichtigung_fuer_bemerkung
        import logging
        logger = logging.getLogger(__name__)
        try:
            erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id, conn)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen von Benachrichtigungen für Bemerkung: ThemaID={thema_id}, BemerkungID={bemerkung_id}, Fehler={str(e)}", exc_info=True)

        neuer_status = None
        neue_farbe = None

        # Falls Status geändert wird
        if status_id and status_id.isdigit():
            cursor.execute("UPDATE SchichtbuchThema SET StatusID = ? WHERE ID = ?", (status_id, thema_id))
            status_row = conn.execute("SELECT Bezeichnung, Farbe FROM Status WHERE ID = ?", (status_id,)).fetchone()
            status_dict = row_to_dict(status_row)
            if status_dict:
                neuer_status = status_dict["Bezeichnung"]
                neue_farbe = status_dict["Farbe"]

        # Mitarbeitername holen
        user_row = conn.execute("SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?", (mitarbeiter_id,)).fetchone()
        user = row_to_dict(user_row)

        # Zwei neueste Bemerkungen (für Themenliste: vorherige = jetzt „weitere“)
        latest_rows = conn.execute(
            """
            SELECT b.Datum, b.Bemerkung, m.Vorname, m.Nachname, t.Bezeichnung AS Taetigkeit
            FROM SchichtbuchBemerkungen b
            JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
            LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
            WHERE b.ThemaID = ? AND b.Gelöscht = 0
            ORDER BY b.Datum DESC, b.ID DESC
            LIMIT 2
            """,
            (thema_id,),
        ).fetchall()

        conn.commit()

    vorherige_payload = None
    if len(latest_rows) >= 2:
        r = row_to_dict(latest_rows[1])
        vorherige_payload = {
            "datum": str(r["Datum"]) if r.get("Datum") is not None else "",
            "bemerkung": r.get("Bemerkung") or "",
            "vorname": r.get("Vorname") or "",
            "nachname": r.get("Nachname") or "",
            "taetigkeit": r.get("Taetigkeit") or "",
        }

    # Wenn per AJAX (fetch)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        taetigkeit_name = None
        if taetigkeit_id:
            with get_db_connection() as conn:
                ta_row = conn.execute("SELECT Bezeichnung FROM Taetigkeit WHERE ID = ?", (taetigkeit_id,)).fetchone()
                ta_dict = row_to_dict(ta_row)
                if ta_dict:
                    taetigkeit_name = ta_dict["Bezeichnung"]

        return jsonify({
            "success": True,
            "thema_id": thema_id,
            "datum": datum,
            "bemerkung": bemerkung_text,
            "vorname": user["Vorname"],
            "nachname": user["Nachname"],
            "taetigkeit": taetigkeit_name,
            "neuer_status": neuer_status,
            "neue_farbe": neue_farbe,
            "vorherige": vorherige_payload,
        })
    else: 
        flash("Bemerkung erfolgreich hinzugefügt.", "success")
        return redirect(next_url)


@schichtbuch_bp.route('/themaneu', methods=['GET', 'POST'])
@login_required
def themaneu():
    """Neues Thema + erste Bemerkung"""
    mitarbeiter_id = session.get('user_id')
    
    # POST = neues Thema speichern
    if request.method == 'POST':
        gewerk_id = request.form['gewerk']
        taetigkeit_id = request.form['taetigkeit']
        status_id = request.form['status']
        bemerkung = request.form['bemerkung']
        sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')
        aufgabenliste_ids = request.form.getlist('aufgabenliste_ids')
        vorgang_datum = (request.form.get('vorgang_datum') or '').strip() or None

        try:
            with get_db_connection() as conn:
                # Thema erstellen über Service
                is_admin = 'admin' in session.get('user_berechtigungen', [])
                thema_id, thema_dict = services.create_thema(
                    gewerk_id, status_id, mitarbeiter_id, taetigkeit_id, bemerkung,
                    sichtbare_abteilungen, conn, vorgang_datum=vorgang_datum,
                    aufgabenliste_ids=aufgabenliste_ids, is_admin=is_admin,
                )

                # Ersatzteile verarbeiten
                ersatzteil_ids = request.form.getlist('ersatzteil_id[]')
                ersatzteil_mengen = request.form.getlist('ersatzteil_menge[]')
                ersatzteil_bemerkungen = request.form.getlist('ersatzteil_bemerkung[]')
                ersatzteil_kostenstellen = request.form.getlist('ersatzteil_kostenstelle[]')
                services.process_ersatzteile_fuer_thema(
                    thema_id, ersatzteil_ids, ersatzteil_mengen, ersatzteil_bemerkungen,
                    mitarbeiter_id, conn, is_admin=is_admin, ersatzteil_kostenstellen=ersatzteil_kostenstellen
                )

                zusatz_gewerke_ids = request.form.getlist('zusatz_gewerke')
                if zusatz_gewerke_ids:
                    services.update_thema_zusatz_gewerke(thema_id, zusatz_gewerke_ids, conn)

                conn.commit()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        # Für AJAX → JSON zurückgeben
        return jsonify(thema_dict)

    # GET = Seite anzeigen
    with get_db_connection() as conn:
        form_data = services.get_thema_erstellung_form_data(mitarbeiter_id, conn)

    return render_template(
        'sbThemaNeu.html',
        gewerke=form_data['gewerke'],
        taetigkeiten=form_data['taetigkeiten'],
        status=form_data['status'],
        bereiche=form_data['bereiche'],
        auswaehlbare_abteilungen=form_data['auswaehlbare_abteilungen'],
        primaer_abteilung_id=form_data['primaer_abteilung_id'],
        kostenstellen=form_data['kostenstellen'],
        aufgabenlisten=form_data.get('aufgabenlisten') or [],
    )


@schichtbuch_bp.route('/themaneu/aktuelle_themen')
@login_required
def aktuelle_themen():
    """AJAX-Route: Letzte Themen des angemeldeten Mitarbeiters"""
    user_id = session.get('user_id')

    with get_db_connection() as conn:
        daten = conn.execute('''
            SELECT 
                t.ID, 
                b.Bezeichnung AS Bereich,
                g.Bezeichnung AS Gewerk,
                s.Bezeichnung AS Status,
                MAX(bm.Datum) AS LetzteBemerkungDatum,
                (SELECT bm2.Bemerkung FROM SchichtbuchBemerkungen bm2
                 WHERE bm2.ThemaID = t.ID AND bm2.Gelöscht = 0
                 ORDER BY bm2.Datum DESC LIMIT 1) AS LetzteBemerkung
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Status s ON t.StatusID = s.ID
            JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID
            WHERE bm.MitarbeiterID = ? AND t.Gelöscht = 0
            GROUP BY t.ID
            ORDER BY t.ID DESC
            LIMIT 10
        ''', (user_id,)).fetchall()

    return jsonify({"themen": [dict(row) for row in daten]})


@schichtbuch_bp.route('/themaneu/themen_nach_gewerk')
@login_required
def themen_nach_gewerk():
    """API: Offene Themen zu einem Gewerk (Status != Erledigt)"""
    gewerk_id = request.args.get('gewerk_id', type=int)
    if not gewerk_id:
        return jsonify({'themen': []})

    if session.get('is_guest'):
        return jsonify({'themen': []})

    mitarbeiter_id = session.get('user_id')
    if not mitarbeiter_id:
        return jsonify({'error': 'Nicht angemeldet'}), 401

    with get_db_connection() as conn:
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)

        base_query = '''
            SELECT 
                t.ID,
                b.Bezeichnung AS Bereich,
                g.Bezeichnung AS Gewerk,
                (SELECT m.Vorname || ' ' || m.Nachname FROM SchichtbuchBemerkungen bm2
                 JOIN Mitarbeiter m ON bm2.MitarbeiterID = m.ID
                 WHERE bm2.ThemaID = t.ID AND bm2.Gelöscht = 0
                 ORDER BY bm2.Datum DESC LIMIT 1) AS Mitarbeiter,
                (SELECT bm2.Bemerkung FROM SchichtbuchBemerkungen bm2
                 WHERE bm2.ThemaID = t.ID AND bm2.Gelöscht = 0
                 ORDER BY bm2.Datum DESC LIMIT 1) AS LetzteBemerkung
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            WHERE t.GewerkID = ? AND t.Gelöscht = 0 AND t.StatusID != 1
        '''
        params = [gewerk_id]

        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            base_query += f''' AND (
                EXISTS (
                    SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                    WHERE sv.ThemaID = t.ID AND sv.AbteilungID IN ({placeholders})
                )
                OR EXISTS (
                    SELECT 1 FROM SchichtbuchBemerkungen b_first
                    WHERE b_first.ThemaID = t.ID AND b_first.Gelöscht = 0
                    AND b_first.MitarbeiterID = ?
                    AND b_first.Datum = (
                        SELECT MIN(b2.Datum) FROM SchichtbuchBemerkungen b2
                        WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0
                    )
                )
            )'''
            params.extend(sichtbare_abteilungen)
            params.append(mitarbeiter_id)
        else:
            base_query += ''' AND EXISTS (
                SELECT 1 FROM SchichtbuchBemerkungen b_first
                WHERE b_first.ThemaID = t.ID AND b_first.Gelöscht = 0
                AND b_first.MitarbeiterID = ?
                AND b_first.Datum = (
                    SELECT MIN(b2.Datum) FROM SchichtbuchBemerkungen b2
                    WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0
                )
            )'''
            params.append(mitarbeiter_id)

        base_query += ''' ORDER BY (
            SELECT MAX(bm2.Datum) FROM SchichtbuchBemerkungen bm2
            WHERE bm2.ThemaID = t.ID AND bm2.Gelöscht = 0
        ) DESC LIMIT 20'''

        rows = conn.execute(base_query, params).fetchall()

        themen = []
        for row in rows:
            thema = dict(row)
            if thema.get('LetzteBemerkung') and len(thema['LetzteBemerkung']) > 80:
                thema['LetzteBemerkung'] = thema['LetzteBemerkung'][:80] + '...'
            thema['Mitarbeiter'] = thema.get('Mitarbeiter') or ''
            themen.append(thema)

    return jsonify({'themen': themen})


@schichtbuch_bp.route('/thema/<int:thema_id>', methods=['GET', 'POST'])
@login_required
def thema_detail(thema_id):
    """Thema-Detail-Seite"""
    mitarbeiter_id = session.get('user_id')
    
    # Berechtigungsprüfung: Darf der Benutzer dieses Thema sehen?
    with get_db_connection() as conn:
        if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
            flash('Sie haben keine Berechtigung, dieses Thema zu sehen.', 'danger')
            return redirect(url_for('schichtbuch.themaliste'))
    
    if request.method == 'POST':
        if not mitarbeiter_id:
            flash('Bitte zuerst anmelden.', 'warning')
            return redirect(url_for('auth.login'))

        bemerkung = request.form['bemerkung']
        neuer_status = request.form.get('status')
        taetigkeit_id = request.form.get("taetigkeit_id")

        with get_db_connection() as conn:
            # Bemerkung speichern
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung)
                VALUES (?, ?, datetime('now', 'localtime'), ?, ?)
            ''', (thema_id, mitarbeiter_id, taetigkeit_id, bemerkung))
            
            bemerkung_id = cursor.lastrowid
            
            # Benachrichtigungen für andere Mitarbeiter erstellen
            from utils import erstelle_benachrichtigung_fuer_bemerkung
            import logging
            logger = logging.getLogger(__name__)
            try:
                erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id, conn)
            except Exception as e:
                logger.error(f"Fehler beim Erstellen von Benachrichtigungen für Bemerkung (API): ThemaID={thema_id}, BemerkungID={bemerkung_id}, Fehler={str(e)}", exc_info=True)

            # Status ggf. ändern
            if neuer_status and neuer_status != "":
                conn.execute('UPDATE SchichtbuchThema SET StatusID = ? WHERE ID = ?', (neuer_status, thema_id))

            conn.commit()

    # Thema-Daten über Service laden
    with get_db_connection() as conn:
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        detail_data = services.get_thema_detail_data(thema_id, mitarbeiter_id, conn, is_admin=is_admin)
        perms_for_gewerk = session.get('user_berechtigungen', [])
        darf_thema_gewerk_aendern = is_admin or 'darf_Thema_Gewerk_ändern' in perms_for_gewerk
        darf_thema_bearbeiten = is_admin or 'darf_Thema_bearbeiten' in perms_for_gewerk
        bereiche_gewerk_edit = None
        gewerke_gewerk_edit = None
        if darf_thema_gewerk_aendern:
            bereiche_gewerk_edit, gewerke_gewerk_edit = services.get_bereiche_gewerke_fuer_gewerk_select(conn)

    previous_page = safe_redirect_target(request.args.get('next'), url_for('schichtbuch.themaliste'))
    
    # Dateianzahl ermitteln
    datei_anzahl = get_datei_anzahl(thema_id)

    perms = session.get('user_berechtigungen', [])
    kann_artikel_rueckbuchen = 'admin' in perms or 'artikel_buchen' in perms
    thema_hat_lagerbuchungen = bool(detail_data['thema_lagerbuchungen'])

    return render_template(
        'sbThemaDetail.html',
        thema=detail_data['thema'],
        bemerkungen=detail_data['bemerkungen'],
        mitarbeiter=detail_data['mitarbeiter'],
        status_liste=detail_data['status_liste'],
        taetigkeiten=detail_data['taetigkeiten'],
        sichtbarkeiten=detail_data['sichtbarkeiten'],
        zusatz_gewerke=detail_data['zusatz_gewerke'],
        previous_page=previous_page,
        datei_anzahl=datei_anzahl,
        ersatzteil_verknuepfungen=detail_data['thema_lagerbuchungen'],
        verfuegbare_ersatzteile=detail_data['verfuegbare_ersatzteile'],
        kostenstellen=detail_data['kostenstellen'],
        is_admin=is_admin,
        thema_hat_lagerbuchungen=thema_hat_lagerbuchungen,
        kann_artikel_rueckbuchen=kann_artikel_rueckbuchen,
        darf_thema_gewerk_aendern=darf_thema_gewerk_aendern,
        darf_thema_bearbeiten=darf_thema_bearbeiten,
        bereiche_gewerk_edit=bereiche_gewerk_edit,
        gewerke_gewerk_edit=gewerke_gewerk_edit,
    )


@schichtbuch_bp.route('/thema/<int:thema_id>/gewerk', methods=['POST'])
@login_required
def thema_gewerk_aendern(thema_id):
    """Gewerk eines Themas ändern (Berechtigung darf_Thema_Gewerk_ändern oder Admin)."""
    mitarbeiter_id = session.get('user_id')
    perms = session.get('user_berechtigungen', [])
    is_admin = 'admin' in perms
    if not is_admin and 'darf_Thema_Gewerk_ändern' not in perms:
        flash('Sie haben keine Berechtigung, das Gewerk zu ändern.', 'danger')
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))

    gewerk_id_raw = (request.form.get('gewerk_id') or '').strip()
    if not gewerk_id_raw:
        flash('Bitte ein Gewerk auswählen.', 'warning')
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
    try:
        gewerk_id = int(gewerk_id_raw)
    except ValueError:
        flash('Ungültige Gewerk-Auswahl.', 'warning')
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))

    next_url = safe_redirect_target(request.form.get('next'), url_for('schichtbuch.thema_detail', thema_id=thema_id))

    with get_db_connection() as conn:
        if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
            flash('Sie haben keine Berechtigung für dieses Thema.', 'danger')
            return redirect(url_for('schichtbuch.themaliste'))

        thema_row = conn.execute(
            'SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0',
            (thema_id,),
        ).fetchone()
        if not thema_row:
            flash('Thema wurde nicht gefunden.', 'warning')
            return redirect(url_for('schichtbuch.themaliste'))

        g_row = conn.execute(
            '''
            SELECT G.ID FROM Gewerke G
            JOIN Bereich B ON G.BereichID = B.ID
            WHERE G.ID = ? AND G.Aktiv = 1 AND B.Aktiv = 1
            ''',
            (gewerk_id,),
        ).fetchone()
        if not g_row:
            flash('Das gewählte Gewerk ist ungültig oder nicht aktiv.', 'warning')
            return redirect(next_url)

        conn.execute(
            'UPDATE SchichtbuchThema SET GewerkID = ? WHERE ID = ? AND Gelöscht = 0',
            (gewerk_id, thema_id),
        )
        conn.commit()

    flash('Gewerk wurde gespeichert.', 'success')
    return redirect(next_url)


@schichtbuch_bp.route('/thema/<int:thema_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def thema_bearbeiten(thema_id):
    """Kombiniertes Bearbeiten von Hauptgewerk, Zusatz-Gewerken und Sichtbarkeit."""
    mitarbeiter_id = session.get('user_id')
    perms = session.get('user_berechtigungen', [])
    is_admin = 'admin' in perms
    if not is_admin and 'darf_Thema_bearbeiten' not in perms:
        flash('Sie haben keine Berechtigung, Themen zu bearbeiten.', 'danger')
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))

    with get_db_connection() as conn:
        if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
            flash('Sie haben keine Berechtigung für dieses Thema.', 'danger')
            return redirect(url_for('schichtbuch.themaliste'))

        thema_row = conn.execute(
            'SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0',
            (thema_id,),
        ).fetchone()
        if not thema_row:
            flash('Thema wurde nicht gefunden.', 'warning')
            return redirect(url_for('schichtbuch.themaliste'))

        if request.method == 'POST':
            gewerk_id_raw = (request.form.get('gewerk_id') or '').strip()
            zusatz_gewerke_raw = request.form.getlist('zusatz_gewerke')
            sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')

            if not gewerk_id_raw:
                flash('Bitte ein Hauptgewerk auswählen.', 'warning')
                return redirect(url_for('schichtbuch.thema_bearbeiten', thema_id=thema_id))
            try:
                gewerk_id = int(gewerk_id_raw)
            except ValueError:
                flash('Ungültige Gewerk-Auswahl.', 'warning')
                return redirect(url_for('schichtbuch.thema_bearbeiten', thema_id=thema_id))

            g_row = conn.execute(
                '''SELECT G.ID FROM Gewerke G
                   JOIN Bereich B ON G.BereichID = B.ID
                   WHERE G.ID = ? AND G.Aktiv = 1 AND B.Aktiv = 1''',
                (gewerk_id,),
            ).fetchone()
            if not g_row:
                flash('Das gewählte Gewerk ist ungültig oder nicht aktiv.', 'warning')
                return redirect(url_for('schichtbuch.thema_bearbeiten', thema_id=thema_id))

            if not sichtbare_abteilungen:
                flash('Mindestens eine Abteilung muss sichtbar sein.', 'warning')
                return redirect(url_for('schichtbuch.thema_bearbeiten', thema_id=thema_id))

            try:
                conn.execute(
                    'UPDATE SchichtbuchThema SET GewerkID = ? WHERE ID = ? AND Gelöscht = 0',
                    (gewerk_id, thema_id),
                )
                services.update_thema_zusatz_gewerke(thema_id, zusatz_gewerke_raw, conn)

                conn.execute(
                    'DELETE FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?',
                    (thema_id,),
                )
                for abt_id_raw in sichtbare_abteilungen:
                    try:
                        abt_id = int(abt_id_raw)
                    except (TypeError, ValueError):
                        continue
                    try:
                        conn.execute(
                            '''INSERT OR IGNORE INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
                               VALUES (?, ?)''',
                            (thema_id, abt_id),
                        )
                    except sqlite3.IntegrityError:
                        pass

                conn.commit()
            except Exception as e:
                conn.rollback()
                flash(f'Fehler beim Speichern: {e}', 'danger')
                return redirect(url_for('schichtbuch.thema_bearbeiten', thema_id=thema_id))

            flash('Thema wurde gespeichert.', 'success')
            return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))

        data = services.get_thema_bearbeiten_data(thema_id, mitarbeiter_id, conn)

    return render_template(
        'sbThemaBearbeiten.html',
        thema=data['thema'],
        bereiche=data['bereiche'],
        gewerke=data['gewerke'],
        zusatz_gewerke_ids=data['zusatz_gewerke_ids'],
        auswaehlbare_abteilungen=data['auswaehlbare_abteilungen'],
        aktuelle_sichtbarkeiten_ids=data['aktuelle_sichtbarkeiten_ids'],
        primaer_abteilung_id=data['primaer_abteilung_id'],
    )


@schichtbuch_bp.route('/edit_bemerkung/<int:bemerkung_id>', methods=['POST'])
@login_required
def edit_bemerkung(bemerkung_id):
    """Bemerkung bearbeiten (nur eigener Nutzer)"""
    user_id = session.get('user_id')
    neuer_text = request.form.get('bemerkung')
    neue_taetigkeit_id = request.form.get('taetigkeit_id')

    if not neuer_text:
        return jsonify({"success": False, "error": "Bemerkung fehlt."}), 400

    with get_db_connection() as conn:
        row = conn.execute('SELECT MitarbeiterID FROM SchichtbuchBemerkungen WHERE ID = ? AND Gelöscht = 0', (bemerkung_id,)).fetchone()
        if not row:
            return jsonify({"success": False, "error": "Bemerkung nicht gefunden."}), 404
        if row['MitarbeiterID'] != user_id:
            return jsonify({"success": False, "error": "Keine Berechtigung."}), 403

        # Update durchführen
        if neue_taetigkeit_id and neue_taetigkeit_id != "":
            conn.execute('UPDATE SchichtbuchBemerkungen SET Bemerkung = ?, TaetigkeitID = ? WHERE ID = ?', (neuer_text, neue_taetigkeit_id, bemerkung_id))
        else:
            conn.execute('UPDATE SchichtbuchBemerkungen SET Bemerkung = ?, TaetigkeitID = NULL WHERE ID = ?', (neuer_text, bemerkung_id))
        conn.commit()

        ta_row = None
        if neue_taetigkeit_id and neue_taetigkeit_id != "":
            ta_row = conn.execute('SELECT Bezeichnung FROM Taetigkeit WHERE ID = ?', (neue_taetigkeit_id,)).fetchone()

    return jsonify({
        "success": True,
        "bemerkung_id": bemerkung_id,
        "bemerkung": neuer_text,
        "taetigkeit_id": int(neue_taetigkeit_id) if (neue_taetigkeit_id and neue_taetigkeit_id != "") else None,
        "taetigkeit": (ta_row['Bezeichnung'] if ta_row else None)
    })


@schichtbuch_bp.route('/delete_thema/<int:thema_id>', methods=['POST'])
@login_required
def delete_thema(thema_id):
    """Thema löschen (Soft-Delete), optional Lager-Gegenbuchungen."""
    mitarbeiter_id = session.get('user_id')
    perms = session.get('user_berechtigungen', [])
    kann_rueckbuchen = 'admin' in perms or 'artikel_buchen' in perms
    rueckbuchen_gewuenscht = request.form.get('rueckbuchen_ersatzteile') == '1'

    next_url = safe_redirect_target(request.referrer, url_for('schichtbuch.themaliste'))
    rueckbuchungs_hinweis = None

    try:
        with get_db_connection() as conn:
            if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
                flash('Sie haben keine Berechtigung, dieses Thema zu löschen.', 'danger')
                return redirect(next_url)

            thema_row = conn.execute(
                'SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0',
                (thema_id,),
            ).fetchone()
            if not thema_row:
                flash('Thema wurde nicht gefunden oder ist bereits gelöscht.', 'warning')
                return redirect(next_url)

            if rueckbuchen_gewuenscht:
                if not kann_rueckbuchen:
                    flash(
                        'Keine Berechtigung zum Zurückbuchen von Artikeln. Thema wird ohne Lagerkorrektur gelöscht.',
                        'warning',
                    )
                else:
                    ok_lb, msg_lb = rueckbuche_lager_fuer_geloeschtes_thema(
                        thema_id, mitarbeiter_id, conn
                    )
                    if not ok_lb:
                        flash(msg_lb, 'danger')
                        return redirect(next_url)
                    rueckbuchungs_hinweis = msg_lb

            conn.execute('UPDATE SchichtbuchThema SET Gelöscht = 1 WHERE ID = ?', (thema_id,))
            conn.commit()
    except Exception as e:
        flash(f'Fehler beim Löschen: {e}', 'danger')
        return redirect(next_url)

    if rueckbuchungs_hinweis:
        flash(f'{rueckbuchungs_hinweis} Thema #{thema_id} wurde gelöscht.', 'success')
    else:
        flash(f'Thema #{thema_id} wurde gelöscht.', 'info')
    return redirect(next_url)


@schichtbuch_bp.route('/delete_bemerkung/<int:bemerkung_id>', methods=['POST'])
@login_required
def delete_bemerkung(bemerkung_id):
    """Bemerkung löschen (Soft-Delete)"""
    with get_db_connection() as conn:
        conn.execute('UPDATE SchichtbuchBemerkungen SET Gelöscht = 1 WHERE ID = ?', (bemerkung_id,))
        conn.commit()
    flash(f'Bemerkung #{bemerkung_id} wurde gelöscht.', 'info')
    next_url = safe_redirect_target(request.referrer, url_for('schichtbuch.themaliste'))
    return redirect(next_url)


@schichtbuch_bp.route('/thema/<int:thema_id>/sichtbarkeit', methods=['GET'])
@login_required
def get_thema_sichtbarkeit(thema_id):
    """AJAX: Sichtbarkeiten eines Themas laden"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        sichtbarkeit_data = services.get_thema_sichtbarkeit_data(thema_id, mitarbeiter_id, conn)
        return jsonify(sichtbarkeit_data)


@schichtbuch_bp.route('/thema/<int:thema_id>/sichtbarkeit', methods=['POST'])
@login_required
def update_thema_sichtbarkeit(thema_id):
    """AJAX: Sichtbarkeiten eines Themas aktualisieren"""
    sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')
    
    with get_db_connection() as conn:
        success, message = services.update_thema_sichtbarkeiten(thema_id, sichtbare_abteilungen, conn)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message}), 400


# ========== Aufgabenlisten ==========


@schichtbuch_bp.route('/aufgabenlisten')
@login_required
def aufgabenlisten_liste():
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    with get_db_connection() as conn:
        listen = aufgabenliste_services.list_aufgabenlisten_fuer_mitarbeiter(
            mitarbeiter_id, conn, is_admin=is_admin
        )
    return render_template('sbAufgabenlisteUebersicht.html', listen=listen)


@schichtbuch_bp.route('/aufgabenlisten/neu', methods=['GET', 'POST'])
@login_required
def aufgabenliste_neu():
    mitarbeiter_id = session.get('user_id')
    from utils import get_abteilungsbaum_fuer_sichtbarkeit

    if request.method == 'POST':
        bezeichnung = (request.form.get('bezeichnung') or '').strip()
        beschreibung = (request.form.get('beschreibung') or '').strip()
        abt = request.form.getlist('sichtbare_abteilungen')
        ma_ids = request.form.getlist('sichtbare_mitarbeiter')
        if not bezeichnung:
            flash('Bitte eine Bezeichnung angeben.', 'danger')
        else:
            with get_db_connection() as conn:
                lid = aufgabenliste_services.create_aufgabenliste(
                    bezeichnung, beschreibung, mitarbeiter_id, abt, ma_ids, conn
                )
                conn.commit()
            flash('Aufgabenliste angelegt.', 'success')
            return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=lid))

    with get_db_connection() as conn:
        auswaehlbare = get_abteilungsbaum_fuer_sichtbarkeit(mitarbeiter_id, conn)
        mitarbeiter_options = aufgabenliste_services.alle_aktiven_mitarbeiter_options(conn)

    return render_template(
        'sbAufgabenlisteForm.html',
        liste=None,
        auswaehlbare_abteilungen=auswaehlbare,
        mitarbeiter_options=mitarbeiter_options,
        gewaehlte_abteilungen=set(),
        gewaehlte_mitarbeiter=set(),
    )


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>')
@login_required
def aufgabenliste_detail(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    status_filter_list = request.args.getlist('status')
    bereich_filter = request.args.get('bereich')
    gewerk_filter = request.args.get('gewerk')

    with get_db_connection() as conn:
        if not aufgabenliste_services.mitarbeiter_sieht_aufgabenliste(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        ):
            flash('Keine Berechtigung für diese Aufgabenliste.', 'danger')
            return redirect(url_for('schichtbuch.aufgabenlisten_liste'))
        detail = aufgabenliste_services.get_aufgabenliste_detail(liste_id, conn)
        themen = aufgabenliste_services.list_themen_fuer_aufgabenliste(
            liste_id,
            conn,
            bereich_filter=bereich_filter or None,
            gewerk_filter=gewerk_filter or None,
            status_filter_list=status_filter_list or None,
        )
        status_liste = conn.execute(
            'SELECT ID, Bezeichnung FROM Status WHERE Aktiv = 1 ORDER BY Sortierung ASC'
        ).fetchall()
        bereich_liste = conn.execute(
            'SELECT Bezeichnung FROM Bereich WHERE Aktiv = 1 ORDER BY Bezeichnung'
        ).fetchall()
        if bereich_filter:
            gewerke_liste = conn.execute(
                '''
                SELECT G.Bezeichnung FROM Gewerke G
                JOIN Bereich B ON G.BereichID = B.ID
                WHERE B.Bezeichnung = ? AND G.Aktiv = 1 ORDER BY G.Bezeichnung
                ''',
                (bereich_filter,),
            ).fetchall()
        else:
            gewerke_liste = conn.execute(
                'SELECT Bezeichnung FROM Gewerke WHERE Aktiv = 1 ORDER BY Bezeichnung'
            ).fetchall()

        darf_stamm = aufgabenliste_services.darf_aufgabenliste_stammdaten_bearbeiten(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        )
        darf_themen = aufgabenliste_services.darf_themen_zu_aufgabenliste_zuordnen(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        )

    return render_template(
        'sbAufgabenlisteDetail.html',
        detail=detail,
        themen=themen,
        status_liste=status_liste,
        bereich_liste=bereich_liste,
        gewerke_liste=gewerke_liste,
        status_filter_list=status_filter_list,
        bereich_filter=bereich_filter,
        gewerk_filter=gewerk_filter,
        darf_stamm=darf_stamm,
        darf_themen=darf_themen,
    )


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def aufgabenliste_bearbeiten(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    from utils import get_abteilungsbaum_fuer_sichtbarkeit

    with get_db_connection() as conn:
        if not aufgabenliste_services.darf_aufgabenliste_stammdaten_bearbeiten(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        ):
            flash('Keine Berechtigung.', 'danger')
            return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))

        if request.method == 'POST':
            bezeichnung = (request.form.get('bezeichnung') or '').strip()
            beschreibung = (request.form.get('beschreibung') or '').strip()
            abt = request.form.getlist('sichtbare_abteilungen')
            ma_ids = request.form.getlist('sichtbare_mitarbeiter')
            if not bezeichnung:
                flash('Bitte eine Bezeichnung angeben.', 'danger')
            else:
                aufgabenliste_services.update_aufgabenliste_stammdaten(
                    liste_id, bezeichnung, beschreibung, abt, ma_ids, conn
                )
                conn.commit()
                flash('Gespeichert.', 'success')
                return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))

        detail = aufgabenliste_services.get_aufgabenliste_detail(liste_id, conn)
        if not detail:
            flash('Liste nicht gefunden.', 'danger')
            return redirect(url_for('schichtbuch.aufgabenlisten_liste'))
        auswaehlbare = get_abteilungsbaum_fuer_sichtbarkeit(mitarbeiter_id, conn)
        mitarbeiter_options = aufgabenliste_services.alle_aktiven_mitarbeiter_options(conn)
        gew_abt = {r['ID'] for r in detail['abteilungen']}
        gew_ma = {r['ID'] for r in detail['mitarbeiter']}

    return render_template(
        'sbAufgabenlisteForm.html',
        liste=detail['liste'],
        auswaehlbare_abteilungen=auswaehlbare,
        mitarbeiter_options=mitarbeiter_options,
        gewaehlte_abteilungen=gew_abt,
        gewaehlte_mitarbeiter=gew_ma,
    )


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/duplizieren', methods=['POST'])
@login_required
def aufgabenliste_duplizieren(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    mit_themen = request.form.get('mit_themen') == '1'

    with get_db_connection() as conn:
        if not aufgabenliste_services.mitarbeiter_sieht_aufgabenliste(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        ):
            flash('Keine Berechtigung.', 'danger')
            return redirect(url_for('schichtbuch.aufgabenlisten_liste'))
        if not aufgabenliste_services.darf_aufgabenliste_stammdaten_bearbeiten(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        ):
            flash('Nur Ersteller oder Admin dürfen duplizieren.', 'danger')
            return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))
        new_id = aufgabenliste_services.duplicate_aufgabenliste(
            liste_id, mitarbeiter_id, conn, mit_themen=mit_themen
        )
        conn.commit()
    if new_id:
        flash('Kopie angelegt.', 'success')
        return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=new_id))
    flash('Duplizieren fehlgeschlagen.', 'danger')
    return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/archivieren', methods=['POST'])
@login_required
def aufgabenliste_archivieren(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])

    with get_db_connection() as conn:
        if not aufgabenliste_services.mitarbeiter_sieht_aufgabenliste(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        ):
            flash('Keine Berechtigung.', 'danger')
            return redirect(url_for('schichtbuch.aufgabenlisten_liste'))
        ok, msg = aufgabenliste_services.archiviere_aufgabenliste(
            liste_id, mitarbeiter_id, conn, is_admin=is_admin
        )
        if ok:
            conn.commit()
            flash(msg, 'success')
            return redirect(url_for('schichtbuch.aufgabenlisten_liste'))
        conn.rollback()
    flash(msg, 'danger')
    return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/sortierung', methods=['POST'])
@login_required
def aufgabenliste_sortierung(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    order = request.form.getlist('thema_reihenfolge[]')

    with get_db_connection() as conn:
        ok, msg = aufgabenliste_services.reorder_aufgabenliste_themen(
            liste_id, order, mitarbeiter_id, conn, is_admin=is_admin
        )
        conn.commit()
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 403


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/thema/<int:thema_id>/entfernen', methods=['POST'])
@login_required
def aufgabenliste_thema_entfernen(liste_id, thema_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])

    with get_db_connection() as conn:
        ok, msg = aufgabenliste_services.remove_thema_from_aufgabenliste(
            liste_id, thema_id, mitarbeiter_id, conn, is_admin=is_admin
        )
        conn.commit()
    if ok:
        flash(msg, 'info')
    else:
        flash(msg, 'danger')
    return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/api/offene-themen', methods=['GET'])
@login_required
def aufgabenliste_api_offene_themen(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    with get_db_connection() as conn:
        if not aufgabenliste_services.mitarbeiter_sieht_aufgabenliste(
            mitarbeiter_id, liste_id, conn, is_admin=is_admin
        ):
            return jsonify({'success': False, 'message': 'Keine Berechtigung.'}), 403
        rows = aufgabenliste_services.list_offene_themen_picker_fuer_aufgabenliste(
            liste_id, mitarbeiter_id, conn, is_admin=is_admin, limit=20
        )
    themen = []
    for r in rows:
        themen.append({
            'id': r['ID'],
            'bereich': r['Bereich'],
            'gewerk': r['Gewerk'],
            'status': r['Status'],
            'farbe': r['Farbe'] or '#6c757d',
        })
    return jsonify({'success': True, 'themen': themen})


@schichtbuch_bp.route('/aufgabenlisten/<int:liste_id>/thema-hinzufuegen', methods=['POST'])
@login_required
def aufgabenliste_thema_hinzufuegen(liste_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    thema_id = request.form.get('thema_id', type=int)
    if thema_id is None:
        body = request.get_json(silent=True) or {}
        try:
            thema_id = int(body.get('thema_id'))
        except (TypeError, ValueError):
            thema_id = None
    try:
        thema_id = int(thema_id)
    except (TypeError, ValueError):
        thema_id = None
    if not thema_id or thema_id < 1:
        err = 'Ungültige Themen-ID.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': err}), 400
        flash(err, 'danger')
        return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))

    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    with get_db_connection() as conn:
        ok, msg = aufgabenliste_services.add_thema_to_aufgabenliste(
            liste_id, thema_id, mitarbeiter_id, conn, is_admin=is_admin
        )
        if ok:
            conn.commit()
        else:
            conn.rollback()

    if is_xhr:
        if ok:
            return jsonify({'success': True, 'message': msg})
        return jsonify({'success': False, 'message': msg}), 400

    if ok:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')
    return redirect(url_for('schichtbuch.aufgabenliste_detail', liste_id=liste_id))


@schichtbuch_bp.route('/thema/<int:thema_id>/aufgabenlisten', methods=['GET'])
@login_required
def get_thema_aufgabenlisten(thema_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    with get_db_connection() as conn:
        if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
            return jsonify({'success': False, 'message': 'Kein Zugriff'}), 403
        data = aufgabenliste_services.get_thema_aufgabenlisten_json(
            thema_id, mitarbeiter_id, conn, is_admin=is_admin
        )
    return jsonify(data)


@schichtbuch_bp.route('/thema/<int:thema_id>/aufgabenlisten', methods=['POST'])
@login_required
def update_thema_aufgabenlisten(thema_id):
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    gewaehlt = request.form.getlist('aufgabenliste_ids')

    with get_db_connection() as conn:
        if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
            return jsonify({'success': False, 'message': 'Kein Zugriff'}), 403
        aufgabenliste_services.set_thema_aufgabenlisten(
            thema_id, mitarbeiter_id, gewaehlt, conn, is_admin=is_admin
        )
        conn.commit()
    return jsonify({'success': True, 'message': 'Gespeichert.'})


# ========== Dateien/Anhänge ==========

@schichtbuch_bp.route('/thema/<int:thema_id>/dateien')
@login_required
def thema_dateien(thema_id):
    """Liste alle Dateien für ein Thema"""
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        berechtigt, thema_exists = services.check_thema_datei_berechtigung(thema_id, user_id, conn)
        
        if not thema_exists:
            return jsonify({'success': False, 'message': 'Thema nicht gefunden'}), 404
        
        if not berechtigt:
            return jsonify({'success': False, 'message': 'Kein Zugriff auf dieses Thema'}), 403
    
        # Dateien aus Datei-Tabelle laden
        dateien_db = get_dateien_fuer_bereich('Thema', thema_id, conn)
        
        # In das Format konvertieren, das das Template erwartet
        dateien = []
        for d in dateien_db:
            # Dateigröße aus Dateisystem ermitteln
            filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], d['Dateipfad'].replace('/', os.sep))
            file_size_str = '0 KB'
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                file_size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
            
            # Dateiendung ermitteln
            file_ext = os.path.splitext(d['Dateiname'])[1].lower()
            
            # Dateityp kategorisieren
            if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'] or d['Typ'] == 'Bild':
                file_type = 'image'
            elif file_ext == '.pdf' or d['Typ'] == 'PDF':
                file_type = 'pdf'
            else:
                file_type = 'document'
            
            # Dateiname aus Dateipfad extrahieren (mit Timestamp)
            dateiname_mit_timestamp = os.path.basename(d['Dateipfad'])
            
            dateien.append({
                'name': d['Dateiname'],
                'path': d['Dateipfad'],
                'size': file_size_str,
                'type': file_type,
                'ext': file_ext,
                'beschreibung': d['Beschreibung'] or '',
                'id': d['ID'],
                'url': url_for('schichtbuch.thema_datei_download', thema_id=thema_id, filename=dateiname_mit_timestamp)
            })
    
    return jsonify({'success': True, 'dateien': dateien})


@schichtbuch_bp.route('/thema/<int:thema_id>/datei/<path:filename>')
@login_required
def thema_datei_download(thema_id, filename):
    """Stelle eine Datei zum Download/Anzeigen bereit"""
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        berechtigt, thema_exists = services.check_thema_datei_berechtigung(thema_id, user_id, conn)
        
        if not thema_exists:
            return "Thema nicht gefunden", 404
        
        if not berechtigt:
            return "Kein Zugriff auf dieses Thema", 403
        
        # Nur Dateien, die explizit zu diesem Thema-Ordner gehoeren und
        # deren Dateiname exakt dem angeforderten Namen entspricht.
        expected_suffix = f'Schichtbuch/Themen/{int(thema_id)}/{filename}'
        datei = conn.execute('''
            SELECT Dateipfad FROM Datei
            WHERE BereichTyp = 'Thema' AND BereichID = ?
              AND REPLACE(Dateipfad, '\\', '/') = ?
        ''', (thema_id, expected_suffix)).fetchone()
        
        if not datei:
            return "Datei nicht gefunden", 404
    
    from utils.security import resolve_under_base, PathTraversalError
    try:
        filepath = resolve_under_base(current_app.config['UPLOAD_BASE_FOLDER'], datei['Dateipfad'])
    except PathTraversalError:
        return "Ungültiger Dateipfad", 403

    if not os.path.isfile(filepath):
        return "Datei nicht gefunden", 404

    return send_from_directory(os.path.dirname(filepath), os.path.basename(filepath))


@schichtbuch_bp.route('/thema/<int:thema_id>/upload', methods=['POST'])
@login_required
def thema_datei_upload(thema_id):
    """Lade eine Datei für ein Thema hoch"""
    user_id = session.get('user_id')
    beschreibung = request.form.get('beschreibung', '').strip() if request.form else ''
    
    with get_db_connection() as conn:
        berechtigt, thema_exists = services.check_thema_datei_berechtigung(thema_id, user_id, conn)
        
        if not thema_exists:
            return jsonify({'success': False, 'message': 'Thema nicht gefunden'}), 404
        
        if not berechtigt:
            return jsonify({'success': False, 'message': 'Kein Zugriff auf dieses Thema'}), 403
    
    # Prüfen ob Datei hochgeladen wurde
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Keine Datei ausgewählt'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Keine Datei ausgewählt'}), 400
    
    thema_folder = os.path.join(current_app.config['SCHICHTBUCH_UPLOAD_FOLDER'], str(thema_id))
    create_upload_folder(thema_folder)
    
    # Datei speichern mit Timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    original_filename = file.filename
    file.filename = timestamp + secure_filename(original_filename)
    
    success, filename, error_message = save_uploaded_file(
        file,
        thema_folder,
        allowed_extensions=current_app.config['ALLOWED_EXTENSIONS'],
        create_unique_name=False  # Wir haben bereits einen eindeutigen Namen erstellt
    )
    
    if not success:
        return jsonify({'success': False, 'message': error_message}), 400
    
    try:
        with get_db_connection() as conn:
            # Datenbankeintrag in Datei-Tabelle
            relative_path = f'Schichtbuch/Themen/{thema_id}/{filename}'
            typ = get_datei_typ_aus_dateiname(original_filename)
            speichere_datei(
                bereich_typ='Thema',
                bereich_id=thema_id,
                dateiname=original_filename,
                dateipfad=relative_path,
                beschreibung=beschreibung,
                typ=typ,
                mitarbeiter_id=user_id,
                conn=conn
            )
        loesche_import_kopie_nach_upload(
            original_filename,
            current_app.config['IMPORT_FOLDER'],
            originale_loeschen_aus_formular(),
        )
        
        return jsonify({
            'success': True, 
            'message': f'Datei "{original_filename}" erfolgreich hochgeladen',
            'filename': filename
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Speichern: {str(e)}'}), 500


@schichtbuch_bp.route('/thema/<int:thema_id>/datei/<int:datei_id>/loeschen', methods=['POST'])
@login_required
def thema_datei_loeschen(thema_id, datei_id):
    """Datei für ein Thema löschen"""
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Berechtigung prüfen
        berechtigt, thema_exists = services.check_thema_datei_berechtigung(thema_id, user_id, conn)
        
        if not thema_exists:
            flash('Thema nicht gefunden.', 'danger')
            return redirect(url_for('schichtbuch.themaliste'))
        
        if not berechtigt:
            flash('Sie haben keine Berechtigung, Dateien für dieses Thema zu löschen.', 'danger')
            return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
        
        # Prüfe ob Datei zu diesem Thema gehört
        datei = conn.execute('''
            SELECT ID, Dateipfad, BereichTyp, BereichID
            FROM Datei
            WHERE ID = ? AND BereichTyp = 'Thema' AND BereichID = ?
        ''', (datei_id, thema_id)).fetchone()
        
        if not datei:
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
        
        # Datei vom Dateisystem löschen
        from modules.ersatzteile.services import loesche_datei
        filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], datei['Dateipfad'].replace('/', os.sep))
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Fehler beim Löschen der Datei vom Dateisystem: {e}")
        
        # Datenbankeintrag löschen
        loesche_datei(datei_id, conn)
        
        flash('Datei erfolgreich gelöscht.', 'success')
    
    return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))


# ========== Benachrichtigungen ==========

@schichtbuch_bp.route('/api/benachrichtigungen')
@login_required
def api_benachrichtigungen():
    """API: Ungelesene Benachrichtigungen (delegiert an zentrale Logik, alle Module)."""
    from utils.benachrichtigungen import build_ungelesen_benachrichtigungen_api_dict

    mitarbeiter_id = session.get('user_id')
    with get_db_connection() as conn:
        payload = build_ungelesen_benachrichtigungen_api_dict(mitarbeiter_id, conn, limit=20)
    return jsonify(payload)


@schichtbuch_bp.route('/api/benachrichtigungen/<int:benachrichtigung_id>/gelesen', methods=['POST'])
@login_required
def api_benachrichtigung_gelesen(benachrichtigung_id):
    """API: Benachrichtigung als gelesen markieren"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Prüfen ob Benachrichtigung dem Benutzer gehört
        benachrichtigung = conn.execute('''
            SELECT ID FROM Benachrichtigung 
            WHERE ID = ? AND MitarbeiterID = ?
        ''', (benachrichtigung_id, mitarbeiter_id)).fetchone()
        
        if not benachrichtigung:
            return jsonify({'success': False, 'message': 'Benachrichtigung nicht gefunden'}), 404
        
        # Als gelesen markieren
        conn.execute('''
            UPDATE Benachrichtigung SET Gelesen = 1 
            WHERE ID = ?
        ''', (benachrichtigung_id,))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Benachrichtigung als gelesen markiert'})


@schichtbuch_bp.route('/api/benachrichtigungen/alle-gelesen', methods=['POST'])
@login_required
def api_alle_benachrichtigungen_gelesen():
    """API: Alle Benachrichtigungen als gelesen markieren"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        conn.execute('''
            UPDATE Benachrichtigung SET Gelesen = 1 
            WHERE MitarbeiterID = ? AND Gelesen = 0
        ''', (mitarbeiter_id,))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'Alle Benachrichtigungen als gelesen markiert'})


# ========== PDF-Export ==========

def hex_to_color(hex_color):
    """Konvertiert Hex-Farbe zu ReportLab Color"""
    if not hex_color or not hex_color.startswith('#'):
        return colors.HexColor('#6c757d')
    try:
        return colors.HexColor(hex_color)
    except:
        return colors.HexColor('#6c757d')


@schichtbuch_bp.route('/thema/<int:thema_id>/pdf')
@login_required
def thema_pdf_export(thema_id):
    """PDF-Export für ein Thema"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        # Berechtigungsprüfung
        with get_db_connection() as conn:
            if not services.check_thema_berechtigung(thema_id, mitarbeiter_id, conn):
                flash('Sie haben keine Berechtigung, dieses Thema zu exportieren.', 'danger')
                return redirect(url_for('schichtbuch.themaliste'))

            # Bericht generieren
            content, filename, mimetype, is_pdf = generate_thema_pdf(thema_id, conn)
            
            response = make_response(content)
            response.headers['Content-Type'] = mimetype
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('schichtbuch.themaliste'))
    except FileNotFoundError as e:
        flash(str(e), 'danger')
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
    except Exception as e:
        flash(f'Fehler beim Erstellen des Berichts: {str(e)}', 'danger')
        print(f"Themen-Export Fehler: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
