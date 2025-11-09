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
        lieferanten = conn.execute('SELECT ID, Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Aktiv FROM Lieferant WHERE Gelöscht = 0 ORDER BY Name').fetchall()
        kostenstellen = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Kostenstelle ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lagerorte = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Lagerort ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lagerplaetze = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Lagerplatz ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()

    return render_template('admin.html',
                           mitarbeiter=mitarbeiter,
                           mitarbeiter_abteilungen=mitarbeiter_abteilungen,
                           abteilungen=abteilungen,
                           bereiche=bereiche,
                           gewerke=gewerke,
                           taetigkeiten=taetigkeiten,
                           status=status,
                           ersatzteil_kategorien=ersatzteil_kategorien,
                           lieferanten=lieferanten,
                           kostenstellen=kostenstellen,
                           lagerorte=lagerorte,
                           lagerplaetze=lagerplaetze)


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


@admin_bp.route('/mitarbeiter/reset-password/<int:mid>', methods=['POST'])
@admin_required
def mitarbeiter_reset_password(mid):
    """Passwort des Mitarbeiters auf Vorname zurücksetzen"""
    try:
        with get_db_connection() as conn:
            # Vorname des Mitarbeiters abrufen
            mitarbeiter = conn.execute(
                'SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?',
                (mid,)
            ).fetchone()
            
            if not mitarbeiter:
                return ajax_response('Mitarbeiter nicht gefunden.', success=False, status_code=404)
            
            vorname = mitarbeiter['Vorname']
            nachname = mitarbeiter['Nachname']
            
            if not vorname:
                return ajax_response('Mitarbeiter hat keinen Vornamen.', success=False)
            
            # Passwort auf Vorname setzen (gehasht)
            neues_passwort_hash = generate_password_hash(vorname)
            conn.execute(
                'UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?',
                (neues_passwort_hash, mid)
            )
            conn.commit()
            
        return ajax_response(f'Passwort für {vorname} {nachname} wurde auf "{vorname}" zurückgesetzt.')
    except Exception as e:
        return ajax_response(f'Fehler beim Zurücksetzen: {str(e)}', success=False, status_code=500)


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


# ========== ErsatzteilKategorie-Verwaltung ==========

@admin_bp.route('/ersatzteil-kategorie/add', methods=['POST'])
@admin_required
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
def lieferant_add():
    """Lieferant anlegen"""
    name = request.form.get('name')
    kontaktperson = request.form.get('kontaktperson', '')
    telefon = request.form.get('telefon', '')
    email = request.form.get('email', '')
    strasse = request.form.get('strasse', '')
    plz = request.form.get('plz', '')
    ort = request.form.get('ort', '')
    
    if not name:
        return ajax_response('Name erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT INTO Lieferant (Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Aktiv) VALUES (?, ?, ?, ?, ?, ?, ?, 1)', 
                         (name, kontaktperson, telefon, email, strasse, plz, ort))
            conn.commit()
        return ajax_response('Lieferant erfolgreich angelegt.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lieferant/update/<int:lid>', methods=['POST'])
@admin_required
def lieferant_update(lid):
    """Lieferant aktualisieren"""
    name = request.form.get('name')
    kontaktperson = request.form.get('kontaktperson', '')
    telefon = request.form.get('telefon', '')
    email = request.form.get('email', '')
    strasse = request.form.get('strasse', '')
    plz = request.form.get('plz', '')
    ort = request.form.get('ort', '')
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    
    if not name:
        return ajax_response('Name erforderlich.', success=False)
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lieferant SET Name = ?, Kontaktperson = ?, Telefon = ?, Email = ?, Strasse = ?, PLZ = ?, Ort = ?, Aktiv = ? WHERE ID = ?', 
                         (name, kontaktperson, telefon, email, strasse, plz, ort, aktiv, lid))
            conn.commit()
        return ajax_response('Lieferant aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)


@admin_bp.route('/lieferant/delete/<int:lid>', methods=['POST'])
@admin_required
def lieferant_delete(lid):
    """Lieferant soft-delete"""
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Lieferant SET Gelöscht = 1 WHERE ID = ?', (lid,))
            conn.commit()
        return ajax_response('Lieferant gelöscht.')
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


@admin_bp.route('/database/repair', methods=['POST'])
@admin_required
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
