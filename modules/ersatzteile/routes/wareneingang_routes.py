"""
Wareneingang Routes - Wareneingang-Verwaltung
"""

from flask import render_template, request, redirect, url_for, session, flash, send_from_directory, current_app
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from .. import ersatzteile_bp
from utils import get_db_connection, login_required, permission_required, get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.file_handling import save_uploaded_file, validate_file_extension, create_upload_folder
from ..services import get_dateien_fuer_bereich, speichere_datei, get_datei_typ_aus_dateiname


def get_lieferschein_dateien(bestellung_id):
    """Hilfsfunktion: Scannt Ordner nach Lieferschein-Dateien (PDF, JPEG, JPG, PNG) für eine Bestellung"""
    lieferschein_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Lieferscheine', str(bestellung_id))
    dateien = []
    
    if os.path.exists(lieferschein_folder):
        try:
            for filename in os.listdir(lieferschein_folder):
                file_ext = filename.lower()
                if file_ext.endswith(('.pdf', '.jpeg', '.jpg', '.png')):
                    filepath = os.path.join(lieferschein_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellwesen/Lieferscheine/{bestellung_id}/{filename}'
                        # Dateityp bestimmen
                        if file_ext.endswith('.pdf'):
                            file_type = 'pdf'
                        elif file_ext.endswith(('.jpeg', '.jpg', '.png')):
                            file_type = 'image'
                        else:
                            file_type = 'unknown'
                        
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'type': file_type,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Lieferschein-Ordners: {e}")
    
    return dateien


@ersatzteile_bp.route('/wareneingang')
@login_required
@permission_required('artikel_buchen')
def wareneingang():
    """Übersichtsseite für Wareneingang - Liste aller bestellten Bestellungen"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Sichtbare Abteilungen für den Mitarbeiter ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Nur Bestellungen mit Status "Bestellt" oder "Teilweise erhalten"
        query = '''
            SELECT 
                b.ID,
                b.Status,
                b.BestelltAm,
                l.Name AS LieferantName,
                abt.Bezeichnung AS Abteilung
            FROM Bestellung b
            LEFT JOIN Lieferant l ON b.LieferantID = l.ID
            LEFT JOIN Abteilung abt ON b.ErstellerAbteilungID = abt.ID
            WHERE b.Status IN ('Bestellt', 'Teilweise erhalten')
        '''
        params = []
        
        # Sichtbarkeitsfilter
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f'''
                AND EXISTS (
                    SELECT 1 FROM BestellungSichtbarkeit bs
                    WHERE bs.BestellungID = b.ID 
                    AND bs.AbteilungID IN ({placeholders})
                )
            '''
            params.extend(sichtbare_abteilungen)
        elif not is_admin:
            query += ' AND 1=0'
        
        query += ' ORDER BY b.BestelltAm DESC'
        
        bestellungen = conn.execute(query, params).fetchall()
    
    return render_template('wareneingang.html', bestellungen=bestellungen)


@ersatzteile_bp.route('/wareneingang/bestellung/<int:bestellung_id>', methods=['GET', 'POST'])
@login_required
@permission_required('artikel_buchen')
def wareneingang_bestellung(bestellung_id):
    """Wareneingang für eine spezifische Bestellung"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Bestellung laden
        bestellung = conn.execute('''
            SELECT b.*, l.Name AS LieferantName
            FROM Bestellung b
            LEFT JOIN Lieferant l ON b.LieferantID = l.ID
            WHERE b.ID = ? AND b.Status IN ('Bestellt', 'Teilweise erhalten')
        ''', (bestellung_id,)).fetchone()
        
        if not bestellung:
            flash('Bestellung nicht gefunden oder nicht für Wareneingang verfügbar.', 'danger')
            return redirect(url_for('ersatzteile.wareneingang'))
        
        # Positionen laden
        positionen = conn.execute('''
            SELECT 
                p.*,
                e.ID AS ErsatzteilID,
                COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
                COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
                e.Einheit
            FROM BestellungPosition p
            LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
            WHERE p.BestellungID = ?
            ORDER BY p.ID
        ''', (bestellung_id,)).fetchall()
        
        if not positionen:
            flash('Bestellung hat keine Positionen.', 'danger')
            return redirect(url_for('ersatzteile.wareneingang'))
    
    if request.method == 'POST':
        # Erhaltene Mengen pro Position
        position_ids = request.form.getlist('position_id[]')
        erhaltene_mengen = request.form.getlist('erhaltene_menge[]')
        
        try:
            with get_db_connection() as conn:
                alle_vollstaendig = True
                mindestens_eine_teilweise = False
                
                for i, pos_id in enumerate(position_ids):
                    if i >= len(erhaltene_mengen):
                        continue
                    
                    try:
                        pos_id_int = int(pos_id)
                        erhaltene_menge = int(erhaltene_mengen[i]) if erhaltene_mengen[i] else 0
                        
                        # Position laden
                        pos = conn.execute('SELECT Menge, ErhalteneMenge, ErsatzteilID FROM BestellungPosition WHERE ID = ?', (pos_id_int,)).fetchone()
                        if not pos:
                            continue
                        
                        # Neue ErhalteneMenge berechnen (erhöhen, nicht überschreiben)
                        neue_erhaltene_menge = pos['ErhalteneMenge'] + erhaltene_menge
                        
                        # Validierung: ErhalteneMenge darf nicht größer als Menge sein
                        if neue_erhaltene_menge > pos['Menge']:
                            flash(f'Position {pos_id}: Erhaltene Menge ({neue_erhaltene_menge}) darf nicht größer als bestellte Menge ({pos["Menge"]}) sein.', 'danger')
                            return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=bestellung_id))
                        
                        # ErhalteneMenge aktualisieren
                        conn.execute('''
                            UPDATE BestellungPosition 
                            SET ErhalteneMenge = ?
                            WHERE ID = ?
                        ''', (neue_erhaltene_menge, pos_id_int))
                        
                        # Lagerbuchung erstellen (wenn ErsatzteilID vorhanden)
                        if pos['ErsatzteilID'] and erhaltene_menge > 0:
                            # Aktueller Bestand ermitteln
                            ersatzteil = conn.execute('SELECT AktuellerBestand FROM Ersatzteil WHERE ID = ?', (pos['ErsatzteilID'],)).fetchone()
                            neuer_bestand = (ersatzteil['AktuellerBestand'] if ersatzteil else 0) + erhaltene_menge
                            
                            # Bestand aktualisieren
                            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, pos['ErsatzteilID']))
                            
                            # Lagerbuchung erstellen
                            conn.execute('''
                                INSERT INTO Lagerbuchung (ErsatzteilID, Typ, Menge, VerwendetVonID, Buchungsdatum, Grund, BestellungID)
                                VALUES (?, 'Eingang', ?, ?, datetime('now'), ?, ?)
                            ''', (pos['ErsatzteilID'], erhaltene_menge, mitarbeiter_id, f'Wareneingang Bestellung #{bestellung_id}', bestellung_id))
                        
                        # Status prüfen
                        if neue_erhaltene_menge < pos['Menge']:
                            alle_vollstaendig = False
                            mindestens_eine_teilweise = True
                        elif neue_erhaltene_menge == pos['Menge']:
                            # Position vollständig, aber prüfe ob alle vollständig sind
                            pass
                    
                    except (ValueError, IndexError):
                        continue
                
                # Status der Bestellung aktualisieren
                if alle_vollstaendig:
                    # Alle Positionen vollständig erhalten
                    conn.execute('UPDATE Bestellung SET Status = ? WHERE ID = ?', ('Erhalten', bestellung_id))
                    # Status auf "Erledigt" setzen
                    conn.execute('UPDATE Bestellung SET Status = ? WHERE ID = ?', ('Erledigt', bestellung_id))
                elif mindestens_eine_teilweise:
                    # Mindestens eine Position teilweise erhalten
                    conn.execute('UPDATE Bestellung SET Status = ? WHERE ID = ?', ('Teilweise erhalten', bestellung_id))
                
                conn.commit()
                
                # Benachrichtigungen erstellen
                try:
                    from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_wareneingang
                    erstelle_benachrichtigung_fuer_wareneingang(bestellung_id, conn)
                except Exception as e:
                    print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
                
                flash('Wareneingang erfolgreich gebucht.', 'success')
                return redirect(url_for('ersatzteile.wareneingang'))
                
        except Exception as e:
            flash(f'Fehler beim Buchen: {str(e)}', 'danger')
            print(f"Wareneingang Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    # Lieferschein-Dateien aus Datei-Tabelle laden
    with get_db_connection() as conn:
        lieferscheine_db = get_dateien_fuer_bereich('Lieferschein', bestellung_id, conn)
        
        # In das Format konvertieren, das das Template erwartet (konsistent mit anderen Bereichen)
        lieferscheine = []
        for d in lieferscheine_db:
            # Dateigröße aus Dateisystem ermitteln
            filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], d['Dateipfad'].replace('/', os.sep))
            file_size = 0
            modified = None
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                modified = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            # Beide Formate unterstützen: Dictionary mit allen Feldern
            datei_dict = dict(d)  # Alle Datenbankfelder kopieren (ID, Dateiname, Dateipfad, Beschreibung, Typ, ErstelltAm, ErstelltVon, etc.)
            datei_dict.update({
                'name': d['Dateiname'],
                'path': d['Dateipfad'],
                'size': file_size,
                'modified': modified,
                'id': d['ID'],
                'beschreibung': d['Beschreibung'] or ''
            })
            lieferscheine.append(datei_dict)
        
        is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    return render_template('wareneingang_bestellung.html', bestellung=bestellung, positionen=positionen, lieferscheine=lieferscheine, is_admin=is_admin)


