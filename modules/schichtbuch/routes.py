"""
Schichtbuch Routes - Themenliste, Details, Bemerkungen
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app, Response
from datetime import datetime
import os
import sqlite3
from xml.sax.saxutils import escape
from werkzeug.utils import secure_filename
from io import BytesIO
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Image
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from . import schichtbuch_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter


def get_datei_anzahl(thema_id):
    """Ermittelt die Anzahl der Dateien für ein Thema"""
    thema_folder = os.path.join(current_app.config['SCHICHTBUCH_UPLOAD_FOLDER'], str(thema_id))
    if not os.path.exists(thema_folder):
        return 0
    try:
        files = os.listdir(thema_folder)
        return len([f for f in files if os.path.isfile(os.path.join(thema_folder, f))])
    except:
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
    
    items_per_page = 50

    with get_db_connection() as conn:
        # Abteilungsfilter: Nur Themen aus sichtbaren Abteilungen
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        
        query = '''
            SELECT 
                t.ID,
                b.Bezeichnung AS Bereich,
                g.Bezeichnung AS Gewerk,
                s.Bezeichnung AS Status,
                s.Farbe AS Farbe,
                abt.Bezeichnung AS Abteilung,
                COALESCE(MAX(bm.Datum), '1900-01-01') AS LetzteBemerkungDatum,
                COALESCE(MAX(bm.MitarbeiterID), 0) AS LetzteMitarbeiterID,
                COALESCE(MAX(m.Vorname), '') AS LetzteMitarbeiterVorname,
                COALESCE(MAX(m.Nachname), '') AS LetzteMitarbeiterNachname,
                COALESCE(MAX(ta.Bezeichnung), '') AS LetzteTatigkeit
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Status s ON t.StatusID = s.ID
            LEFT JOIN Abteilung abt ON t.ErstellerAbteilungID = abt.ID
            LEFT JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID AND bm.Gelöscht = 0
            LEFT JOIN Mitarbeiter m ON bm.MitarbeiterID = m.ID
            LEFT JOIN Taetigkeit ta ON bm.TaetigkeitID = ta.ID
            WHERE t.Gelöscht = 0
        '''
        params = []
        
        # Sichtbarkeitsfilter: Nur Themen anzeigen, für die Berechtigung besteht
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f''' AND EXISTS (
                SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                WHERE sv.ThemaID = t.ID 
                AND sv.AbteilungID IN ({placeholders})
            )'''
            params.extend(sichtbare_abteilungen)

        if bereich_filter:
            query += ' AND b.Bezeichnung = ?'
            params.append(bereich_filter)

        if gewerk_filter:
            query += ' AND g.Bezeichnung = ?'
            params.append(gewerk_filter)

        if status_filter_list:
            placeholders = ','.join(['?'] * len(status_filter_list))
            query += f' AND s.Bezeichnung IN ({placeholders})'
            params.extend(status_filter_list)

        if q_filter:
            query += ' AND EXISTS (SELECT 1 FROM SchichtbuchBemerkungen b2 WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0 AND b2.Bemerkung LIKE ? )'
            params.append(f'%{q_filter}%')

        query += ' GROUP BY t.ID'
        query += ''' ORDER BY 
                        LetzteBemerkungDatum DESC,
                        LetzteMitarbeiterNachname ASC,
                        LetzteMitarbeiterVorname ASC,
                        Bereich ASC,
                        Gewerk ASC,
                        LetzteTatigkeit ASC,
                        Status ASC
                    LIMIT ?'''
        params.append(items_per_page)

        themen = conn.execute(query, params).fetchall()

        # Nur Bemerkungen für die aktuell angezeigten Themen laden
        if themen:
            thema_ids = [t['ID'] for t in themen]
            placeholders = ','.join(['?'] * len(thema_ids))
            bemerkungen = conn.execute(f'''
                SELECT 
                    b.ThemaID,
                    b.Datum,
                    b.Bemerkung,
                    m.Vorname,
                    m.Nachname,
                    t.Bezeichnung AS Taetigkeit
                FROM SchichtbuchBemerkungen b
                JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
                LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
                WHERE b.Gelöscht = 0 AND b.ThemaID IN ({placeholders})
                ORDER BY b.ThemaID DESC, b.Datum DESC
            ''', thema_ids).fetchall()
        else:
            bemerkungen = []

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

    # Nach Thema gruppieren
    bemerk_dict = {}
    for b in bemerkungen:
        bemerk_dict.setdefault(b['ThemaID'], []).append(b)

    return render_template(
        'sbThemaListe.html',
        themen=themen,
        bemerk_dict=bemerk_dict,
        status_liste=status_liste,
        bereich_liste=bereich_liste,
        taetigkeiten_liste=taetigkeiten_liste,
        status_filter_list=status_filter_list,
        bereich_filter=bereich_filter,
        gewerk_filter=gewerk_filter,
        q_filter=q_filter,
        gewerke_liste=gewerke_liste
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

    with get_db_connection() as conn:
        # Abteilungsfilter auch hier anwenden
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        
        query = '''
            SELECT 
                t.ID,
                b.Bezeichnung AS Bereich,
                g.Bezeichnung AS Gewerk,
                s.Bezeichnung AS Status,
                s.Farbe AS Farbe,
                abt.Bezeichnung AS Abteilung,
                COALESCE(MAX(bm.Datum), '1900-01-01') AS LetzteBemerkungDatum,
                COALESCE(MAX(bm.MitarbeiterID), 0) AS LetzteMitarbeiterID,
                COALESCE(MAX(m.Vorname), '') AS LetzteMitarbeiterVorname,
                COALESCE(MAX(m.Nachname), '') AS LetzteMitarbeiterNachname,
                COALESCE(MAX(ta.Bezeichnung), '') AS LetzteTatigkeit
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Status s ON t.StatusID = s.ID
            LEFT JOIN Abteilung abt ON t.ErstellerAbteilungID = abt.ID
            LEFT JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID AND bm.Gelöscht = 0
            LEFT JOIN Mitarbeiter m ON bm.MitarbeiterID = m.ID
            LEFT JOIN Taetigkeit ta ON bm.TaetigkeitID = ta.ID
            WHERE t.Gelöscht = 0
        '''
        params = []
        
        # Sichtbarkeitsfilter: Nur Themen anzeigen, für die Berechtigung besteht
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f''' AND EXISTS (
                SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                WHERE sv.ThemaID = t.ID 
                AND sv.AbteilungID IN ({placeholders})
            )'''
            params.extend(sichtbare_abteilungen)

        if bereich_filter:
            query += ' AND b.Bezeichnung = ?'
            params.append(bereich_filter)

        if gewerk_filter:
            query += ' AND g.Bezeichnung = ?'
            params.append(gewerk_filter)

        if status_filter_list:
            placeholders = ','.join(['?'] * len(status_filter_list))
            query += f' AND s.Bezeichnung IN ({placeholders})'
            params.extend(status_filter_list)

        if q_filter:
            query += ' AND EXISTS (SELECT 1 FROM SchichtbuchBemerkungen b2 WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0 AND b2.Bemerkung LIKE ? )'
            params.append(f'%{q_filter}%')

        query += ' GROUP BY t.ID ORDER BY LetzteBemerkungDatum DESC, LetzteMitarbeiterNachname ASC, LetzteMitarbeiterVorname ASC, Bereich ASC, Gewerk ASC, LetzteTatigkeit ASC, Status ASC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        themen = conn.execute(query, params).fetchall()

        # Nur Bemerkungen für diese Themen laden
        if themen:
            thema_ids = [t['ID'] for t in themen]
            placeholders = ','.join(['?'] * len(thema_ids))
            bemerkungen = conn.execute(f'''
                SELECT 
                    b.ThemaID,
                    b.Datum,
                    b.Bemerkung,
                    m.Vorname,
                    m.Nachname,
                    t.Bezeichnung AS Taetigkeit
                FROM SchichtbuchBemerkungen b
                JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
                LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
                WHERE b.Gelöscht = 0 AND b.ThemaID IN ({placeholders})
                ORDER BY b.ThemaID DESC, b.Datum DESC
            ''', thema_ids).fetchall()
        else:
            bemerkungen = []

    # Nach Thema gruppieren
    bemerk_dict = {}
    for b in bemerkungen:
        bemerk_dict.setdefault(b['ThemaID'], []).append(b)

    # Als JSON zurückgeben
    return jsonify({
        'themen': [dict(t) for t in themen],
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
    next_url = request.form.get('next') or url_for('schichtbuch.themaliste')
    

    if not thema_id or not bemerkung_text:
        flash("Fehler: Thema oder Bemerkung fehlt.", "danger")
        return redirect(next_url)

    mitarbeiter_id = session.get('user_id')
    datum = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Neue Bemerkung speichern
        cursor.execute("""
            INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Bemerkung, Datum, TaetigkeitID)
            VALUES (?, ?, ?, ?, ?)
            """, (thema_id, mitarbeiter_id, bemerkung_text, datum, taetigkeit_id))
        
        bemerkung_id = cursor.lastrowid
        
        # Benachrichtigungen für andere Mitarbeiter erstellen
        from utils import erstelle_benachrichtigung_fuer_bemerkung
        try:
            erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id, conn)
        except Exception as e:
            print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")

        neuer_status = None
        neue_farbe = None

        # Falls Status geändert wird
        if status_id and status_id.isdigit():
            cursor.execute("UPDATE SchichtbuchThema SET StatusID = ? WHERE ID = ?", (status_id, thema_id))
            status_row = conn.execute("SELECT Bezeichnung, Farbe FROM Status WHERE ID = ?", (status_id,)).fetchone()
            if status_row:
                neuer_status = status_row["Bezeichnung"]
                neue_farbe = status_row["Farbe"]

        # Mitarbeitername holen
        user = conn.execute("SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?", (mitarbeiter_id,)).fetchone()

        conn.commit()

    # Wenn per AJAX (fetch)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        taetigkeit_name = None
        if taetigkeit_id:
            with get_db_connection() as conn:
                ta_row = conn.execute("SELECT Bezeichnung FROM Taetigkeit WHERE ID = ?", (taetigkeit_id,)).fetchone()
                if ta_row:
                    taetigkeit_name = ta_row["Bezeichnung"]

        return jsonify({
            "success": True,
            "thema_id": thema_id,
            "datum": datum,
            "bemerkung": bemerkung_text,
            "vorname": user["Vorname"],
            "nachname": user["Nachname"],
            "taetigkeit": taetigkeit_name,
            "neuer_status": neuer_status,
            "neue_farbe": neue_farbe
        })
    else: 
        flash("Bemerkung erfolgreich hinzugefügt.", "success")
        return redirect(next_url)


@schichtbuch_bp.route('/themaneu', methods=['GET', 'POST'])
@login_required
def themaneu():
    """Neues Thema + erste Bemerkung"""
    # POST = neues Thema speichern
    if request.method == 'POST':
        mitarbeiter_id = session.get('user_id')
        gewerk_id = request.form['gewerk']
        taetigkeit_id = request.form['taetigkeit']
        status_id = request.form['status']
        bemerkung = request.form['bemerkung']
        sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')

        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # Primärabteilung des Erstellers ermitteln
            mitarbeiter = conn.execute(
                'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
                (mitarbeiter_id,)
            ).fetchone()
            
            ersteller_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None

            # Thema mit Abteilung anlegen
            cur.execute(
                'INSERT INTO SchichtbuchThema (GewerkID, StatusID, ErstellerAbteilungID) VALUES (?, ?, ?)',
                (gewerk_id, status_id, ersteller_abteilung_id)
            )
            thema_id = cur.lastrowid

            # Erste Bemerkung hinzufügen
            cur.execute('''
                INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
            ''', (thema_id, mitarbeiter_id, taetigkeit_id, bemerkung))
            
            # Imports für Benachrichtigungen und Unterabteilungen
            from utils import erstelle_benachrichtigung_fuer_neues_thema, get_untergeordnete_abteilungen
            
            # Sichtbarkeiten speichern
            # Alle Abteilungs-IDs sammeln (inkl. Unterabteilungen und Duplikate vermeiden)
            alle_sichtbarkeits_ids = set()
            
            if sichtbare_abteilungen:
                for abt_id in sichtbare_abteilungen:
                    abt_id_int = int(abt_id)
                    alle_sichtbarkeits_ids.add(abt_id_int)
                    # Unterabteilungen auch hinzufügen (Funktion gibt direkt IDs zurück)
                    unterabteilungen = get_untergeordnete_abteilungen(abt_id_int, conn)
                    alle_sichtbarkeits_ids.update(unterabteilungen)
            else:
                # Fallback: Wenn nichts ausgewählt, nur Ersteller-Abteilung
                if ersteller_abteilung_id:
                    alle_sichtbarkeits_ids.add(ersteller_abteilung_id)
                    # Unterabteilungen auch hinzufügen (Funktion gibt direkt IDs zurück)
                    unterabteilungen = get_untergeordnete_abteilungen(ersteller_abteilung_id, conn)
                    alle_sichtbarkeits_ids.update(unterabteilungen)
            
            # Benachrichtigungen für Mitarbeiter in sichtbaren Abteilungen erstellen
            try:
                if alle_sichtbarkeits_ids:
                    erstelle_benachrichtigung_fuer_neues_thema(thema_id, list(alle_sichtbarkeits_ids), conn)
            except Exception as e:
                print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
            
            # Sichtbarkeiten einfügen (INSERT OR IGNORE verhindert Duplikate)
            for abt_id in alle_sichtbarkeits_ids:
                try:
                    cur.execute('''
                        INSERT OR IGNORE INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
                        VALUES (?, ?)
                    ''', (thema_id, abt_id))
                except sqlite3.IntegrityError:
                    # Duplikat ignorieren (falls INSERT OR IGNORE nicht funktioniert)
                    pass

            conn.commit()

            # Taetigkeit-Name holen
            taetigkeit_row = conn.execute(
                "SELECT Bezeichnung FROM Taetigkeit WHERE ID = ?",
                (taetigkeit_id,)
            ).fetchone()
            taetigkeit_name = taetigkeit_row["Bezeichnung"] if taetigkeit_row else None

            # Neu erstellten Datensatz abrufen
            thema = conn.execute('''
                SELECT 
                    t.ID, 
                    b.Bezeichnung AS Bereich,
                    g.Bezeichnung AS Gewerk,
                    s.Bezeichnung AS Status,
                    ? AS LetzteBemerkung,
                    CURRENT_TIMESTAMP AS LetzteBemerkungDatum
                FROM SchichtbuchThema t
                JOIN Gewerke g ON t.GewerkID = g.ID
                JOIN Bereich b ON g.BereichID = b.ID
                JOIN Status s ON t.StatusID = s.ID
                WHERE t.ID = ?
            ''', (bemerkung, thema_id)).fetchone()

        # Für AJAX → JSON zurückgeben
        return jsonify({
            "ID": thema["ID"],
            "Bereich": thema["Bereich"],
            "Gewerk": thema["Gewerk"],
            "Taetigkeit": taetigkeit_name,
            "Status": thema["Status"],
            "LetzteBemerkung": thema["LetzteBemerkung"],
            "LetzteBemerkungDatum": thema["LetzteBemerkungDatum"]
        })

    # GET = Seite anzeigen
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        gewerke = conn.execute('''
            SELECT G.ID, G.Bezeichnung, B.ID AS BereichID, B.Bezeichnung AS Bereich
            FROM Gewerke G
            JOIN Bereich B ON G.BereichID = B.ID
            WHERE G.Aktiv = 1 AND B.Aktiv = 1
            ORDER BY B.Bezeichnung, G.Bezeichnung
        ''').fetchall()

        taetigkeiten = conn.execute('SELECT * FROM Taetigkeit WHERE Aktiv = 1 ORDER BY Sortierung ASC').fetchall()
        status = conn.execute('SELECT * FROM Status WHERE Aktiv = 1 ORDER BY Sortierung ASC').fetchall()
        bereiche = conn.execute('SELECT * FROM Bereich WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
        
        # Primärabteilung des Mitarbeiters
        mitarbeiter = conn.execute(
            'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
            (mitarbeiter_id,)
        ).fetchone()
        primaer_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
        
        # Auswählbare Abteilungen für Sichtbarkeitssteuerung (mit ALLEN Unterabteilungen für neues Thema)
        from utils import get_auswaehlbare_abteilungen_fuer_neues_thema
        auswaehlbare_abteilungen = get_auswaehlbare_abteilungen_fuer_neues_thema(mitarbeiter_id, conn)

    return render_template(
        'sbThemaNeu.html',
        gewerke=gewerke,
        taetigkeiten=taetigkeiten,
        status=status,
        bereiche=bereiche,
        auswaehlbare_abteilungen=auswaehlbare_abteilungen,
        primaer_abteilung_id=primaer_abteilung_id
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


@schichtbuch_bp.route('/thema/<int:thema_id>', methods=['GET', 'POST'])
@login_required
def thema_detail(thema_id):
    """Thema-Detail-Seite"""
    mitarbeiter_id = session.get('user_id')
    
    # Berechtigungsprüfung: Darf der Benutzer dieses Thema sehen?
    with get_db_connection() as conn:
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            berechtigt = conn.execute(f'''
                SELECT COUNT(*) as count FROM SchichtbuchThemaSichtbarkeit
                WHERE ThemaID = ? AND AbteilungID IN ({placeholders})
            ''', [thema_id] + sichtbare_abteilungen).fetchone()
            
            if berechtigt['count'] == 0:
                flash('Sie haben keine Berechtigung, dieses Thema zu sehen.', 'danger')
                return redirect(url_for('schichtbuch.themaliste'))
    
    if request.method == 'POST':
        if not mitarbeiter_id:
            flash('Bitte zuerst anmelden.', 'warning')
            return redirect(url_for('auth.login'))

        bemerkung = request.form['bemerkung']
        neuer_status = request.form.get('status')
        taetigkeit_id = request.form.get("taetigkeit_id")
        datum = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db_connection() as conn:
            # Bemerkung speichern
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung)
                VALUES (?, ?, ?, ?, ?)
            ''', (thema_id, mitarbeiter_id, datum, taetigkeit_id, bemerkung))
            
            bemerkung_id = cursor.lastrowid
            
            # Benachrichtigungen für andere Mitarbeiter erstellen
            from utils import erstelle_benachrichtigung_fuer_bemerkung
            try:
                erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id, conn)
            except Exception as e:
                print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")

            # Status ggf. ändern
            if neuer_status and neuer_status != "":
                conn.execute('UPDATE SchichtbuchThema SET StatusID = ? WHERE ID = ?', (neuer_status, thema_id))

            conn.commit()

    # Thema-Infos abrufen
    with get_db_connection() as conn:
        thema = conn.execute('''
            SELECT 
                t.ID, 
                g.Bezeichnung AS Gewerk,
                b.Bezeichnung AS Bereich,
                s.Bezeichnung AS Status, 
                s.ID AS StatusID,
                s.Farbe AS StatusFarbe,
                a.Bezeichnung AS Abteilung
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Status s ON t.StatusID = s.ID
            LEFT JOIN Abteilung a ON t.ErstellerAbteilungID = a.ID
            WHERE t.ID = ?
        ''', (thema_id,)).fetchone()

        # Sichtbare Abteilungen für dieses Thema laden
        sichtbarkeiten = conn.execute('''
            SELECT a.Bezeichnung, a.ParentAbteilungID
            FROM SchichtbuchThemaSichtbarkeit sv
            JOIN Abteilung a ON sv.AbteilungID = a.ID
            WHERE sv.ThemaID = ?
            ORDER BY a.Sortierung, a.Bezeichnung
        ''', (thema_id,)).fetchall()

        # Alle Status-Werte für Dropdown
        status_liste = conn.execute('SELECT * FROM Status ORDER BY Sortierung ASC').fetchall()
        taetigkeiten = conn.execute('SELECT * FROM Taetigkeit ORDER BY Sortierung ASC').fetchall()

        # Bemerkungen zu diesem Thema
        bemerkungen = conn.execute('''
            SELECT 
                b.ID AS BemerkungID,
                b.Datum,
                b.MitarbeiterID,
                m.Vorname,
                m.Nachname,
                b.Bemerkung,
                b.TaetigkeitID,
                t.Bezeichnung AS Taetigkeit
            FROM SchichtbuchBemerkungen b
            JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
            LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
            WHERE b.ThemaID = ? AND b.Gelöscht = 0
            ORDER BY b.Datum DESC
        ''', (thema_id,)).fetchall()

        mitarbeiter = conn.execute('SELECT * FROM Mitarbeiter').fetchall()

        # Alle Lagerbuchungen für dieses Thema laden (Eingang, Ausgang, Inventur)
        thema_lagerbuchungen = conn.execute('''
            SELECT 
                l.ID AS BuchungsID,
                l.ErsatzteilID,
                l.Typ,
                l.Menge,
                l.Grund,
                l.Buchungsdatum,
                l.Bemerkung,
                l.Preis,
                l.Waehrung,
                e.Bestellnummer,
                e.Bezeichnung AS ErsatzteilBezeichnung,
                m.Vorname || ' ' || m.Nachname AS VerwendetVon,
                k.Bezeichnung AS Kostenstelle
            FROM Lagerbuchung l
            JOIN Ersatzteil e ON l.ErsatzteilID = e.ID
            LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
            LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
            WHERE l.ThemaID = ?
            ORDER BY l.Buchungsdatum DESC
        ''', (thema_id,)).fetchall()

        # Verfügbare Ersatzteile für den aktuellen Benutzer laden
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        verfuegbare_query = '''
            SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.AktuellerBestand, e.Einheit
            FROM Ersatzteil e
            WHERE e.Gelöscht = 0 AND e.Aktiv = 1 AND e.AktuellerBestand > 0
        '''
        verfuegbare_params = []
        
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            verfuegbare_query += f'''
                AND e.ID IN (
                    SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                    WHERE AbteilungID IN ({placeholders})
                )
            '''
            verfuegbare_params.extend(sichtbare_abteilungen)
        elif not is_admin:
            verfuegbare_query += ' AND 1=0'
        
        verfuegbare_query += ' ORDER BY e.Bezeichnung'
        verfuegbare_ersatzteile = conn.execute(verfuegbare_query, verfuegbare_params).fetchall()

        # Kostenstellen für Dropdown
        kostenstellen = conn.execute('SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()

    previous_page = request.args.get('next') or url_for('index')
    
    # Dateianzahl ermitteln
    datei_anzahl = get_datei_anzahl(thema_id)

    return render_template(
        'sbThemaDetail.html',
        thema=thema,
        bemerkungen=bemerkungen,
        mitarbeiter=mitarbeiter,
        status_liste=status_liste,
        taetigkeiten=taetigkeiten,
        sichtbarkeiten=sichtbarkeiten,
        previous_page=previous_page,
        datei_anzahl=datei_anzahl,
        ersatzteil_verknuepfungen=thema_lagerbuchungen,
        verfuegbare_ersatzteile=verfuegbare_ersatzteile,
        kostenstellen=kostenstellen
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
    """Thema löschen (Soft-Delete)"""
    with get_db_connection() as conn:
        conn.execute('UPDATE SchichtbuchThema SET Gelöscht = 1 WHERE ID = ?', (thema_id,))
        conn.commit()
    flash(f'Thema #{thema_id} wurde gelöscht.', 'info')
    next_url = request.referrer or url_for('schichtbuch.themaliste')
    return redirect(next_url)


@schichtbuch_bp.route('/delete_bemerkung/<int:bemerkung_id>', methods=['POST'])
@login_required
def delete_bemerkung(bemerkung_id):
    """Bemerkung löschen (Soft-Delete)"""
    with get_db_connection() as conn:
        conn.execute('UPDATE SchichtbuchBemerkungen SET Gelöscht = 1 WHERE ID = ?', (bemerkung_id,))
        conn.commit()
    flash(f'Bemerkung #{bemerkung_id} wurde gelöscht.', 'info')
    next_url = request.referrer or url_for('schichtbuch.themaliste')
    return redirect(next_url)


@schichtbuch_bp.route('/thema/<int:thema_id>/sichtbarkeit', methods=['GET'])
@login_required
def get_thema_sichtbarkeit(thema_id):
    """AJAX: Sichtbarkeiten eines Themas laden"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Primärabteilung des Mitarbeiters
        mitarbeiter = conn.execute(
            'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
            (mitarbeiter_id,)
        ).fetchone()
        primaer_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
        
        # Auswählbare Abteilungen (eigene + untergeordnete)
        from utils import get_auswaehlbare_abteilungen_fuer_mitarbeiter, get_mitarbeiter_abteilungen
        auswaehlbare = get_auswaehlbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        eigene_abteilungen_ids = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
        
        # Aktuell ausgewählte Sichtbarkeiten mit Details
        aktuelle = conn.execute('''
            SELECT sv.AbteilungID, a.Bezeichnung, a.ParentAbteilungID, a.Sortierung
            FROM SchichtbuchThemaSichtbarkeit sv
            JOIN Abteilung a ON sv.AbteilungID = a.ID
            WHERE sv.ThemaID = ?
            ORDER BY a.Sortierung, a.Bezeichnung
        ''', (thema_id,)).fetchall()
        aktuelle_ids = [a['AbteilungID'] for a in aktuelle]
        
        # Alle eigenen Abteilungen mit allen Unterabteilungen (für Vergleich)
        from utils import get_untergeordnete_abteilungen
        alle_eigene_mit_unter = set()
        for abt_id in eigene_abteilungen_ids:
            alle_eigene_mit_unter.update(get_untergeordnete_abteilungen(abt_id, conn))
        
        # Alle aktuell zugewiesenen Abteilungen, die NICHT in den eigenen (inkl. Unterabteilungen) sind
        zusaetzliche_aktuelle = []
        for akt in aktuelle:
            if akt['AbteilungID'] not in alle_eigene_mit_unter:
                # Parent-Abteilung finden (falls vorhanden)
                parent_info = None
                if akt['ParentAbteilungID']:
                    parent = conn.execute(
                        'SELECT ID, Bezeichnung FROM Abteilung WHERE ID = ?',
                        (akt['ParentAbteilungID'],)
                    ).fetchone()
                    if parent:
                        parent_info = {'id': parent['ID'], 'name': parent['Bezeichnung']}
                
                zusaetzliche_aktuelle.append({
                    'id': akt['AbteilungID'],
                    'name': akt['Bezeichnung'],
                    'parent': parent_info,
                    'is_own': False
                })
        
        # In JSON-Format umwandeln
        auswaehlbare_json = []
        for gruppe in auswaehlbare:
            children_json = []
            for c in gruppe['children']:
                is_current = c['ID'] in aktuelle_ids
                children_json.append({
                    'id': c['ID'], 
                    'name': c['Bezeichnung'],
                    'is_current': is_current
                })
            
            is_current_parent = gruppe['parent']['ID'] in aktuelle_ids
            auswaehlbare_json.append({
                'parent': {
                    'id': gruppe['parent']['ID'],
                    'name': gruppe['parent']['Bezeichnung'],
                    'is_primaer': gruppe['parent']['ID'] == primaer_abteilung_id,
                    'is_current': is_current_parent
                },
                'children': children_json
            })
        
        return jsonify({
            'success': True,
            'thema_id': thema_id,
            'auswaehlbare': auswaehlbare_json,
            'zusaetzliche': zusaetzliche_aktuelle,
            'aktuelle': aktuelle_ids
        })


