"""
Admin Routes - Stammdaten-Verwaltung
Mitarbeiter, Abteilungen, Bereiche, Gewerke, Tätigkeiten, Status
"""

from flask import render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
import sqlite3
from . import admin_bp
from utils import get_db_connection, login_required


@admin_bp.route('/')
@login_required
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
                           abteilungen=abteilungen,
                           bereiche=bereiche,
                           gewerke=gewerke,
                           taetigkeiten=taetigkeiten,
                           status=status)


# ========== Mitarbeiter-Verwaltung ==========

@admin_bp.route('/mitarbeiter/add', methods=['POST'])
@login_required
def mitarbeiter_add():
    """Mitarbeiter anlegen"""
    personalnummer = request.form.get('personalnummer')
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    if not personalnummer or not vorname or not nachname:
        flash('Bitte Personalnummer, Vorname und Nachname ausfüllen.', 'danger')
        return redirect(url_for('admin.dashboard'))
    with get_db_connection() as conn:
        if passwort:
            conn.execute('INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv, Passwort) VALUES (?, ?, ?, ?, ?)',
                         (personalnummer, vorname, nachname, aktiv, generate_password_hash(passwort)))
        else:
            conn.execute('INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Aktiv) VALUES (?, ?, ?, ?)',
                         (personalnummer, vorname, nachname, aktiv))
        conn.commit()
    flash('Mitarbeiter angelegt.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/mitarbeiter/update/<int:mid>', methods=['POST'])
@login_required
def mitarbeiter_update(mid):
    """Mitarbeiter aktualisieren"""
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    with get_db_connection() as conn:
        conn.execute('UPDATE Mitarbeiter SET Vorname = ?, Nachname = ?, Aktiv = ? WHERE ID = ?', (vorname, nachname, aktiv, mid))
        if passwort:
            conn.execute('UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?', (generate_password_hash(passwort), mid))
        conn.commit()
    flash('Mitarbeiter aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/mitarbeiter/deactivate/<int:mid>', methods=['POST'])
@login_required
def mitarbeiter_deactivate(mid):
    """Mitarbeiter deaktivieren"""
    with get_db_connection() as conn:
        conn.execute('UPDATE Mitarbeiter SET Aktiv = 0 WHERE ID = ?', (mid,))
        conn.commit()
    flash('Mitarbeiter deaktiviert.', 'info')
    return redirect(url_for('admin.dashboard'))


# ========== Abteilungs-Verwaltung ==========

@admin_bp.route('/abteilung/add', methods=['POST'])
@login_required
def abteilung_add():
    """Abteilung anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    parent_id = request.form.get('parent_abteilung_id')
    sortierung = request.form.get('sortierung', type=int) or 0
    
    if parent_id == '' or parent_id is None:
        parent_id = None
    
    if not bezeichnung:
        flash('Bezeichnung erforderlich.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    with get_db_connection() as conn:
        conn.execute('INSERT INTO Abteilung (Bezeichnung, ParentAbteilungID, Aktiv, Sortierung) VALUES (?, ?, 1, ?)', 
                     (bezeichnung, parent_id, sortierung))
        conn.commit()
    flash('Abteilung angelegt.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/abteilung/update/<int:aid>', methods=['POST'])
@login_required
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
        flash('Eine Abteilung kann nicht ihre eigene Überabteilung sein.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    with get_db_connection() as conn:
        conn.execute('UPDATE Abteilung SET Bezeichnung = ?, ParentAbteilungID = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', 
                     (bezeichnung, parent_id, sortierung, aktiv, aid))
        conn.commit()
    flash('Abteilung aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/abteilung/delete/<int:aid>', methods=['POST'])
@login_required
def abteilung_delete(aid):
    """Abteilung deaktivieren"""
    with get_db_connection() as conn:
        conn.execute('UPDATE Abteilung SET Aktiv = 0 WHERE ID = ?', (aid,))
        conn.commit()
    flash('Abteilung deaktiviert.', 'info')
    return redirect(url_for('admin.dashboard'))


# ========== Mitarbeiter-Abteilungen Verwaltung ==========

@admin_bp.route('/mitarbeiter/<int:mid>/abteilungen', methods=['POST'])
@login_required
def mitarbeiter_abteilungen(mid):
    """Mitarbeiter-Abteilungen zuweisen"""
    primaer_abteilung_id = request.form.get('primaer_abteilung_id')
    zusaetzliche_ids = request.form.getlist('zusaetzliche_abteilungen')
    
    # Leere Strings in None konvertieren
    if primaer_abteilung_id == '' or primaer_abteilung_id is None:
        primaer_abteilung_id = None
    
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
    flash('Mitarbeiter-Abteilungen aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


# ========== Bereich-Verwaltung ==========

@admin_bp.route('/bereich/add', methods=['POST'])
@login_required
def bereich_add():
    """Bereich anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    if not bezeichnung:
        flash('Bezeichnung erforderlich.', 'danger')
        return redirect(url_for('admin.dashboard'))
    with get_db_connection() as conn:
        conn.execute('INSERT INTO Bereich (Bezeichnung, Aktiv) VALUES (?, 1)', (bezeichnung,))
        conn.commit()
    flash('Bereich angelegt.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/bereich/update/<int:bid>', methods=['POST'])
