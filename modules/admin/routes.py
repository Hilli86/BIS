"""
Admin Routes - Stammdaten-Verwaltung
Mitarbeiter, Abteilungen, Bereiche, Gewerke, Tätigkeiten, Status
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash
import sqlite3
from . import admin_bp
from utils import get_db_connection, admin_required
from utils.zebra_client import send_zpl_to_printer, build_test_label
from utils.helpers import row_to_dict


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
            SELECT m.ID, m.Personalnummer, m.Vorname, m.Nachname, m.Email, m.Handynummer, m.Aktiv,
                   a.Bezeichnung AS PrimaerAbteilung, m.PrimaerAbteilungID
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
        lieferanten = conn.execute('SELECT ID, Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Aktiv FROM Lieferant WHERE Gelöscht = 0 ORDER BY Name').fetchall()
        kostenstellen = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Kostenstelle ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lagerorte = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Lagerort ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        lagerplaetze = conn.execute('SELECT ID, Bezeichnung, Beschreibung, Aktiv, Sortierung FROM Lagerplatz ORDER BY Sortierung ASC, Bezeichnung ASC').fetchall()
        
        # Firmendaten laden (nur erste Zeile, sollte nur eine geben)
        firmendaten_row = conn.execute('SELECT * FROM Firmendaten LIMIT 1').fetchone()
        firmendaten = row_to_dict(firmendaten_row) if firmendaten_row else None
        
        # Berechtigungen laden
        berechtigungen = conn.execute('SELECT ID, Schluessel, Bezeichnung, Beschreibung, Aktiv FROM Berechtigung ORDER BY Bezeichnung').fetchall()

        # Zebra-Drucker und Etikettenformate laden
        zebra_printers = conn.execute('''
            SELECT id, name, ip_address, description, active
            FROM zebra_printers
            ORDER BY name
        ''').fetchall()
        label_formats = conn.execute('''
            SELECT id, name, description, width_mm, height_mm, orientation, zpl_header
            FROM label_formats
            ORDER BY name
        ''').fetchall()
        
        # Etiketten laden
        etiketten = conn.execute('''
            SELECT id, bezeichnung, drucker_id, etikettformat_id, druckbefehle
            FROM Etikett
            ORDER BY bezeichnung
        ''').fetchall()

    return render_template('admin.html',
                           mitarbeiter=mitarbeiter,
                           mitarbeiter_abteilungen=mitarbeiter_abteilungen,
                           mitarbeiter_berechtigungen=mitarbeiter_berechtigungen,
                           abteilungen=abteilungen,
                           bereiche=bereiche,
                           gewerke=gewerke,
                           taetigkeiten=taetigkeiten,
                           status=status,
                           ersatzteil_kategorien=ersatzteil_kategorien,
                           lieferanten=lieferanten,
                           kostenstellen=kostenstellen,
                           lagerorte=lagerorte,
                           lagerplaetze=lagerplaetze,
                           firmendaten=firmendaten,
                           berechtigungen=berechtigungen,
                           zebra_printers=zebra_printers,
                           label_formats=label_formats,
                           etiketten=etiketten)


# ========== Zebra-Drucker Verwaltung ==========

@admin_bp.route('/zebra/printers', methods=['POST'])
@admin_required
def zebra_printer_save():
    """
    Zebra-Drucker anlegen oder aktualisieren.
    Wenn eine ID übergeben wird, wird aktualisiert, sonst neu angelegt.
    """
    printer_id = request.form.get('id')
    name = request.form.get('name', '').strip()
    ip_address = request.form.get('ip_address', '').strip()
    description = request.form.get('description', '').strip() or None
    active = 1 if request.form.get('active') == 'on' else 0

    if not name or not ip_address:
        return ajax_response('Bitte Name und IP-Adresse ausfüllen.', success=False)

    try:
        with get_db_connection() as conn:
            if printer_id:
                conn.execute('''
                    UPDATE zebra_printers
                    SET name = ?, ip_address = ?, description = ?, active = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (name, ip_address, description, active, printer_id))
            else:
                conn.execute('''
                    INSERT INTO zebra_printers (name, ip_address, description, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (name, ip_address, description, active))
            conn.commit()
        return ajax_response('Zebra-Drucker gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern des Druckers: {str(e)}', success=False, status_code=500)


@admin_bp.route('/zebra/printers/toggle/<int:pid>', methods=['POST'])
@admin_required
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


# ========== Etikettenformate Verwaltung ==========

@admin_bp.route('/zebra/labels', methods=['POST'])
@admin_required
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
    orientation = request.form.get('orientation', 'portrait').strip() or 'portrait'
    zpl_header = request.form.get('zpl_header', '').strip()

    if not name or not width_mm or not height_mm or not zpl_header:
        return ajax_response('Bitte Name, Breite, Höhe und ZPL-Header ausfüllen.', success=False)

    try:
        with get_db_connection() as conn:
            if label_id:
                conn.execute('''
                    UPDATE label_formats
                    SET name = ?, description = ?, width_mm = ?, height_mm = ?, orientation = ?, zpl_header = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (name, description, width_mm, height_mm, orientation, zpl_header, label_id))
            else:
                conn.execute('''
                    INSERT INTO label_formats (name, description, width_mm, height_mm, orientation, zpl_header, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (name, description, width_mm, height_mm, orientation, zpl_header))
            conn.commit()
        return ajax_response('Etikettenformat gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern des Etikettenformats: {str(e)}', success=False, status_code=500)


# ========== Zebra-Testdruck ==========

@admin_bp.route('/zebra/test', methods=['GET', 'POST'])
@admin_required
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

            # Kompletten ZPL-Befehl in der Konsole ausgeben (für Debugging)
            print("===== ZEBRA TEST ZPL =====")
            print(zpl)
            print("===== END ZEBRA TEST ZPL =====")

            try:
                send_zpl_to_printer(printer['ip_address'], zpl)
                flash(f"Testetikett '{label['name']}' an Drucker '{printer['name']}' gesendet.", 'success')
            except Exception as e:
                flash(f"Fehler beim Senden an den Drucker: {e}", 'danger')

            return redirect(url_for('admin.zebra_test'))

    return render_template('admin_zebra_test.html', printers=printers, labels=labels)


# ========== Etiketten-Verwaltung ==========

@admin_bp.route('/zebra/etiketten/save', methods=['POST'])
@admin_required
def zebra_etikett_save():
    """
    Etikett anlegen oder aktualisieren.
    Wenn eine ID übergeben wird, wird aktualisiert, sonst neu angelegt.
    """
    etikett_id = request.form.get('id')
    bezeichnung = request.form.get('bezeichnung', '').strip()
    drucker_id = request.form.get('drucker_id', type=int)
    etikettformat_id = request.form.get('etikettformat_id', type=int)
    druckbefehle = request.form.get('druckbefehle', '').strip()

    if not bezeichnung or not drucker_id or not etikettformat_id or not druckbefehle:
        return ajax_response('Bitte alle Felder ausfüllen.', success=False)

    try:
        with get_db_connection() as conn:
            # Prüfe ob Drucker und Format existieren
            printer = conn.execute('SELECT id FROM zebra_printers WHERE id = ?', (drucker_id,)).fetchone()
            label_format = conn.execute('SELECT id FROM label_formats WHERE id = ?', (etikettformat_id,)).fetchone()
            
            if not printer:
                return ajax_response('Ausgewählter Drucker nicht gefunden.', success=False)
            if not label_format:
                return ajax_response('Ausgewähltes Etikettenformat nicht gefunden.', success=False)
            
            if etikett_id:
                conn.execute('''
                    UPDATE Etikett
                    SET bezeichnung = ?, drucker_id = ?, etikettformat_id = ?, druckbefehle = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                ''', (bezeichnung, drucker_id, etikettformat_id, druckbefehle, etikett_id))
            else:
                conn.execute('''
                    INSERT INTO Etikett (bezeichnung, drucker_id, etikettformat_id, druckbefehle, created_at, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                ''', (bezeichnung, drucker_id, etikettformat_id, druckbefehle))
            conn.commit()
        return ajax_response('Etikett gespeichert.')
    except Exception as e:
        return ajax_response(f'Fehler beim Speichern des Etiketts: {str(e)}', success=False, status_code=500)


# ========== Mitarbeiter-Verwaltung ==========

@admin_bp.route('/mitarbeiter/add', methods=['POST'])
@admin_required
def mitarbeiter_add():
    """Mitarbeiter anlegen"""
    personalnummer = request.form.get('personalnummer')
    vorname = request.form.get('vorname')
    nachname = request.form.get('nachname')
    email = request.form.get('email', '').strip() or None
    handynummer = request.form.get('handynummer', '').strip() or None
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    
    if not personalnummer or not vorname or not nachname:
        return ajax_response('Bitte Personalnummer, Vorname und Nachname ausfüllen.', success=False)
    
    try:
        with get_db_connection() as conn:
            if passwort:
                conn.execute('INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Email, Handynummer, Aktiv, Passwort) VALUES (?, ?, ?, ?, ?, ?, ?)',
                             (personalnummer, vorname, nachname, email, handynummer, aktiv, generate_password_hash(passwort)))
            else:
                conn.execute('INSERT INTO Mitarbeiter (Personalnummer, Vorname, Nachname, Email, Handynummer, Aktiv) VALUES (?, ?, ?, ?, ?, ?)',
                             (personalnummer, vorname, nachname, email, handynummer, aktiv))
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
    email = request.form.get('email', '').strip() or None
    handynummer = request.form.get('handynummer', '').strip() or None
    aktiv = 1 if request.form.get('aktiv') == 'on' else 0
    passwort = request.form.get('passwort')
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Mitarbeiter SET Vorname = ?, Nachname = ?, Email = ?, Handynummer = ?, Aktiv = ? WHERE ID = ?', 
                        (vorname, nachname, email, handynummer, aktiv, mid))
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


@admin_bp.route('/benachrichtigungen/cleanup', methods=['POST'])
@admin_required
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
            conn.execute(
                'INSERT INTO Berechtigung (Schluessel, Bezeichnung, Beschreibung, Aktiv) VALUES (?, ?, ?, ?)',
                (schluessel, bezeichnung, beschreibung, aktiv)
            )
            conn.commit()
        return ajax_response('Berechtigung erfolgreich angelegt.')
    except sqlite3.IntegrityError:
        return ajax_response('Eine Berechtigung mit diesem Schlüssel existiert bereits.', success=False, status_code=400)
    except Exception as e:
        return ajax_response(f'Fehler beim Anlegen: {str(e)}', success=False, status_code=500)


@admin_bp.route('/berechtigung/update/<int:bid>', methods=['POST'])
@admin_required
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
            
            # Neue Berechtigungen hinzufügen
            for berechtigung_id in berechtigung_ids:
                # Prüfen ob Berechtigung existiert
                berechtigung = conn.execute('SELECT ID FROM Berechtigung WHERE ID = ?', (berechtigung_id,)).fetchone()
                if berechtigung:
                    try:
                        conn.execute(
                            'INSERT INTO MitarbeiterBerechtigung (MitarbeiterID, BerechtigungID) VALUES (?, ?)',
                            (mid, berechtigung_id)
                        )
                    except sqlite3.IntegrityError:
                        # Duplikat - ignorieren
                        pass
            
            conn.commit()
        
        return ajax_response('Berechtigungen erfolgreich aktualisiert.')
    except Exception as e:
        return ajax_response(f'Fehler: {str(e)}', success=False, status_code=500)
