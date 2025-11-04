"""
Admin Routes - Stammdaten-Verwaltung
Mitarbeiter, Abteilungen, Bereiche, Gewerke, Tätigkeiten, Status
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash
import sqlite3
from . import admin_bp
from utils import get_db_connection, admin_required


def ajax_response(message, success=True, status_code=None):
    """Hilfsfunktion für AJAX/Standard-Responses"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if status_code is None:
            status_code = 200 if success else 400
        return jsonify({'success': success, 'message': message}), status_code
    else:
        flash(message, 'success' if success else 'danger')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin Dashboard - Übersicht aller Stammdaten"""
    with get_db_connection() as conn:
        mitarbeiter = conn.execute('''
            SELECT m.ID, m.Personalnummer, m.Vorname, m.Nachname, m.Aktiv,
                   a.Bezeichnung AS PrimaerAbteilung, m.PrimaerAbteilungID
            FROM Mitarbeiter m
            LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID
            ORDER BY m.Nachname, m.Vorname
        ''').fetchall()
        
        # Zusätzliche Abteilungen für jeden Mitarbeiter laden
        mitarbeiter_abteilungen = {}
        for m in mitarbeiter:
            zusaetzliche = conn.execute('''
                SELECT AbteilungID
                FROM MitarbeiterAbteilung
                WHERE MitarbeiterID = ?
            ''', (m['ID'],)).fetchall()
            mitarbeiter_abteilungen[m['ID']] = [row['AbteilungID'] for row in zusaetzliche]
        
        # Abteilungen hierarchisch laden
        abteilungen = conn.execute('''
            SELECT a.ID, a.Bezeichnung, a.ParentAbteilungID, a.Aktiv, a.Sortierung,
                   p.Bezeichnung AS ParentBezeichnung
            FROM Abteilung a
            LEFT JOIN Abteilung p ON a.ParentAbteilungID = p.ID
            ORDER BY COALESCE(p.Bezeichnung, a.Bezeichnung), a.Bezeichnung
        ''').fetchall()
        
        bereiche = conn.execute('SELECT ID, Bezeichnung FROM Bereich ORDER BY Bezeichnung').fetchall()
        gewerke = conn.execute('''
            SELECT G.ID, G.Bezeichnung, B.Bezeichnung AS Bereich, G.BereichID
            FROM Gewerke G
            JOIN Bereich B ON G.BereichID = B.ID
            ORDER BY B.Bezeichnung, G.Bezeichnung
        ''').fetchall()
        taetigkeiten = conn.execute('SELECT ID, Bezeichnung, Sortierung FROM Taetigkeit ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        status = conn.execute('SELECT ID, Bezeichnung, Farbe, Sortierung FROM Status ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()

    return render_template('admin.html',
                           mitarbeiter=mitarbeiter,
                           mitarbeiter_abteilungen=mitarbeiter_abteilungen,
                           abteilungen=abteilungen,
                           bereiche=bereiche,
                           gewerke=gewerke,
                           taetigkeiten=taetigkeiten,
                           status=status)


# ========== Mitarbeiter-Verwaltung ==========

@admin_bp.route('/mitarbeiter/add', methods=['POST'])
@admin_required
def mitarbeiter_add():
    """Mitarbeiter anlegen"""
    personalnummer = request.form.get('personalnummer')
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    
    if not personalnummer or not vorname or not nachname:
        return ajax_response('Bitte Personalnummer, Vorname und Nachname ausfüllen.', success=False)
    
    try:
        with get_db_connection() as conn:
            if passwort:
                conn.execute('INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort) VALUES (?, ?, ?, ?, ?)',
                             (personalnummer, vorname, nachname, aktiv, generate_password_hash(passwort)))
            else:
                conn.execute('INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv) VALUES (?, ?, ?, ?)',
                             (personalnummer, vorname, nachname, aktiv))
            conn.commit()
        return ajax_response('Mitarbeiter erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler beim Anlegen: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/update/<int:mid>', methods=['POST'])
@admin_required
def mitarbeiter_update(mid):
    """Mitarbeiter aktualisieren"""
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Mitarbeiter SET Vorname = ?, Nachname = ?, Aktiv = ? WHERE ID = ?', (vorname, nachname, aktiv, mid))
            if passwort:
                conn.execute('UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?', (generate_password_hash(passwort), mid))
            conn.commit()
        return ajax_response('Mitarbeiter aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/mitarbeiter/deactivate/<int:mid>', methods=['POST'])
@admin_required
def mitarbeiter_deactivate(mid):
    """Mitarbeiter deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Mitarbeiter SET Aktiv = 0 WHERE ID = ?', (mid,))
            conn.commit()
        return ajax_response('Mitarbeiter deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Abteilungs-Verwaltung ==========

@admin_bp.route('/abteilung/add', methods=['POST'])
@admin_required
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
            
            # Neue zusätzliche Abteilungen hinzufügen
            for abt_id in zusaetzliche_ids:
                if abt_id and abt_id != '' and abt_id != str(primaer_abteilung_id):
                    try:
                        conn.execute('INSERT INTO MitarbeiterAbteilung (MitarbeiterID, AbteilungID) VALUES (?, ?)', 
                                     (mid, abt_id))
                    except sqlite3.IntegrityError:
                        # Duplikat - ignorieren
                        pass
            
            conn.commit()
        return ajax_response('Mitarbeiter-Abteilungen aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


# ========== Bereich-Verwaltung ==========

@admin_bp.route('/bereich/add', methods=['POST'])
@admin_required
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
def status_delete(sid):
    """Status deaktivieren"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Status SET Aktiv = 0 WHERE ID = ?', (sid,))
            conn.commit()
        return ajax_response('Status deaktiviert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)