@login_required
def bereich_update(bid):
    """Bereich aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    with get_db_connection() as conn:
        conn.execute('UPDATE Bereich SET Bezeichnung = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, aktiv, bid))
        conn.commit()
    flash('Bereich aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/bereich/delete/<int:bid>', methods=['POST'])
@login_required
def bereich_delete(bid):
    """Bereich deaktivieren"""
    with get_db_connection() as conn:
        conn.execute('UPDATE Bereich SET Aktiv = 0 WHERE ID = ?', (bid,))
        conn.commit()
    flash('Bereich deaktiviert.', 'info')
    return redirect(url_for('admin.dashboard'))


# ========== Gewerk-Verwaltung ==========

@admin_bp.route('/gewerk/add', methods=['POST'])
@login_required
def gewerk_add():
    """Gewerk anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    bereich_id = request.form.get('bereich_id')
    if not bezeichnung or not bereich_id:
        flash('Bezeichnung und Bereich erforderlich.', 'danger')
        return redirect(url_for('admin.dashboard'))
    with get_db_connection() as conn:
        conn.execute('INSERT INTO Gewerke (Bezeichnung, BereichID, Aktiv) VALUES (?, ?, 1)', (bezeichnung, bereich_id))
        conn.commit()
    flash('Gewerk angelegt.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/gewerk/update/<int:gid>', methods=['POST'])
@login_required
def gewerk_update(gid):
    """Gewerk aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    bereich_id = request.form.get('bereich_id')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    with get_db_connection() as conn:
        conn.execute('UPDATE Gewerke SET Bezeichnung = ?, BereichID = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, bereich_id, aktiv, gid))
        conn.commit()
    flash('Gewerk aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/gewerk/delete/<int:gid>', methods=['POST'])
@login_required
def gewerk_delete(gid):
    """Gewerk deaktivieren"""
    with get_db_connection() as conn:
        conn.execute('UPDATE Gewerke SET Aktiv = 0 WHERE ID = ?', (gid,))
        conn.commit()
    flash('Gewerk deaktiviert.', 'info')
    return redirect(url_for('admin.dashboard'))


# ========== Tätigkeit-Verwaltung ==========

@admin_bp.route('/taetigkeit/add', methods=['POST'])
@login_required
def taetigkeit_add():
    """Tätigkeit anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    sortierung = request.form.get('sortierung', type=int)
    if not bezeichnung:
        flash('Bezeichnung erforderlich.', 'danger')
        return redirect(url_for('admin.dashboard'))
    with get_db_connection() as conn:
        conn.execute('INSERT INTO Taetigkeit (Bezeichnung, Sortierung, Aktiv) VALUES (?, ?, 1)', (bezeichnung, sortierung))
        conn.commit()
    flash('Tätigkeit angelegt.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/taetigkeit/update/<int:tid>', methods=['POST'])
@login_required
def taetigkeit_update(tid):
    """Tätigkeit aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    sortierung = request.form.get('sortierung', type=int)
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    with get_db_connection() as conn:
        conn.execute('UPDATE Taetigkeit SET Bezeichnung = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, sortierung, aktiv, tid))
        conn.commit()
    flash('Tätigkeit aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/taetigkeit/delete/<int:tid>', methods=['POST'])
@login_required
def taetigkeit_delete(tid):
    """Tätigkeit deaktivieren"""
    with get_db_connection() as conn:
        conn.execute('UPDATE Taetigkeit SET Aktiv = 0 WHERE ID = ?', (tid,))
        conn.commit()
    flash('Tätigkeit deaktiviert.', 'info')
    return redirect(url_for('admin.dashboard'))


# ========== Status-Verwaltung ==========

@admin_bp.route('/status/add', methods=['POST'])
@login_required
def status_add():
    """Status anlegen"""
    bezeichnung = request.form.get('bezeichnung')
    farbe = request.form.get('farbe')
    sortierung = request.form.get('sortierung', type=int)
    if not bezeichnung:
        flash('Bezeichnung erforderlich.', 'danger')
        return redirect(url_for('admin.dashboard'))
    with get_db_connection() as conn:
        conn.execute('INSERT INTO Status (Bezeichnung, Farbe, Sortierung, Aktiv) VALUES (?, ?, ?, 1)', (bezeichnung, farbe, sortierung))
        conn.commit()
    flash('Status angelegt.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/status/update/<int:sid>', methods=['POST'])
@login_required
def status_update(sid):
    """Status aktualisieren"""
    bezeichnung = request.form.get('bezeichnung')
    farbe = request.form.get('farbe')
    sortierung = request.form.get('sortierung', type=int)
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    with get_db_connection() as conn:
        conn.execute('UPDATE Status SET Bezeichnung = ?, Farbe = ?, Sortierung = ?, Aktiv = ? WHERE ID = ?', (bezeichnung, farbe, sortierung, aktiv, sid))
        conn.commit()
    flash('Status aktualisiert.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/status/delete/<int:sid>', methods=['POST'])
@login_required
def status_delete(sid):
    """Status deaktivieren"""
    with get_db_connection() as conn:
        conn.execute('UPDATE Status SET Aktiv = 0 WHERE ID = ?', (sid,))
        conn.commit()
    flash('Status deaktiviert.', 'info')
    return redirect(url_for('admin.dashboard'))