@ersatzteile_bp.route('/lieferschein/<int:bestellung_id>/upload', methods=['POST'])
@login_required
@permission_required('artikel_buchen')
def lieferschein_upload(bestellung_id):
    """Lieferschein-Upload für Wareneingang (PDF, JPEG, JPG, PNG)"""
    mitarbeiter_id = session.get('user_id')
    beschreibung = request.form.get('beschreibung', '').strip()
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=bestellung_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=bestellung_id))
    
    # Dateiendung prüfen
    if not validate_file_extension(file.filename, {'pdf', 'jpg', 'jpeg', 'png'}):
        flash('Nur PDF-, JPEG-, JPG- oder PNG-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=bestellung_id))
    
    try:
        with get_db_connection() as conn:
            # Ordner erstellen
            lieferschein_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Lieferscheine', str(bestellung_id))
            create_upload_folder(lieferschein_folder)
            
            # Datei speichern mit Timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            original_filename = file.filename
            file.filename = timestamp + secure_filename(original_filename)
            
            success_upload, filename, error_message = save_uploaded_file(
                file,
                lieferschein_folder,
                allowed_extensions={'pdf', 'jpg', 'jpeg', 'png'}
            )
            
            if not success_upload or error_message:
                flash(f'Fehler beim Hochladen: {error_message}', 'danger')
                return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=bestellung_id))
            
            # Datenbankeintrag in Datei-Tabelle
            relative_path = f'Bestellwesen/Lieferscheine/{bestellung_id}/{filename}'
            speichere_datei(
                bereich_typ='Lieferschein',
                bereich_id=bestellung_id,
                dateiname=original_filename,
                dateipfad=relative_path,
                beschreibung=beschreibung,
                typ=get_datei_typ_aus_dateiname(original_filename),
                mitarbeiter_id=mitarbeiter_id,
                conn=conn
            )
            
            flash('Lieferschein erfolgreich hochgeladen.', 'success')
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Lieferschein-Upload Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/lieferschein/<path:filepath>')
@login_required
def lieferschein_anzeigen(filepath):
    """Lieferschein-Datei anzeigen/herunterladen (PDF oder Bild) - für alle angemeldeten Benutzer"""
    mitarbeiter_id = session.get('user_id')
    
    # Normalisiere den Pfad: Backslashes zu Forward-Slashes (für Windows-Kompatibilität)
    filepath = filepath.replace('\\', '/')
    
    # Sicherheitsprüfung: Dateipfad muss mit Bestellwesen/Lieferscheine beginnen
    if not filepath.startswith('Bestellwesen/Lieferscheine/'):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.wareneingang'))
    
    try:
        # Vollständigen Pfad erstellen
        full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath)
        
        # Sicherheitsprüfung: Datei muss existieren und im erlaubten Ordner sein
        if not os.path.exists(full_path) or not os.path.abspath(full_path).startswith(os.path.abspath(current_app.config['UPLOAD_BASE_FOLDER'])):
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.wareneingang'))
        
        # Dateityp bestimmen
        file_ext = os.path.splitext(full_path)[1].lower()
        if file_ext == '.pdf':
            mimetype = 'application/pdf'
        elif file_ext in ['.jpeg', '.jpg']:
            mimetype = 'image/jpeg'
        elif file_ext == '.png':
            mimetype = 'image/png'
        else:
            mimetype = 'application/octet-stream'
        
        return send_from_directory(
            os.path.dirname(full_path),
            os.path.basename(full_path),
            mimetype=mimetype,
            as_attachment=False  # Im Browser anzeigen
        )
    except Exception as e:
        flash(f'Fehler beim Laden der Datei: {str(e)}', 'danger')
        print(f"Lieferschein anzeigen Fehler: {e}")
        return redirect(url_for('ersatzteile.wareneingang'))