@schichtbuch_bp.route('/thema/<int:thema_id>/sichtbarkeit', methods=['POST'])
@login_required
def update_thema_sichtbarkeit(thema_id):
    """AJAX: Sichtbarkeiten eines Themas aktualisieren"""
    sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')
    
    if not sichtbare_abteilungen:
        return jsonify({'success': False, 'message': 'Mindestens eine Abteilung muss ausgewählt sein.'}), 400
    
    try:
        with get_db_connection() as conn:
            # Alte Sichtbarkeiten löschen
            conn.execute('DELETE FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?', (thema_id,))
            
            # Neue Sichtbarkeiten einfügen
            for abt_id in sichtbare_abteilungen:
                try:
                    conn.execute('''
                        INSERT INTO SchichtbuchThemaSichtbarkeit (ThemaID, AbteilungID)
                        VALUES (?, ?)
                    ''', (thema_id, abt_id))
                except sqlite3.IntegrityError:
                    pass  # Duplikat ignorieren
            
            conn.commit()
        
        return jsonify({'success': True, 'message': 'Sichtbarkeit erfolgreich aktualisiert.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500


# ========== Dateien/Anhänge ==========

@schichtbuch_bp.route('/thema/<int:thema_id>/dateien')
@login_required
def thema_dateien(thema_id):
    """Liste alle Dateien für ein Thema"""
    # Prüfen ob Benutzer Zugriff auf das Thema hat
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(user_id, conn)
        
        thema = conn.execute('''
            SELECT t.ID, t.ErstellerAbteilungID
            FROM SchichtbuchThema t
            WHERE t.ID = ? AND t.Gelöscht = 0
        ''', (thema_id,)).fetchone()
        
        if not thema:
            return jsonify({'success': False, 'message': 'Thema nicht gefunden'}), 404
        
        # Prüfen ob Thema für Benutzer sichtbar ist
        thema_sichtbarkeiten = conn.execute('''
            SELECT AbteilungID FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?
        ''', (thema_id,)).fetchall()
        
        thema_abteilungen = [s['AbteilungID'] for s in thema_sichtbarkeiten]
        
        if not any(abt in sichtbare_abteilungen for abt in thema_abteilungen):
            return jsonify({'success': False, 'message': 'Kein Zugriff auf dieses Thema'}), 403
    
    # Dateipfad ermitteln
    thema_folder = os.path.join(current_app.config['SCHICHTBUCH_UPLOAD_FOLDER'], str(thema_id))
    
    dateien = []
    if os.path.exists(thema_folder):
        for filename in os.listdir(thema_folder):
            filepath = os.path.join(thema_folder, filename)
            if os.path.isfile(filepath):
                # Dateigröße ermitteln
                file_size = os.path.getsize(filepath)
                file_size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
                
                # Dateiendung ermitteln
                file_ext = os.path.splitext(filename)[1].lower()
                
                # Dateityp kategorisieren
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    file_type = 'image'
                elif file_ext == '.pdf':
                    file_type = 'pdf'
                else:
                    file_type = 'document'
                
                dateien.append({
                    'name': filename,
                    'size': file_size_str,
                    'type': file_type,
                    'ext': file_ext,
                    'url': url_for('schichtbuch.thema_datei_download', thema_id=thema_id, filename=filename)
                })
    
    return jsonify({'success': True, 'dateien': dateien})


@schichtbuch_bp.route('/thema/<int:thema_id>/datei/<path:filename>')
@login_required
def thema_datei_download(thema_id, filename):
    """Stelle eine Datei zum Download/Anzeigen bereit"""
    # Prüfen ob Benutzer Zugriff auf das Thema hat
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(user_id, conn)
        
        thema = conn.execute('''
            SELECT t.ID, t.ErstellerAbteilungID
            FROM SchichtbuchThema t
            WHERE t.ID = ? AND t.Gelöscht = 0
        ''', (thema_id,)).fetchone()
        
        if not thema:
            return "Thema nicht gefunden", 404
        
        # Prüfen ob Thema für Benutzer sichtbar ist
        thema_sichtbarkeiten = conn.execute('''
            SELECT AbteilungID FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?
        ''', (thema_id,)).fetchall()
        
        thema_abteilungen = [s['AbteilungID'] for s in thema_sichtbarkeiten]
        
        if not any(abt in sichtbare_abteilungen for abt in thema_abteilungen):
            return "Kein Zugriff auf dieses Thema", 403
    
    # Dateipfad ermitteln
    thema_folder = os.path.join(current_app.config['SCHICHTBUCH_UPLOAD_FOLDER'], str(thema_id))
    
    # Sicherheitsprüfung: Datei muss im Thema-Ordner sein
    safe_path = os.path.abspath(os.path.join(thema_folder, filename))
    if not safe_path.startswith(os.path.abspath(thema_folder)):
        return "Ungültiger Dateipfad", 403
    
    return send_from_directory(thema_folder, filename)


@schichtbuch_bp.route('/thema/<int:thema_id>/upload', methods=['POST'])
@login_required
def thema_datei_upload(thema_id):
    """Lade eine Datei für ein Thema hoch"""
    # Prüfen ob Benutzer Zugriff auf das Thema hat
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(user_id, conn)
        
        thema = conn.execute('''
            SELECT t.ID, t.ErstellerAbteilungID
            FROM SchichtbuchThema t
            WHERE t.ID = ? AND t.Gelöscht = 0
        ''', (thema_id,)).fetchone()
        
        if not thema:
            return jsonify({'success': False, 'message': 'Thema nicht gefunden'}), 404
        
        # Prüfen ob Thema für Benutzer sichtbar ist
        thema_sichtbarkeiten = conn.execute('''
            SELECT AbteilungID FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?
        ''', (thema_id,)).fetchall()
        
        thema_abteilungen = [s['AbteilungID'] for s in thema_sichtbarkeiten]
        
        if not any(abt in sichtbare_abteilungen for abt in thema_abteilungen):
            return jsonify({'success': False, 'message': 'Kein Zugriff auf dieses Thema'}), 403
    
    # Prüfen ob Datei hochgeladen wurde
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Keine Datei ausgewählt'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Keine Datei ausgewählt'}), 400
    
    # Dateiendung prüfen
    def allowed_file(filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
    
    if not allowed_file(file.filename):
        allowed = ', '.join(current_app.config['ALLOWED_EXTENSIONS'])
        return jsonify({'success': False, 'message': f'Dateityp nicht erlaubt. Erlaubt sind: {allowed}'}), 400
    
    # Sicheren Dateinamen erstellen
    filename = secure_filename(file.filename)
    
    # Zielordner erstellen falls nicht vorhanden
    thema_folder = os.path.join(current_app.config['SCHICHTBUCH_UPLOAD_FOLDER'], str(thema_id))
    os.makedirs(thema_folder, exist_ok=True)
    
    # Prüfen ob Datei bereits existiert
    filepath = os.path.join(thema_folder, filename)
    if os.path.exists(filepath):
        # Dateiname mit Nummer versehen
        name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{name}_{counter}{ext}"
            filepath = os.path.join(thema_folder, filename)
            counter += 1
    
    try:
        # Datei speichern
        file.save(filepath)
        return jsonify({
            'success': True, 
            'message': f'Datei "{filename}" erfolgreich hochgeladen',
            'filename': filename
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Speichern: {str(e)}'}), 500


# ========== Benachrichtigungen ==========

@schichtbuch_bp.route('/api/benachrichtigungen')
@login_required
def api_benachrichtigungen():
    """API: Ungelesene Benachrichtigungen abrufen"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        benachrichtigungen = conn.execute('''
            SELECT 
                B.ID,
                B.Typ,
                B.Titel,
                B.Nachricht,
                B.ThemaID,
                B.ErstelltAm,
                T.GewerkID,
                G.Bezeichnung AS Gewerk,
                BE.Bezeichnung AS Bereich
            FROM Benachrichtigung B
            JOIN SchichtbuchThema T ON B.ThemaID = T.ID
            JOIN Gewerke G ON T.GewerkID = G.ID
            JOIN Bereich BE ON G.BereichID = BE.ID
            WHERE B.MitarbeiterID = ? AND B.Gelesen = 0 AND T.Gelöscht = 0
            ORDER BY B.ErstelltAm DESC
            LIMIT 20
        ''', (mitarbeiter_id,)).fetchall()
        
        anzahl_ungelesen = conn.execute('''
            SELECT COUNT(*) AS Anzahl
            FROM Benachrichtigung
            WHERE MitarbeiterID = ? AND Gelesen = 0
        ''', (mitarbeiter_id,)).fetchone()['Anzahl']
    
    return jsonify({
        'success': True,
        'benachrichtigungen': [dict(b) for b in benachrichtigungen],
        'anzahl_ungelesen': anzahl_ungelesen
    })


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
    
    # Berechtigungsprüfung
    with get_db_connection() as conn:
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            berechtigt = conn.execute(f'''
                SELECT COUNT(*) as count FROM SchichtbuchThemaSichtbarkeit
                WHERE ThemaID = ? AND AbteilungID IN ({placeholders})
            ''', [thema_id] + sichtbare_abteilungen).fetchone()
            
            if berechtigt['count'] == 0:
                flash('Sie haben keine Berechtigung, dieses Thema zu exportieren.', 'danger')
                return redirect(url_for('schichtbuch.themaliste'))
        
        # Thema-Informationen laden
        thema = conn.execute('''
            SELECT 
                t.ID,
                t.ErstelltAm,
                g.Bezeichnung AS Gewerk,
                b.Bezeichnung AS Bereich,
                s.Bezeichnung AS Status,
                s.Farbe AS StatusFarbe,
                a.Bezeichnung AS Abteilung
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Status s ON t.StatusID = s.ID
            LEFT JOIN Abteilung a ON t.ErstellerAbteilungID = a.ID
            WHERE t.ID = ?
        ''', (thema_id,)).fetchone()
        
        if not thema:
            flash('Thema nicht gefunden.', 'danger')
            return redirect(url_for('schichtbuch.themaliste'))
        
        # Sichtbare Abteilungen laden
        sichtbarkeiten = conn.execute('''
            SELECT a.Bezeichnung, a.ParentAbteilungID
            FROM SchichtbuchThemaSichtbarkeit sv
            JOIN Abteilung a ON sv.AbteilungID = a.ID
            WHERE sv.ThemaID = ?
            ORDER BY a.Sortierung, a.Bezeichnung
        ''', (thema_id,)).fetchall()
        
        # Bemerkungen laden (chronologisch, älteste zuerst)
        bemerkungen = conn.execute('''
            SELECT 
                b.ID AS BemerkungID,
                b.Datum,
                m.Vorname,
                m.Nachname,
                b.Bemerkung,
                t.Bezeichnung AS Taetigkeit
            FROM SchichtbuchBemerkungen b
            JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
            LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
            WHERE b.ThemaID = ? AND b.Gelöscht = 0
            ORDER BY b.Datum ASC
        ''', (thema_id,)).fetchall()
        
        # Ersatzteile für dieses Thema laden
        ersatzteile = conn.execute('''
            SELECT 
                l.ID AS BuchungsID,
                l.ErsatzteilID,
                l.Typ,
                l.Menge,
                l.Grund,
                l.Buchungsdatum,
                l.Bemerkung,
                l.Preis,
                l.Waehrung,
                e.Bestellnummer,
                e.Bezeichnung AS ErsatzteilBezeichnung,
                e.Einheit,
                m.Vorname || ' ' || m.Nachname AS VerwendetVon,
                k.Bezeichnung AS Kostenstelle
            FROM Lagerbuchung l
            JOIN Ersatzteil e ON l.ErsatzteilID = e.ID
            LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
            LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
            WHERE l.ThemaID = ?
            ORDER BY l.Buchungsdatum ASC
        ''', (thema_id,)).fetchall()
    
    # PDF erstellen mit moderneren Rändern
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2.5*cm, bottomMargin=2*cm)
    
    # Container für PDF-Inhalt
    story = []
    
    # Moderne Farbpalette
    primary_color = colors.HexColor('#2563eb')  # Modernes Blau
    secondary_color = colors.HexColor('#64748b')  # Grau
    accent_color = colors.HexColor('#0ea5e9')  # Helles Blau
    bg_light = colors.HexColor('#f8fafc')  # Sehr helles Grau
    bg_dark = colors.HexColor('#1e293b')  # Dunkles Grau für Header
    text_primary = colors.HexColor('#0f172a')  # Fast schwarz
    text_secondary = colors.HexColor('#475569')  # Mittleres Grau
    border_color = colors.HexColor('#e2e8f0')  # Helles Grau für Borders
    
    # Status-Farbe konvertieren
    status_color = hex_to_color(thema['StatusFarbe'])
    
    # Styles definieren
    styles = getSampleStyleSheet()
    
    # Header-Style (groß, modern)
    header_style = ParagraphStyle(
        'ModernHeader',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=bg_dark,
        spaceAfter=8,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        leading=28
    )
    
    # Subtitle-Style
    subtitle_style = ParagraphStyle(
        'ModernSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=text_secondary,
        spaceAfter=20,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    # Titel-Style für Abschnitte
    section_style = ParagraphStyle(
        'ModernSection',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=primary_color,
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold',
        leading=20
    )
    
    # Normaler Text
    normal_style = ParagraphStyle(
        'ModernNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=text_primary,
        leading=14,
        fontName='Helvetica',
        alignment=TA_LEFT
    )
    
    # Kleiner Text für Metadaten
    small_style = ParagraphStyle(
        'ModernSmall',
        parent=styles['Normal'],
        fontSize=9,
        textColor=text_secondary,
        leading=12,
        fontName='Helvetica'
    )
    
    # QR-Code mit ThemenID generieren
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=3,
        border=2,
    )
    qr.add_data(str(thema_id))
    qr.make(fit=True)
    
    # QR-Code als Bild erstellen
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    
    # QR-Code-Bild für ReportLab vorbereiten
    qr_image = Image(qr_buffer, width=2*cm, height=2*cm)
    
    # Header-Bereich mit modernem Design (inkl. QR-Code)
    header_table_data = [
        [
            Paragraph('<b>BIS</b><br/><font size="9" color="#64748b">Betriebsinformationssystem</font>', 
                     ParagraphStyle('HeaderLeft', parent=normal_style, fontSize=18, textColor=bg_dark, fontName='Helvetica-Bold')),
            Paragraph(f'<font size="20" color="#2563eb"><b>Thema #{thema["ID"]}</b></font>', 
                     ParagraphStyle('HeaderRight', parent=normal_style, fontSize=20, textColor=primary_color, alignment=TA_RIGHT, fontName='Helvetica-Bold')),
            qr_image
        ]
    ]
    header_table = Table(header_table_data, colWidths=[8*cm, 7*cm, 2*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    
    # Trennlinie unter Header
    story.append(Table([['']], colWidths=[17*cm], style=TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 2, primary_color),
        ('TOPPADDING', (0, 0), (0, 0), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 0),
    ])))
    story.append(Spacer(1, 0.8*cm))
    
    # Thema-Informationen als moderne Info-Box
    thema_info_data = []
    
    # Status-Badge mit Farbe
    status_bg = status_color if status_color else primary_color
    status_text = f'<font color="white"><b>{escape(str(thema["Status"]))}</b></font>'
    status_cell = Table([[Paragraph(status_text, ParagraphStyle('StatusBadge', parent=normal_style, 
                                                                 fontSize=10, textColor=colors.white, 
                                                                 alignment=TA_CENTER, fontName='Helvetica-Bold'))]], 
                        colWidths=[4*cm])
    status_cell.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), status_bg),
        ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (0, 0), 6),
        ('TOPPADDING', (0, 0), (0, 0), 6),
        ('ROWBACKGROUNDS', (0, 0), (0, 0), [status_bg]),
    ]))
    
    thema_info_data.append([
        Paragraph('<b>Bereich</b>', small_style),
        Paragraph(escape(str(thema['Bereich'])), normal_style)
    ])
    thema_info_data.append([
        Paragraph('<b>Gewerk</b>', small_style),
        Paragraph(escape(str(thema['Gewerk'])), normal_style)
    ])
    thema_info_data.append([
        Paragraph('<b>Status</b>', small_style),
        status_cell
    ])
    
    if thema['Abteilung']:
        thema_info_data.append([
            Paragraph('<b>Abteilung</b>', small_style),
            Paragraph(escape(str(thema['Abteilung'])), normal_style)
        ])
    
    if thema['ErstelltAm']:
        erstellt_datum = thema['ErstelltAm'][:10] if len(thema['ErstelltAm']) >= 10 else thema['ErstelltAm']
        thema_info_data.append([
            Paragraph('<b>Erstellt am</b>', small_style),
            Paragraph(escape(str(erstellt_datum)), normal_style)
        ])
    
    if sichtbarkeiten:
        sichtbarkeiten_text = ', '.join([s['Bezeichnung'] for s in sichtbarkeiten])
        thema_info_data.append([
            Paragraph('<b>Sichtbar für</b>', small_style),
            Paragraph(escape(sichtbarkeiten_text), normal_style)
        ])
    
    thema_table = Table(thema_info_data, colWidths=[4.5*cm, 12.5*cm])
    thema_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), bg_light),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, border_color),
    ]))
    
    story.append(thema_table)
    story.append(Spacer(1, 1.2*cm))
    
    # Bemerkungen-Sektion (schlanker)
    story.append(Paragraph("Bemerkungen", section_style))
    
    if bemerkungen:
        for idx, bemerkung in enumerate(bemerkungen, 1):
            # Container für jede Bemerkung (Header + Text zusammenhalten)
            bemerkung_container = []
            
            datum_text = bemerkung['Datum'][:16] if len(bemerkung['Datum']) >= 16 else bemerkung['Datum']
            
            # Schlanke Bemerkung: Name, Datum, Tätigkeit in einer Zeile
            header_parts = [f'<b>{escape(bemerkung["Vorname"])} {escape(bemerkung["Nachname"])}</b>']
            header_parts.append(f'<font color="#64748b">{datum_text}</font>')
            if bemerkung['Taetigkeit']:
                header_parts.append(f'<font color="#64748b">• {escape(bemerkung["Taetigkeit"])}</font>')
            
            bemerkung_header = ' '.join(header_parts)
            
            # Header zur Bemerkung hinzufügen
            bemerkung_container.append(Paragraph(bemerkung_header, ParagraphStyle(
                'BemerkungHeader',
                parent=normal_style,
                fontSize=9,
                textColor=text_secondary,
                spaceAfter=4,
                fontName='Helvetica'
            )))
            
            # Bemerkungstext zur Bemerkung hinzufügen
            bemerkung_container.append(Paragraph(escape(bemerkung['Bemerkung']).replace('\n', '<br/>'), 
                                  ParagraphStyle('BemerkungText', parent=normal_style, 
                                                fontSize=10, textColor=text_primary, 
                                                leading=14, spaceAfter=8)))
            
            # Trennstrich zwischen Bemerkungen (außer bei der letzten)
            if idx < len(bemerkungen):
                bemerkung_container.append(Table([['']], colWidths=[17*cm], style=TableStyle([
                    ('LINEBELOW', (0, 0), (0, 0), 0.5, border_color),
                    ('TOPPADDING', (0, 0), (0, 0), 0),
                    ('BOTTOMPADDING', (0, 0), (0, 0), 0),
                ])))
                bemerkung_container.append(Spacer(1, 0.4*cm))
            
            # Bemerkung als zusammengehöriges Element hinzufügen
            story.append(KeepTogether(bemerkung_container))
    else:
        story.append(Paragraph("<i>Keine Bemerkungen vorhanden.</i>", 
                              ParagraphStyle('EmptyMsg', parent=normal_style, 
                                            fontSize=10, textColor=text_secondary)))
    
    # Ersatzteile-Sektion (zusammenhalten mit KeepTogether)
    story.append(Spacer(1, 1.2*cm))
    
    # Container für Überschrift und Tabelle zusammen
    ersatzteile_section = []
    ersatzteile_section.append(Paragraph("Verwendete Ersatzteile", section_style))
    
    if ersatzteile:
        # Tabelle für Ersatzteile erstellen
        ersatzteile_data = []
        
        # Header-Zeile
        ersatzteile_data.append([
            Paragraph('<b>Datum</b>', small_style),
            Paragraph('<b>Ersatzteil</b>', small_style),
            Paragraph('<b>Typ</b>', small_style),
            Paragraph('<b>Menge</b>', small_style),
            Paragraph('<b>Verwendet von</b>', small_style)
        ])
        
        # Datenzeilen
        for ersatzteil in ersatzteile:
            datum_text = ersatzteil['Buchungsdatum'][:10] if len(ersatzteil['Buchungsdatum']) >= 10 else ersatzteil['Buchungsdatum']
            
            # Ersatzteil-Name mit Bestellnummer
            ersatzteil_name = escape(str(ersatzteil['ErsatzteilBezeichnung']))
            if ersatzteil['Bestellnummer']:
                ersatzteil_name = f"{ersatzteil_name}<br/><font size='8' color='#64748b'>{escape(str(ersatzteil['Bestellnummer']))}</font>"
            
            # Typ-Text
            typ_text = escape(str(ersatzteil['Typ']))
            if typ_text == 'Ausgang':
                typ_text = f'<font color="#dc2626">{typ_text}</font>'
            elif typ_text == 'Eingang':
                typ_text = f'<font color="#16a34a">{typ_text}</font>'
            elif typ_text == 'Inventur':
                typ_text = f'<font color="#2563eb">{typ_text}</font>'
            
            # Menge mit Einheit
            menge_text = f"{ersatzteil['Menge']}"
            if ersatzteil['Einheit']:
                menge_text += f" {escape(str(ersatzteil['Einheit']))}"
            
            # Verwendet von
            verwendet_von = escape(str(ersatzteil['VerwendetVon'])) if ersatzteil['VerwendetVon'] else '-'
            
            ersatzteile_data.append([
                Paragraph(datum_text, normal_style),
                Paragraph(ersatzteil_name, normal_style),
                Paragraph(typ_text, normal_style),
                Paragraph(menge_text, normal_style),
                Paragraph(verwendet_von, normal_style)
            ])
        
        ersatzteile_table = Table(ersatzteile_data, colWidths=[3*cm, 6*cm, 2.5*cm, 2.5*cm, 3*cm])
        ersatzteile_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), bg_light),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),  # Menge rechtsbündig
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, border_color),
            ('LINEBELOW', (0, 0), (-1, 0), 1, border_color),
        ]))
        
        ersatzteile_section.append(ersatzteile_table)
    else:
        ersatzteile_section.append(Paragraph("<i>Keine Ersatzteile verwendet.</i>", 
                              ParagraphStyle('EmptyMsg', parent=normal_style, 
                                            fontSize=10, textColor=text_secondary)))
    
    # Überschrift und Tabelle zusammenhalten
    story.append(KeepTogether(ersatzteile_section))
    
    # Footer mit Datum
    story.append(Spacer(1, 1.5*cm))
    export_datum = datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")
    footer_text = f'<font color="#94a3b8" size="8">Exportiert am {export_datum}</font>'
    story.append(Paragraph(footer_text, ParagraphStyle(
        'ModernFooter',
        parent=normal_style,
        fontSize=8,
        textColor=colors.HexColor('#94a3b8'),
        alignment=TA_RIGHT
    )))
    
    # PDF generieren
    doc.build(story)
    buffer.seek(0)
    
    # PDF als Download senden
    filename = f"Thema_{thema_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename={filename}'
        }
    )


@schichtbuch_bp.route('/suche')
@login_required
def suche_thema():
    """Suche nach Thema-ID"""
    mitarbeiter_id = session.get('user_id')
    thema_id_str = request.args.get('thema_id', '').strip()
    
    if thema_id_str:
        try:
            thema_id = int(thema_id_str)
            
            with get_db_connection() as conn:
                # Berechtigte Abteilungen ermitteln
                sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
                
                # Prüfen ob Thema existiert und Berechtigung besteht
                query = '''
                    SELECT t.ID
                    FROM SchichtbuchThema t
                    WHERE t.Gelöscht = 0 AND t.ID = ?
                '''
                params = [thema_id]
                
                # Sichtbarkeitsfilter: Nur Themen anzeigen, für die Berechtigung besteht
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    query += f''' AND EXISTS (
                        SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                        WHERE sv.ThemaID = t.ID 
                        AND sv.AbteilungID IN ({placeholders})
                    )'''
                    params.extend(sichtbare_abteilungen)
                else:
                    # Keine Berechtigung
                    flash('Thema nicht gefunden oder Sie haben keine Berechtigung.', 'danger')
                    return render_template('thema_suche.html')
                
                thema = conn.execute(query, params).fetchone()
                
                if thema:
                    return redirect(url_for('schichtbuch.thema_detail', thema_id=thema['ID']))
                else:
                    flash('Thema nicht gefunden oder Sie haben keine Berechtigung.', 'danger')
        except ValueError:
            flash('Bitte geben Sie eine gültige Thema-ID ein.', 'danger')
        except Exception as e:
            flash(f'Fehler bei der Suche: {str(e)}', 'danger')
    
    return render_template('thema_suche.html')
