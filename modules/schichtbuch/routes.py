"""
Schichtbuch Routes - Themenliste, Details, Bemerkungen
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime
from . import schichtbuch_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter


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
        
        # Abteilungsfilter hinzufügen
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f' AND (t.ErstellerAbteilungID IN ({placeholders}) OR t.ErstellerAbteilungID IS NULL)'
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
        
        # Abteilungsfilter hinzufügen
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f' AND (t.ErstellerAbteilungID IN ({placeholders}) OR t.ErstellerAbteilungID IS NULL)'
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

    return render_template(
        'sbThemaNeu.html',
        gewerke=gewerke,
        taetigkeiten=taetigkeiten,
        status=status,
        bereiche=bereiche
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
    if request.method == 'POST':
        mitarbeiter_id = session.get('user_id')
        if not mitarbeiter_id:
            flash('Bitte zuerst anmelden.', 'warning')
            return redirect(url_for('auth.login'))

        bemerkung = request.form['bemerkung']
        neuer_status = request.form.get('status')
        taetigkeit_id = request.form.get("taetigkeit_id")
        datum = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db_connection() as conn:
            # Bemerkung speichern
            conn.execute('''
                INSERT INTO SchichtbuchBemerkungen (ThemaID, MitarbeiterID, Datum, TaetigkeitID, Bemerkung)
                VALUES (?, ?, ?, ?, ?)
            ''', (thema_id, mitarbeiter_id, datum, taetigkeit_id, bemerkung))

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

    previous_page = request.args.get('next') or url_for('index')

    return render_template(
        'sbThemaDetail.html',
        thema=thema,
        bemerkungen=bemerkungen,
        mitarbeiter=mitarbeiter,
        status_liste=status_liste,
        taetigkeiten=taetigkeiten,
        previous_page=previous_page
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

