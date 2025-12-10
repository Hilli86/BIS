"""
Bestellung Routes - Bestellungs-Verwaltung
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, current_app, make_response, send_from_directory
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from .. import ersatzteile_bp
from utils import get_db_connection, login_required, permission_required, get_sichtbare_abteilungen_fuer_mitarbeiter, ist_admin
from utils.file_handling import save_uploaded_file, validate_file_extension, create_upload_folder
from ..services import generate_bestellung_pdf, get_dateien_fuer_bereich


def get_bestellung_dateien(bestellung_id):
    """Hilfsfunktion: Scannt Ordner nach PDF-Dateien für eine Bestellung"""
    bestellung_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], 'Bestellungen', str(bestellung_id))
    dateien = []
    
    if os.path.exists(bestellung_folder):
        try:
            for filename in os.listdir(bestellung_folder):
                if filename.lower().endswith('.pdf'):
                    filepath = os.path.join(bestellung_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellungen/{bestellung_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Bestellung-Ordners: {e}")
    
    return dateien


def get_auftragsbestätigung_dateien(bestellung_id):
    """Hilfsfunktion: Scannt Ordner nach Auftragsbestätigungs-Dateien (PDF, JPEG, JPG, PNG) für eine Bestellung"""
    auftragsbestätigung_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Auftragsbestätigungen', str(bestellung_id))
    dateien = []
    
    if os.path.exists(auftragsbestätigung_folder):
        try:
            for filename in os.listdir(auftragsbestätigung_folder):
                file_ext = filename.lower()
                if file_ext.endswith(('.pdf', '.jpeg', '.jpg', '.png')):
                    filepath = os.path.join(auftragsbestätigung_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellwesen/Auftragsbestätigungen/{bestellung_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Auftragsbestätigung-Ordners: {e}")
    
    return dateien


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


@ersatzteile_bp.route('/bestellungen')
@login_required
def bestellung_liste():
    """Liste aller Bestellungen mit Filter"""
    mitarbeiter_id = session.get('user_id')
    
    # Filterparameter - mehrere Status möglich
    status_filter_list = request.args.getlist('status')
    lieferant_filter = request.args.get('lieferant')
    abteilung_filter = request.args.get('abteilung')
    
    with get_db_connection() as conn:
        # Sichtbare Abteilungen für den Mitarbeiter ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Basis-Query
        query = '''
            SELECT 
                b.ID,
                b.Status,
                b.ErstelltAm,
                b.FreigegebenAm,
                b.BestelltAm,
                l.Name AS LieferantName,
                m1.Vorname || ' ' || m1.Nachname AS ErstelltVon,
                m2.Vorname || ' ' || m2.Nachname AS FreigegebenVon,
                m3.Vorname || ' ' || m3.Nachname AS BestelltVon,
                abt.Bezeichnung AS Abteilung,
                COALESCE(SUM(bp.Menge * COALESCE(bp.Preis, 0)), 0) AS Gesamtbetrag,
                COUNT(bp.ID) AS PositionenAnzahl
            FROM Bestellung b
            LEFT JOIN Lieferant l ON b.LieferantID = l.ID
            LEFT JOIN Mitarbeiter m1 ON b.ErstelltVonID = m1.ID
            LEFT JOIN Mitarbeiter m2 ON b.FreigegebenVonID = m2.ID
            LEFT JOIN Mitarbeiter m3 ON b.BestelltVonID = m3.ID
            LEFT JOIN Abteilung abt ON b.ErstellerAbteilungID = abt.ID
            LEFT JOIN BestellungPosition bp ON b.ID = bp.BestellungID
            WHERE b.Gelöscht = 0
        '''
        params = []
        
        # Sichtbarkeitsfilter: Nur Bestellungen mit Sichtbarkeit für sichtbare Abteilungen
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
            # Keine Berechtigung - keine Bestellungen anzeigen
            query += ' AND 1=0'
        
        # Status-Filter (mehrere Status möglich)
        if status_filter_list:
            placeholders = ','.join(['?'] * len(status_filter_list))
            query += f' AND b.Status IN ({placeholders})'
            params.extend(status_filter_list)
        else:
            # Standard: Erledigt und Storniert ausschließen
            query += " AND b.Status != 'Erledigt' AND b.Status != 'Storniert'"
        
        # Lieferant-Filter
        if lieferant_filter:
            query += ' AND b.LieferantID = ?'
            params.append(lieferant_filter)
        
        # Abteilung-Filter
        if abteilung_filter:
            query += ' AND b.ErstellerAbteilungID = ?'
            params.append(abteilung_filter)
        
        query += ' GROUP BY b.ID ORDER BY b.ErstelltAm DESC'
        
        bestellungen = conn.execute(query, params).fetchall()
        
        # Lieferanten für Filter laden
        lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
        
        # Abteilungen für Filter laden
        abteilungen = conn.execute('SELECT ID, Bezeichnung FROM Abteilung ORDER BY Sortierung, Bezeichnung').fetchall()
    
    return render_template(
        'bestellung_liste.html',
        bestellungen=bestellungen,
        status_filter_list=status_filter_list,
        lieferant_filter=lieferant_filter,
        abteilung_filter=abteilung_filter,
        lieferanten=lieferanten,
        abteilungen=abteilungen
    )


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/loeschen', methods=['POST'])
@login_required
def bestellung_loeschen(bestellung_id):
    """Bestellung löschen (nur wenn Status 'Erstellt' oder 'Zur Freigabe')"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    has_bestellungen_erstellen = 'bestellungen_erstellen' in session.get('user_berechtigungen', [])
    
    if not (is_admin or has_bestellungen_erstellen):
        flash('Sie haben keine Berechtigung, Bestellungen zu löschen.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_liste'))
    
    try:
        with get_db_connection() as conn:
            # Bestellung laden und prüfen
            bestellung = conn.execute('SELECT Status, ErstelltVonID, ErstellerAbteilungID FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
            
            if not bestellung:
                flash('Bestellung nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
            
            # Berechtigungsprüfung: Nur Bestellungen mit Sichtbarkeit für sichtbare Abteilungen
            if not is_admin:
                sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
                sichtbarkeiten = conn.execute('SELECT AbteilungID FROM BestellungSichtbarkeit WHERE BestellungID = ?', (bestellung_id,)).fetchall()
                sichtbarkeits_ids = [s['AbteilungID'] for s in sichtbarkeiten]
                
                if not any(abt in sichtbare_abteilungen for abt in sichtbarkeits_ids):
                    flash('Sie haben keine Berechtigung, diese Bestellung zu löschen.', 'danger')
                    return redirect(url_for('ersatzteile.bestellung_liste'))
            
            # Nur Bestellungen mit Status 'Erstellt', 'Zur Freigabe' oder 'Freigegeben' können gelöscht werden
            if bestellung['Status'] not in ['Erstellt', 'Zur Freigabe', 'Freigegeben']:
                flash(f'Bestellungen mit Status "{bestellung["Status"]}" können nicht gelöscht werden. Nur Bestellungen mit Status "Erstellt", "Zur Freigabe" oder "Freigegeben" können gelöscht werden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
            
            # Bestellung als gelöscht markieren (soft delete)
            conn.execute('UPDATE Bestellung SET Gelöscht = 1 WHERE ID = ?', (bestellung_id,))
            conn.commit()
            
        flash('Bestellung erfolgreich gelöscht.', 'success')
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Fehler beim Löschen der Bestellung: {error_details}")
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
    
    return redirect(url_for('ersatzteile.bestellung_liste'))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>')
@login_required
def bestellung_detail(bestellung_id):
    """Detailansicht einer Bestellung"""
    mitarbeiter_id = session.get('user_id')
    
    # Filter-Parameter aus URL übernehmen (für Zurück-Button)
    status_filter_list = request.args.getlist('status')
    lieferant_filter = request.args.get('lieferant', '')
    abteilung_filter = request.args.get('abteilung', '')
    
    with get_db_connection() as conn:
        # Bestellung laden
        bestellung = conn.execute('''
            SELECT 
                b.*,
                l.Name AS LieferantName,
                l.Kontaktperson AS LieferantKontakt,
                l.Telefon AS LieferantTelefon,
                l.Email AS LieferantEmail,
                m1.Vorname || ' ' || m1.Nachname AS ErstelltVon,
                m2.Vorname || ' ' || m2.Nachname AS FreigegebenVon,
                m3.Vorname || ' ' || m3.Nachname AS BestelltVon,
                abt.Bezeichnung AS Abteilung
            FROM Bestellung b
            LEFT JOIN Lieferant l ON b.LieferantID = l.ID
            LEFT JOIN Mitarbeiter m1 ON b.ErstelltVonID = m1.ID
            LEFT JOIN Mitarbeiter m2 ON b.FreigegebenVonID = m2.ID
            LEFT JOIN Mitarbeiter m3 ON b.BestelltVonID = m3.ID
            LEFT JOIN Abteilung abt ON b.ErstellerAbteilungID = abt.ID
            WHERE b.ID = ? AND b.Gelöscht = 0
        ''', (bestellung_id,)).fetchone()
        
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        # Berechtigungsprüfung: Nur Bestellungen mit Sichtbarkeit für sichtbare Abteilungen
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        if not is_admin:
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            sichtbarkeiten = conn.execute('SELECT AbteilungID FROM BestellungSichtbarkeit WHERE BestellungID = ?', (bestellung_id,)).fetchall()
            sichtbarkeits_ids = [s['AbteilungID'] for s in sichtbarkeiten]
            
            if not any(abt in sichtbare_abteilungen for abt in sichtbarkeits_ids):
                flash('Sie haben keine Berechtigung, diese Bestellung zu sehen.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
        
        # Positionen laden
        positionen = conn.execute('''
            SELECT 
                p.*,
                e.ID AS ErsatzteilID,
                COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
                COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
                COALESCE(p.Einheit, e.Einheit, 'Stück') AS Einheit,
                COALESCE(p.Link, e.Link) AS Link
            FROM BestellungPosition p
            LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
            WHERE p.BestellungID = ?
            ORDER BY p.ID
        ''', (bestellung_id,)).fetchall()
        
        # Gesamtsumme berechnen
        gesamtbetrag = 0
        waehrung = 'EUR'
        for pos in positionen:
            preis = pos['Preis'] or 0
            menge = pos['Menge'] or 0
            gesamtbetrag += preis * menge
            if pos['Waehrung']:
                waehrung = pos['Waehrung']
        
        # Dateien aus Datei-Tabelle laden
        alle_dateien = get_dateien_fuer_bereich('Bestellung', bestellung_id, conn)
        
        # Lieferscheine separat laden (eigener BereichTyp)
        lieferscheine_db = get_dateien_fuer_bereich('Lieferschein', bestellung_id, conn)
        
        # Dateien nach Typ filtern (Pfad-basiert für Rückwärtskompatibilität)
        dateien = [d for d in alle_dateien if 'Bestellungen' in d['Dateipfad']]
        auftragsbestätigungen = []
        lieferscheine = []
        if bestellung['Status'] in ['Bestellt', 'Teilweise erhalten', 'Erhalten', 'Erledigt']:
            auftragsbestätigungen = [d for d in alle_dateien if 'Auftragsbestätigungen' in d['Dateipfad']]
            # Lieferscheine aus eigenem BereichTyp verwenden
            lieferscheine = list(lieferscheine_db)
        
        # Berechtigungen prüfen (Admin hat alle Rechte)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        kann_freigeben = is_admin or 'bestellungen_freigeben' in session.get('user_berechtigungen', [])
        kann_buchen = is_admin or 'artikel_buchen' in session.get('user_berechtigungen', [])
        
        # Prüfen, ob Benutzer der Ersteller ist
        ist_ersteller = bestellung['ErstelltVonID'] == mitarbeiter_id if bestellung['ErstelltVonID'] else False
        kann_freigabebemerkung_bearbeiten = ist_ersteller and bestellung['Status'] in ['Erstellt', 'Zur Freigabe']
    
    return render_template(
        'bestellung_detail.html',
        bestellung=bestellung,
        positionen=positionen,
        dateien=dateien,
        auftragsbestätigungen=auftragsbestätigungen,
        lieferscheine=lieferscheine,
        kann_freigeben=kann_freigeben,
        kann_buchen=kann_buchen,
        gesamtbetrag=gesamtbetrag,
        waehrung=waehrung,
        kann_freigabebemerkung_bearbeiten=kann_freigabebemerkung_bearbeiten,
        is_admin=is_admin,
        status_filter_list=status_filter_list,
        lieferant_filter=lieferant_filter,
        abteilung_filter=abteilung_filter
    )


@ersatzteile_bp.route('/bestellungen/neu', methods=['GET', 'POST'])
@login_required
@permission_required('bestellungen_erstellen')
def bestellung_neu():
    """Neue Bestellung manuell erstellen"""
    mitarbeiter_id = session.get('user_id')
    
    if request.method == 'POST':
        lieferant_id = request.form.get('lieferant_id', type=int)
        bemerkung = request.form.get('bemerkung', '').strip()
        sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')
        
        # Ersatzteil-Positionen aus Formular
        ersatzteil_ids = request.form.getlist('ersatzteil_id[]')
        mengen = request.form.getlist('menge[]')
        einheiten = request.form.getlist('einheit[]')
        bestellnummern = request.form.getlist('bestellnummer[]')
        bezeichnungen = request.form.getlist('bezeichnung[]')
        preise = request.form.getlist('preis[]')
        waehrungen = request.form.getlist('waehrung[]')
        positionen_bemerkungen = request.form.getlist('position_bemerkung[]')
        links = request.form.getlist('link[]')
        
        if not lieferant_id:
            flash('Bitte wählen Sie einen Lieferanten aus.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_neu'))
        
        # Mindestens eine Position muss vorhanden sein
        has_positions = False
        for i in range(max(len(ersatzteil_ids), len(bestellnummern))):
            ersatzteil_id_str = ersatzteil_ids[i] if i < len(ersatzteil_ids) else ''
            bestellnummer = bestellnummern[i].strip() if i < len(bestellnummern) and bestellnummern[i] else ''
            if (ersatzteil_id_str and ersatzteil_id_str.strip()) or bestellnummer:
                has_positions = True
                break
        
        if not has_positions:
            flash('Bitte fügen Sie mindestens eine Position hinzu.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_neu'))
        
        try:
            with get_db_connection() as conn:
                # Primärabteilung des Mitarbeiters ermitteln
                mitarbeiter = conn.execute(
                    'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
                    (mitarbeiter_id,)
                ).fetchone()
                abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
                
                # Bestellung erstellen
                cursor = conn.execute('''
                    INSERT INTO Bestellung (LieferantID, ErstelltVonID, ErstellerAbteilungID, Status, Bemerkung, ErstelltAm)
                    VALUES (?, ?, ?, 'Erstellt', ?, datetime('now', 'localtime'))
                ''', (lieferant_id, mitarbeiter_id, abteilung_id, bemerkung))
                bestellung_id = cursor.lastrowid
                
                # Positionen hinzufügen
                for i, ersatzteil_id_str in enumerate(ersatzteil_ids):
                    if not ersatzteil_id_str and (i >= len(bestellnummern) or not bestellnummern[i] or not bestellnummern[i].strip()):
                        continue
                    
                    try:
                        ersatzteil_id = int(ersatzteil_id_str) if ersatzteil_id_str and ersatzteil_id_str.strip() else None
                        menge = int(mengen[i]) if i < len(mengen) and mengen[i] else 1
                        einheit = einheiten[i].strip() if i < len(einheiten) and einheiten[i] else None
                        bestellnummer = bestellnummern[i].strip() if i < len(bestellnummern) and bestellnummern[i] else None
                        bezeichnung = bezeichnungen[i].strip() if i < len(bezeichnungen) and bezeichnungen[i] else None
                        preis_str = preise[i].strip() if i < len(preise) and preise[i] else None
                        preis = float(preis_str) if preis_str else None
                        waehrung = waehrungen[i].strip() if i < len(waehrungen) and waehrungen[i] else 'EUR'
                        pos_bemerkung = positionen_bemerkungen[i].strip() if i < len(positionen_bemerkungen) and positionen_bemerkungen[i] else None
                        link = links[i].strip() if i < len(links) and links[i] else None
                        
                        # Wenn ErsatzteilID vorhanden, aber Bestellnummer/Bezeichnung/Einheit fehlen, aus Ersatzteil laden
                        if ersatzteil_id and (not bestellnummer or not bezeichnung or not einheit):
                            ersatzteil = conn.execute('SELECT Bestellnummer, Bezeichnung, Einheit, Link FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                            if ersatzteil:
                                if not bestellnummer:
                                    bestellnummer = ersatzteil['Bestellnummer']
                                if not bezeichnung:
                                    bezeichnung = ersatzteil['Bezeichnung']
                                if not einheit:
                                    einheit = ersatzteil['Einheit'] if ersatzteil['Einheit'] else 'Stück'
                                # Link nur aus Ersatzteil übernehmen, wenn kein Link im Formular vorhanden
                                if not link and 'Link' in ersatzteil.keys() and ersatzteil['Link']:
                                    link = ersatzteil['Link']
                        elif ersatzteil_id:
                            # Auch wenn alle anderen Felder vorhanden sind, Link aus Ersatzteil laden, wenn kein Link im Formular
                            if not link:
                                ersatzteil = conn.execute('SELECT Link FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                                if ersatzteil and 'Link' in ersatzteil.keys() and ersatzteil['Link']:
                                    link = ersatzteil['Link']
                        
                        if not einheit:
                            einheit = 'Stück'
                        
                        conn.execute('''
                            INSERT INTO BestellungPosition (BestellungID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Bemerkung, Preis, Waehrung, Link)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (bestellung_id, ersatzteil_id, menge, einheit, bestellnummer, bezeichnung, pos_bemerkung, preis, waehrung, link))
                    except (ValueError, IndexError):
                        continue
                
                # Sichtbarkeiten setzen (optional - wenn keine ausgewählt, wird Primärabteilung verwendet)
                if sichtbare_abteilungen:
                    for abt_id in sichtbare_abteilungen:
                        try:
                            conn.execute('''
                                INSERT INTO BestellungSichtbarkeit (BestellungID, AbteilungID)
                                VALUES (?, ?)
                            ''', (bestellung_id, abt_id))
                        except:
                            pass
                elif abteilung_id:
                    # Wenn keine Abteilungen ausgewählt, Primärabteilung verwenden
                    try:
                        conn.execute('''
                            INSERT INTO BestellungSichtbarkeit (BestellungID, AbteilungID)
                            VALUES (?, ?)
                        ''', (bestellung_id, abteilung_id))
                    except:
                        pass
                
                conn.commit()
                
                # Benachrichtigungen erstellen
                try:
                    from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
                    erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'neue_bestellung', conn)
                except Exception as e:
                    print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
                
                flash('Bestellung erfolgreich erstellt.', 'success')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
                
        except Exception as e:
            flash(f'Fehler beim Erstellen: {str(e)}', 'danger')
            print(f"Bestellung neu Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    # GET: Formular anzeigen
    with get_db_connection() as conn:
        lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
        
        # Auswählbare Abteilungen für Sichtbarkeit
        from utils import get_auswaehlbare_abteilungen_fuer_neues_thema
        auswaehlbare_abteilungen = get_auswaehlbare_abteilungen_fuer_neues_thema(mitarbeiter_id, conn)
    
    return render_template(
        'bestellung_neu.html',
        lieferanten=lieferanten,
        auswaehlbare_abteilungen=auswaehlbare_abteilungen
    )


@ersatzteile_bp.route('/bestellungen/aus-angebot/<int:angebotsanfrage_id>', methods=['GET', 'POST'])
@login_required
@permission_required('bestellungen_erstellen')
def bestellung_aus_angebot(angebotsanfrage_id):
    """Bestellung aus Angebot erstellen"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Angebotsanfrage laden
        anfrage = conn.execute('''
            SELECT a.*, l.Name AS LieferantName
            FROM Angebotsanfrage a
            LEFT JOIN Lieferant l ON a.LieferantID = l.ID
            WHERE a.ID = ? AND a.Status = 'Angebot erhalten'
        ''', (angebotsanfrage_id,)).fetchone()
        
        if not anfrage:
            flash('Angebotsanfrage nicht gefunden oder Status nicht "Angebot erhalten".', 'danger')
            return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
        
        # Positionen laden
        positionen = conn.execute('''
            SELECT 
                p.*,
                e.ID AS ErsatzteilID,
                COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
                COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
                COALESCE(p.Einheit, e.Einheit, 'Stück') AS Einheit,
                COALESCE(p.Angebotspreis, e.Preis) AS Preis,
                COALESCE(p.Angebotswaehrung, e.Waehrung, 'EUR') AS Waehrung,
                COALESCE(p.Link, e.Link) AS Link
            FROM AngebotsanfragePosition p
            LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
            WHERE p.AngebotsanfrageID = ?
            ORDER BY p.ID
        ''', (angebotsanfrage_id,)).fetchall()
        
        if not positionen:
            flash('Angebotsanfrage hat keine Positionen.', 'danger')
            return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    
    if request.method == 'POST':
        bemerkung = request.form.get('bemerkung', '').strip()
        sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')
        ausgewaehlte_positionen = request.form.getlist('position_id')
        
        if not ausgewaehlte_positionen:
            flash('Bitte wählen Sie mindestens eine Position aus.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_aus_angebot', angebotsanfrage_id=angebotsanfrage_id))
        
        try:
            with get_db_connection() as conn:
                # Primärabteilung des Mitarbeiters ermitteln
                mitarbeiter = conn.execute(
                    'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
                    (mitarbeiter_id,)
                ).fetchone()
                abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
                
                # Bestellung erstellen
                cursor = conn.execute('''
                    INSERT INTO Bestellung (AngebotsanfrageID, LieferantID, ErstelltVonID, ErstellerAbteilungID, Status, Bemerkung, ErstelltAm)
                    VALUES (?, ?, ?, ?, 'Erstellt', ?, datetime('now', 'localtime'))
                ''', (angebotsanfrage_id, anfrage['LieferantID'], mitarbeiter_id, abteilung_id, bemerkung))
                bestellung_id = cursor.lastrowid
                
                # Ausgewählte Positionen hinzufügen
                for pos_id in ausgewaehlte_positionen:
                    pos = next((p for p in positionen if str(p['ID']) == pos_id), None)
                    if not pos:
                        continue
                    
                    einheit = pos['Einheit'] if 'Einheit' in pos.keys() and pos['Einheit'] else 'Stück'
                    link = pos['Link'] if 'Link' in pos.keys() else None
                    conn.execute('''
                        INSERT INTO BestellungPosition (BestellungID, AngebotsanfragePositionID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Bemerkung, Preis, Waehrung, Link)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (bestellung_id, pos['ID'], pos['ErsatzteilID'], pos['Menge'], einheit, pos['Bestellnummer'], pos['Bezeichnung'], pos['Bemerkung'], pos['Preis'], pos['Waehrung'], link))
                
                # Sichtbarkeiten setzen (optional - wenn keine ausgewählt, wird Primärabteilung verwendet)
                if sichtbare_abteilungen:
                    for abt_id in sichtbare_abteilungen:
                        try:
                            conn.execute('''
                                INSERT INTO BestellungSichtbarkeit (BestellungID, AbteilungID)
                                VALUES (?, ?)
                            ''', (bestellung_id, abt_id))
                        except:
                            pass
                elif abteilung_id:
                    # Wenn keine Abteilungen ausgewählt, Primärabteilung verwenden
                    try:
                        conn.execute('''
                            INSERT INTO BestellungSichtbarkeit (BestellungID, AbteilungID)
                            VALUES (?, ?)
                        ''', (bestellung_id, abteilung_id))
                    except:
                        pass
                
                # Angebotsanfrage als abgeschlossen markieren
                conn.execute('''
                    UPDATE Angebotsanfrage
                    SET Status = 'Abgeschlossen'
                    WHERE ID = ?
                ''', (angebotsanfrage_id,))
                
                conn.commit()
                
                # Benachrichtigungen erstellen
                try:
                    from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
                    erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'neue_bestellung', conn)
                except Exception as e:
                    print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
                
                flash('Bestellung erfolgreich aus Angebot erstellt.', 'success')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
                
        except Exception as e:
            flash(f'Fehler beim Erstellen: {str(e)}', 'danger')
            print(f"Bestellung aus Angebot Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    # GET: Formular anzeigen
    with get_db_connection() as conn:
        from utils import get_auswaehlbare_abteilungen_fuer_neues_thema
        auswaehlbare_abteilungen = get_auswaehlbare_abteilungen_fuer_neues_thema(mitarbeiter_id, conn)
    
    return render_template(
        'bestellung_aus_angebot.html',
        anfrage=anfrage,
        positionen=positionen,
        auswaehlbare_abteilungen=auswaehlbare_abteilungen
    )


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/zur-freigabe', methods=['POST'])
@login_required
def bestellung_zur_freigabe(bestellung_id):
    """Bestellung zur Freigabe markieren"""
    freigabe_bemerkung = request.form.get('freigabe_bemerkung', '').strip()
    
    with get_db_connection() as conn:
        bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        if bestellung['Status'] not in ['Erstellt']:
            flash('Bestellung kann nur im Status "Erstellt" zur Freigabe markiert werden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        conn.execute('UPDATE Bestellung SET Status = ?, FreigabeBemerkung = ? WHERE ID = ?', 
                    ('Zur Freigabe', freigabe_bemerkung if freigabe_bemerkung else None, bestellung_id))
        conn.commit()
        
        # Benachrichtigungen erstellen
        try:
            from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
            erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'bestellung_zur_freigabe', conn)
        except Exception as e:
            print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
        
        flash('Bestellung wurde zur Freigabe markiert.', 'success')
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/freigabebemerkung/bearbeiten', methods=['POST'])
@login_required
def bestellung_freigabebemerkung_bearbeiten(bestellung_id):
    """Freigabebemerkung einer Bestellung bearbeiten (nur für Ersteller, solange nicht freigegeben)"""
    mitarbeiter_id = session.get('user_id')
    freigabe_bemerkung = request.form.get('freigabe_bemerkung', '').strip()
    
    with get_db_connection() as conn:
        # Bestellung laden
        bestellung = conn.execute('''
            SELECT Status, ErstelltVonID FROM Bestellung 
            WHERE ID = ? AND Gelöscht = 0
        ''', (bestellung_id,)).fetchone()
        
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        # Prüfen, ob Benutzer der Ersteller ist
        if bestellung['ErstelltVonID'] != mitarbeiter_id:
            flash('Nur der Ersteller kann die Freigabebemerkung bearbeiten.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        # Prüfen, ob Status "Erstellt" oder "Zur Freigabe" ist
        if bestellung['Status'] not in ['Erstellt', 'Zur Freigabe']:
            flash('Freigabebemerkung kann nur bearbeitet werden, solange die Bestellung nicht freigegeben wurde.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        # Freigabebemerkung aktualisieren
        conn.execute('UPDATE Bestellung SET FreigabeBemerkung = ? WHERE ID = ?', 
                    (freigabe_bemerkung if freigabe_bemerkung else None, bestellung_id))
        conn.commit()
        flash('Freigabebemerkung wurde gespeichert.', 'success')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/freigeben', methods=['POST'])
@login_required
@permission_required('bestellungen_freigeben')
def bestellung_freigeben(bestellung_id):
    """Bestellung freigeben mit Unterschrift"""
    mitarbeiter_id = session.get('user_id')
    unterschrift = request.form.get('unterschrift', '').strip()
    
    # Validierung: Unterschrift ist erforderlich
    if not unterschrift:
        flash('Bitte unterschreiben Sie die Bestellung.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    with get_db_connection() as conn:
        bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        if bestellung['Status'] != 'Zur Freigabe':
            flash('Bestellung kann nur im Status "Zur Freigabe" freigegeben werden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        # Unterschrift und Freigabe speichern
        conn.execute('''
            UPDATE Bestellung 
            SET Status = ?, FreigegebenAm = datetime('now', 'localtime'), FreigegebenVonID = ?, Unterschrift = ?
            WHERE ID = ?
        ''', ('Freigegeben', mitarbeiter_id, unterschrift, bestellung_id))
        conn.commit()
        
        # Alle bestehenden Benachrichtigungen für diese Bestellung löschen
        conn.execute('''
            DELETE FROM Benachrichtigung 
            WHERE Modul = 'bestellwesen' 
            AND Zusatzdaten LIKE ?
        ''', (f'%bestellung_id":{bestellung_id}%',))
        
        # Benachrichtigungen erstellen
        try:
            from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
            erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'bestellung_freigegeben', conn)
        except Exception as e:
            print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
        
        flash('Bestellung wurde freigegeben.', 'success')
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/als-bestellt', methods=['POST'])
@login_required
def bestellung_als_bestellt(bestellung_id):
    """Bestellung als bestellt markieren"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        if bestellung['Status'] != 'Freigegeben':
            flash('Bestellung kann nur im Status "Freigegeben" als bestellt markiert werden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        conn.execute('''
            UPDATE Bestellung 
            SET Status = ?, BestelltAm = datetime('now', 'localtime'), BestelltVonID = ?
            WHERE ID = ?
        ''', ('Bestellt', mitarbeiter_id, bestellung_id))
        conn.commit()
        
        # Alle bestehenden Benachrichtigungen für diese Bestellung löschen (egal ob gelesen oder nicht)
        conn.execute('''
            DELETE FROM Benachrichtigung 
            WHERE Modul = 'bestellwesen' 
            AND Zusatzdaten LIKE ?
        ''', (f'%bestellung_id":{bestellung_id}%',))
        conn.commit()
        
        # Benachrichtigungen erstellen
        try:
            from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
            erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'bestellung_bestellt', conn)
        except Exception as e:
            print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
        
        flash('Bestellung wurde als bestellt markiert.', 'success')
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/stornieren', methods=['POST'])
@login_required
def bestellung_stornieren(bestellung_id):
    """Bestellung stornieren"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        if bestellung['Status'] != 'Erledigt':
            flash('Bestellung kann nur im Status "Erledigt" storniert werden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        conn.execute('''
            UPDATE Bestellung 
            SET Status = ?
            WHERE ID = ?
        ''', ('Storniert', bestellung_id))
        conn.commit()
        
        # Benachrichtigungen erstellen
        try:
            from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
            erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'bestellung_storniert', conn)
        except Exception as e:
            print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
        
        flash('Bestellung wurde storniert.', 'success')
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/position-hinzufuegen', methods=['POST'])
@login_required
def bestellung_position_hinzufuegen(bestellung_id):
    """Position zu bestehender Bestellung hinzufügen"""
    mitarbeiter_id = session.get('user_id')
    
    ersatzteil_id_str = request.form.get('ersatzteil_id', '').strip()
    ersatzteil_id = int(ersatzteil_id_str) if ersatzteil_id_str else None
    menge = request.form.get('menge', type=int) or 1
    bestellnummer = request.form.get('bestellnummer', '').strip() or None
    bezeichnung = request.form.get('bezeichnung', '').strip() or None
    preis_str = request.form.get('preis', '').strip()
    preis = float(preis_str) if preis_str else None
    waehrung = request.form.get('waehrung', 'EUR').strip()
    bemerkung = request.form.get('bemerkung', '').strip() or None
    link = request.form.get('link', '').strip() or None
    # Prüfe ob link "None" als String ist und konvertiere zu None
    if link and link.lower() in ('none', 'null', 'undefined'):
        link = None
    
    if not ersatzteil_id and not bestellnummer:
        flash('Bitte geben Sie entweder eine ErsatzteilID oder eine Bestellnummer ein.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Bestellung existiert und Status erlaubt Bearbeitung
            bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
            if not bestellung:
                flash('Bestellung nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
            
            if bestellung['Status'] not in ['Erstellt', 'Zur Freigabe']:
                flash('Positionen können nur bei Bestellungen im Status "Erstellt" oder "Zur Freigabe" hinzugefügt werden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
            
            # Falls ErsatzteilID vorhanden und Bestellnummer/Bezeichnung/Einheit nicht angegeben, aus Ersatzteil laden
            einheit = None
            if ersatzteil_id:
                ersatzteil = conn.execute('SELECT Bestellnummer, Bezeichnung, Einheit, Link FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                if ersatzteil:
                    if not bestellnummer:
                        bestellnummer = ersatzteil['Bestellnummer']
                    if not bezeichnung:
                        bezeichnung = ersatzteil['Bezeichnung']
                    if not einheit:
                        einheit = ersatzteil['Einheit'] if ersatzteil['Einheit'] else 'Stück'
                    # Link nur aus Ersatzteil übernehmen, wenn kein Link im Formular vorhanden
                    if not link and 'Link' in ersatzteil.keys() and ersatzteil['Link']:
                        link = ersatzteil['Link']
            
            if not einheit:
                einheit = 'Stück'
            
            # Position hinzufügen
            conn.execute('''
                INSERT INTO BestellungPosition (BestellungID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Bemerkung, Preis, Waehrung, Link)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bestellung_id, ersatzteil_id, menge, einheit, bestellnummer, bezeichnung, bemerkung, preis, waehrung, link))
            conn.commit()
            flash('Position erfolgreich hinzugefügt.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Hinzufügen: {str(e)}', 'danger')
        print(f"Position hinzufügen Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/position/<int:position_id>/bearbeiten', methods=['POST'])
@login_required
def bestellung_position_bearbeiten(bestellung_id, position_id):
    """Position einer Bestellung bearbeiten"""
    menge = request.form.get('menge', type=int)
    einheit = request.form.get('einheit', '').strip() or None
    bestellnummer = request.form.get('bestellnummer', '').strip() or None
    bezeichnung = request.form.get('bezeichnung', '').strip() or None
    preis_str = request.form.get('preis', '').strip()
    preis = float(preis_str) if preis_str else None
    waehrung = request.form.get('waehrung', 'EUR').strip()
    bemerkung = request.form.get('bemerkung', '').strip() or None
    link = request.form.get('link', '').strip() or None
    # Prüfe ob link "None" als String ist und konvertiere zu None
    if link and link.lower() in ('none', 'null', 'undefined'):
        link = None
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Bestellung existiert und Status erlaubt Bearbeitung
            bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
            if not bestellung:
                flash('Bestellung nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
            
            if bestellung['Status'] not in ['Erstellt', 'Zur Freigabe']:
                flash('Positionen können nur bei Bestellungen im Status "Erstellt" oder "Zur Freigabe" bearbeitet werden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
            
            # Einheit aus Formular oder bestehender Position übernehmen
            if not einheit:
                # Einheit aus bestehender Position übernehmen oder Standard
                alte_position = conn.execute('SELECT Einheit, ErsatzteilID FROM BestellungPosition WHERE ID = ?', (position_id,)).fetchone()
                if alte_position:
                    einheit = alte_position['Einheit'] if alte_position['Einheit'] else None
                    # Falls keine Einheit vorhanden, versuchen von Ersatzteil zu laden
                    if not einheit and alte_position['ErsatzteilID']:
                        ersatzteil = conn.execute('SELECT Einheit FROM Ersatzteil WHERE ID = ?', (alte_position['ErsatzteilID'],)).fetchone()
                        if ersatzteil and ersatzteil['Einheit']:
                            einheit = ersatzteil['Einheit']
            
            if not einheit:
                einheit = 'Stück'
            
            # Position aktualisieren
            conn.execute('''
                UPDATE BestellungPosition 
                SET Menge = ?, Einheit = ?, Bestellnummer = ?, Bezeichnung = ?, Bemerkung = ?, Preis = ?, Waehrung = ?, Link = ?
                WHERE ID = ? AND BestellungID = ?
            ''', (menge, einheit, bestellnummer, bezeichnung, bemerkung, preis, waehrung, link, position_id, bestellung_id))
            conn.commit()
            flash('Position erfolgreich aktualisiert.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Aktualisieren: {str(e)}', 'danger')
        print(f"Position bearbeiten Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/position/<int:position_id>/loeschen', methods=['POST'])
@login_required
def bestellung_position_loeschen(bestellung_id, position_id):
    """Position einer Bestellung löschen"""
    try:
        with get_db_connection() as conn:
            # Prüfe ob Bestellung existiert und Status erlaubt Bearbeitung
            bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
            if not bestellung:
                flash('Bestellung nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
            
            if bestellung['Status'] not in ['Erstellt', 'Zur Freigabe']:
                flash('Positionen können nur bei Bestellungen im Status "Erstellt" oder "Zur Freigabe" gelöscht werden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
            
            # Position löschen
            conn.execute('DELETE FROM BestellungPosition WHERE ID = ? AND BestellungID = ?', (position_id, bestellung_id))
            conn.commit()
            flash('Position erfolgreich gelöscht.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
        print(f"Position löschen Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/sichtbarkeit', methods=['GET'])
@login_required
def get_bestellung_sichtbarkeit(bestellung_id):
    """AJAX: Sichtbarkeiten einer Bestellung laden"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Primärabteilung des Mitarbeiters
        mitarbeiter = conn.execute(
            'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
            (mitarbeiter_id,)
        ).fetchone()
        primaer_abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
        
        # Auswählbare Abteilungen
        from utils import get_auswaehlbare_abteilungen_fuer_mitarbeiter, get_mitarbeiter_abteilungen
        auswaehlbare = get_auswaehlbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        eigene_abteilungen_ids = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
        
        # Aktuell ausgewählte Sichtbarkeiten
        aktuelle = conn.execute('''
            SELECT sv.AbteilungID, a.Bezeichnung, a.ParentAbteilungID, a.Sortierung
            FROM BestellungSichtbarkeit sv
            JOIN Abteilung a ON sv.AbteilungID = a.ID
            WHERE sv.BestellungID = ?
            ORDER BY a.Sortierung, a.Bezeichnung
        ''', (bestellung_id,)).fetchall()
        aktuelle_ids = [a['AbteilungID'] for a in aktuelle]
        
        # Alle eigenen Abteilungen mit allen Unterabteilungen
        from utils import get_untergeordnete_abteilungen
        alle_eigene_mit_unter = set()
        for abt_id in eigene_abteilungen_ids:
            alle_eigene_mit_unter.update(get_untergeordnete_abteilungen(abt_id, conn))
        
        # Zusätzliche aktuelle Abteilungen
        zusaetzliche_aktuelle = []
        for akt in aktuelle:
            if akt['AbteilungID'] not in alle_eigene_mit_unter:
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
            'bestellung_id': bestellung_id,
            'auswaehlbare': auswaehlbare_json,
            'zusaetzliche': zusaetzliche_aktuelle,
            'aktuelle': aktuelle_ids
        })


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/sichtbarkeit', methods=['POST'])
@login_required
def update_bestellung_sichtbarkeit(bestellung_id):
    """AJAX: Sichtbarkeiten einer Bestellung aktualisieren"""
    sichtbare_abteilungen = request.form.getlist('sichtbare_abteilungen')
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Primärabteilung des Mitarbeiters ermitteln
            mitarbeiter = conn.execute(
                'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
                (mitarbeiter_id,)
            ).fetchone()
            abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
            
            # Alte Sichtbarkeiten löschen
            conn.execute('DELETE FROM BestellungSichtbarkeit WHERE BestellungID = ?', (bestellung_id,))
            
            # Neue Sichtbarkeiten einfügen (optional - wenn keine ausgewählt, wird Primärabteilung verwendet)
            if sichtbare_abteilungen:
                for abt_id in sichtbare_abteilungen:
                    try:
                        conn.execute('''
                            INSERT INTO BestellungSichtbarkeit (BestellungID, AbteilungID)
                            VALUES (?, ?)
                        ''', (bestellung_id, abt_id))
                    except:
                        pass
            elif abteilung_id:
                # Wenn keine Abteilungen ausgewählt, Primärabteilung verwenden
                try:
                    conn.execute('''
                        INSERT INTO BestellungSichtbarkeit (BestellungID, AbteilungID)
                        VALUES (?, ?)
                    ''', (bestellung_id, abteilung_id))
                except:
                    pass
            
            conn.commit()
        
        return jsonify({'success': True, 'message': 'Sichtbarkeit erfolgreich aktualisiert.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler: {str(e)}'}), 500


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/pdf')
@login_required
def bestellung_pdf_export(bestellung_id):
    """PDF-Export für eine Bestellung mit docx-Vorlage"""
    try:
        with get_db_connection() as conn:
            content, filename, mimetype, is_pdf = generate_bestellung_pdf(bestellung_id, conn)
            
            response = make_response(content)
            response.headers['Content-Type'] = mimetype
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('ersatzteile.bestellung_liste'))
    except FileNotFoundError as e:
        flash(str(e), 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    except Exception as e:
        flash(f'Fehler beim Erstellen des Berichts: {str(e)}', 'danger')
        print(f"Bestellungs-Export Fehler: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/datei/upload', methods=['POST'])
@login_required
def bestellung_datei_upload(bestellung_id):
    """Datei-Upload für Bestellung"""
    mitarbeiter_id = session.get('user_id')
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    file = request.files['file']
    beschreibung = request.form.get('beschreibung', '').strip()
    
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    # Dateiendung prüfen
    if not validate_file_extension(file.filename, {'pdf'}):
        flash('Nur PDF-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    try:
        with get_db_connection() as conn:
            # Ordner erstellen
            bestellung_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], 'Bestellungen', str(bestellung_id))
            create_upload_folder(bestellung_folder)
            
            # Datei speichern mit Timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            original_filename = file.filename
            file.filename = timestamp + secure_filename(original_filename)
            
            success_upload, filename, error_message = save_uploaded_file(
                file,
                bestellung_folder,
                allowed_extensions={'pdf'}
            )
            
            if not success_upload or error_message:
                flash(f'Fehler beim Hochladen: {error_message}', 'danger')
            else:
                # Datenbankeintrag in Datei-Tabelle
                relative_path = f'Angebote/Bestellungen/{bestellung_id}/{filename}'
                from ..services import speichere_datei, get_datei_typ_aus_dateiname
                speichere_datei(
                    bereich_typ='Bestellung',
                    bereich_id=bestellung_id,
                    dateiname=original_filename,
                    dateipfad=relative_path,
                    beschreibung=beschreibung,
                    typ='PDF',
                    mitarbeiter_id=mitarbeiter_id,
                    conn=conn
                )
                flash('Datei erfolgreich hochgeladen.', 'success')
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Datei-Upload Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/auftragsbestätigung/upload', methods=['POST'])
@login_required
def bestellung_auftragsbestätigung_upload(bestellung_id):
    """Auftragsbestätigung-Upload für Bestellung"""
    mitarbeiter_id = session.get('user_id')
    
    # Prüfe ob Bestellung den Status "Bestellt" hat
    with get_db_connection() as conn:
        bestellung = conn.execute('SELECT Status FROM Bestellung WHERE ID = ? AND Gelöscht = 0', (bestellung_id,)).fetchone()
        if not bestellung:
            flash('Bestellung nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
        if bestellung['Status'] not in ['Bestellt', 'Teilweise erhalten', 'Erhalten', 'Erledigt']:
            flash('Auftragsbestätigung kann nur für bestellte Bestellungen hochgeladen werden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    file = request.files['file']
    beschreibung = request.form.get('beschreibung', '').strip()
    
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    # Dateiendung prüfen
    if not validate_file_extension(file.filename, {'pdf', 'jpg', 'jpeg', 'png'}):
        flash('Nur PDF-, JPEG- oder PNG-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    try:
        with get_db_connection() as conn:
            # Ordner erstellen
            auftragsbestätigung_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Auftragsbestätigungen', str(bestellung_id))
            create_upload_folder(auftragsbestätigung_folder)
            
            # Datei speichern mit Timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            original_filename = file.filename
            file.filename = timestamp + secure_filename(original_filename)
            
            success_upload, filename, error_message = save_uploaded_file(
                file,
                auftragsbestätigung_folder,
                allowed_extensions={'pdf', 'jpg', 'jpeg', 'png'}
            )
            
            if not success_upload or error_message:
                flash(f'Fehler beim Hochladen: {error_message}', 'danger')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
            
            # Datenbankeintrag in Datei-Tabelle
            relative_path = f'Bestellwesen/Auftragsbestätigungen/{bestellung_id}/{filename}'
            from ..services import speichere_datei, get_datei_typ_aus_dateiname
            typ = get_datei_typ_aus_dateiname(original_filename)
            speichere_datei(
                bereich_typ='Bestellung',
                bereich_id=bestellung_id,
                dateiname=original_filename,
                dateipfad=relative_path,
                beschreibung=beschreibung,
                typ=typ,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn
            )
            flash('Auftragsbestätigung erfolgreich hochgeladen.', 'success')
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Auftragsbestätigung-Upload Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/datei/<path:filepath>')
@login_required
def bestellung_datei_anzeigen(bestellung_id, filepath):
    """Bestellungs-Datei anzeigen/herunterladen (PDF)"""
    mitarbeiter_id = session.get('user_id')
    
    # Normalisiere den Pfad: Backslashes zu Forward-Slashes (für Windows-Kompatibilität)
    filepath = filepath.replace('\\', '/')
    
    # Sicherheitsprüfung: Dateipfad muss mit Bestellungen/{bestellung_id}/ oder Angebote/Bestellungen/{bestellung_id}/ beginnen
    expected_prefixes = [
        f'Bestellungen/{bestellung_id}/',
        f'Angebote/Bestellungen/{bestellung_id}/'
    ]
    if not any(filepath.startswith(prefix) for prefix in expected_prefixes):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    try:
        # Berechtigungsprüfung: Prüfe ob Benutzer Zugriff auf die Bestellung hat
        with get_db_connection() as conn:
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            if not is_admin:
                sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
                sichtbarkeiten = conn.execute('SELECT AbteilungID FROM BestellungSichtbarkeit WHERE BestellungID = ?', (bestellung_id,)).fetchall()
                sichtbarkeits_ids = [s['AbteilungID'] for s in sichtbarkeiten]
                
                if not any(abt in sichtbare_abteilungen for abt in sichtbarkeits_ids):
                    flash('Sie haben keine Berechtigung, diese Datei zu sehen.', 'danger')
                    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        # Vollständigen Pfad erstellen - unterstütze beide Pfad-Formate
        if filepath.startswith('Angebote/Bestellungen/'):
            # Neues Format: Angebote/Bestellungen/{id}/...
            full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath.replace('/', os.sep))
        else:
            # Altes Format: Bestellungen/{id}/...
            full_path = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], filepath.replace('/', os.sep))
        
        # Sicherheitsprüfung: Datei muss existieren
        if not os.path.exists(full_path):
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        # Dateiname extrahieren
        filename = os.path.basename(full_path)
        directory = os.path.dirname(full_path)
        
        return send_from_directory(
            directory,
            filename,
            mimetype='application/pdf',
            as_attachment=False  # Im Browser anzeigen
        )
    except Exception as e:
        flash(f'Fehler beim Laden der Datei: {str(e)}', 'danger')
        print(f"Bestellung Datei anzeigen Fehler: {e}")
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/auftragsbestätigung/<path:filepath>')
@login_required
def auftragsbestätigung_anzeigen(filepath):
    """Auftragsbestätigung-Datei anzeigen/herunterladen (PDF, JPEG, JPG, PNG) - für alle angemeldeten Benutzer"""
    mitarbeiter_id = session.get('user_id')
    
    # Normalisiere den Pfad: Backslashes zu Forward-Slashes (für Windows-Kompatibilität)
    filepath = filepath.replace('\\', '/')
    
    # Sicherheitsprüfung: Dateipfad muss mit Bestellwesen/Auftragsbestätigungen beginnen
    if not filepath.startswith('Bestellwesen/Auftragsbestätigungen/'):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_liste'))
    
    try:
        # Bestellung-ID aus Pfad extrahieren (Bestellwesen/Auftragsbestätigungen/{id}/...)
        parts = filepath.split('/')
        if len(parts) >= 3:
            bestellung_id = parts[2]
            try:
                bestellung_id = int(bestellung_id)
                # Berechtigungsprüfung: Prüfe ob Benutzer Zugriff auf die Bestellung hat
                with get_db_connection() as conn:
                    is_admin = 'admin' in session.get('user_berechtigungen', [])
                    if not is_admin:
                        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
                        sichtbarkeiten = conn.execute('SELECT AbteilungID FROM BestellungSichtbarkeit WHERE BestellungID = ?', (bestellung_id,)).fetchall()
                        sichtbarkeits_ids = [s['AbteilungID'] for s in sichtbarkeiten]
                        
                        if not any(abt in sichtbare_abteilungen for abt in sichtbarkeits_ids):
                            flash('Sie haben keine Berechtigung, diese Datei zu sehen.', 'danger')
                            return redirect(url_for('ersatzteile.bestellung_liste'))
            except (ValueError, TypeError):
                flash('Ungültige Bestellungs-ID im Dateipfad.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
        
        # Vollständigen Pfad erstellen
        full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath)
        
        # Sicherheitsprüfung: Datei muss existieren und im erlaubten Ordner sein
        if not os.path.exists(full_path) or not os.path.abspath(full_path).startswith(os.path.abspath(current_app.config['UPLOAD_BASE_FOLDER'])):
            flash('Datei nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.bestellung_liste'))
        
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
        print(f"Auftragsbestätigung anzeigen Fehler: {e}")
        return redirect(url_for('ersatzteile.bestellung_liste'))
