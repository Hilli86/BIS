"""
Angebotsanfrage Routes - Angebotsanfragen-Verwaltung
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app, make_response
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from .. import ersatzteile_bp
from utils import get_db_connection, login_required
from utils.file_handling import save_uploaded_file, create_upload_folder
from ..services import generate_angebotsanfrage_pdf, get_dateien_fuer_bereich, speichere_datei, get_datei_typ_aus_dateiname


def log_info(message):
    """Loggt eine Info-Nachricht direkt an stderr (für journalctl)"""
    import sys
    print(f"[INFO] {message}", file=sys.stderr, flush=True)

def log_error(message):
    """Loggt eine Fehlernachricht direkt an stderr (für journalctl)"""
    import sys
    print(f"[ERROR] {message}", file=sys.stderr, flush=True)

def log_warning(message):
    """Loggt eine Warnung direkt an stderr (für journalctl)"""
    import sys
    print(f"[WARNING] {message}", file=sys.stderr, flush=True)


def get_angebotsanfrage_dateien(angebotsanfrage_id):
    """
    Konvertiert eine DOCX-Datei zu PDF.
    Versucht zuerst docx2pdf (Windows), dann LibreOffice (Linux/Cross-Platform).
    """
    # Methode 1: docx2pdf (funktioniert auf Windows mit Word)
    if DOCX2PDF_AVAILABLE:
        try:
            # COM-Initialisierung für Windows
            if sys.platform == 'win32':
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except ImportError:
                    pass
            
            convert(docx_path, pdf_path)
            
            # COM aufräumen (Windows)
            if sys.platform == 'win32':
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except:
                    pass
            
            # Prüfen ob PDF erstellt wurde
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                return True
        except Exception as e:
            # Weiter zu LibreOffice
            pass
    
    # Methode 2: LibreOffice (funktioniert auf Linux und Windows)
    libreoffice_cmd = None
    if sys.platform == 'win32':
        # Windows: Suche nach LibreOffice
        possible_paths = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                libreoffice_cmd = path
                break
    else:
        # Linux/Unix: Suche nach LibreOffice
        libreoffice_cmd = shutil.which('libreoffice') or shutil.which('soffice')
        
        # Falls nicht im PATH, bekannte Linux-Pfade prüfen
        if not libreoffice_cmd:
            possible_paths = [
                '/usr/bin/libreoffice',
                '/usr/bin/soffice',
                '/usr/local/bin/libreoffice',
                '/usr/local/bin/soffice',
                '/snap/bin/libreoffice',
                '/opt/libreoffice*/program/soffice',
            ]
            for path in possible_paths:
                # Unterstützung für Wildcards
                if '*' in path:
                    import glob
                    matches = glob.glob(path)
                    if matches:
                        path = matches[0]
                
                if os.path.exists(path) and os.access(path, os.X_OK):
                    libreoffice_cmd = path
                    break
    
    if not libreoffice_cmd:
        log_error("LibreOffice nicht gefunden. Bitte installieren Sie LibreOffice.")
        return False
    
    try:
        # LibreOffice im headless-Modus für Konvertierung
        output_dir = os.path.dirname(pdf_path)
        cmd = [
            libreoffice_cmd,
            '--headless',
            '--nodefault',
            '--nolockcheck',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            docx_path
        ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False
        )
        
        # LibreOffice erstellt PDF mit gleichem Namen wie DOCX
        docx_basename = os.path.splitext(os.path.basename(docx_path))[0]
        generated_pdf = os.path.join(output_dir, f"{docx_basename}.pdf")
        
        # Prüfe auch, ob die PDF mit dem Namen der temporären PDF-Datei erstellt wurde
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        alternative_pdf = os.path.join(output_dir, f"{pdf_basename}.pdf")
        
        # Suche nach erstellter PDF
        found_pdf = None
        if os.path.exists(generated_pdf):
            found_pdf = generated_pdf
        elif os.path.exists(alternative_pdf):
            found_pdf = alternative_pdf
        else:
            # Prüfe, ob vielleicht eine PDF mit anderem Namen erstellt wurde
            if os.path.exists(output_dir):
                try:
                    pdf_files = [f for f in os.listdir(output_dir) if f.endswith('.pdf')]
                    if pdf_files:
                        found_pdf = os.path.join(output_dir, pdf_files[0])
                except Exception as e:
                    log_error(f"Fehler beim Auflisten des Ausgabeverzeichnisses: {e}")
        
        # Wenn PDF gefunden wurde, verwenden
        if found_pdf and os.path.exists(found_pdf):
            if found_pdf != pdf_path:
                shutil.move(found_pdf, pdf_path)
            if os.path.getsize(pdf_path) > 0:
                return True
            else:
                log_error(f"PDF wurde erstellt, ist aber leer: {pdf_path}")
        else:
            if result.returncode != 0:
                stderr_text = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ''
                log_error(f"LibreOffice Fehler (Returncode {result.returncode}): {stderr_text[:200]}")
            else:
                log_error(f"PDF wurde nicht erstellt. Gesuchte Pfade: {generated_pdf}, {alternative_pdf}")
    except subprocess.TimeoutExpired:
        log_error("LibreOffice Konvertierung: Timeout nach 60 Sekunden")
    except Exception as e:
        log_error(f"LibreOffice Konvertierung fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
    
    return False


def get_angebotsanfrage_dateien(angebotsanfrage_id):
    """Hilfsfunktion: Scannt Ordner nach PDF-Dateien für eine Angebotsanfrage"""
    angebote_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Angebote', str(angebotsanfrage_id))
    dateien = []
    
    if os.path.exists(angebote_folder):
        try:
            for filename in os.listdir(angebote_folder):
                if filename.lower().endswith('.pdf'):
                    filepath = os.path.join(angebote_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellwesen/Angebote/{angebotsanfrage_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Angebote-Ordners: {e}")
    
    return dateien


@ersatzteile_bp.route('/angebotsanfragen')
@login_required
def angebotsanfrage_liste():
    """Liste aller Angebotsanfragen mit Filter"""
    mitarbeiter_id = session.get('user_id')
    
    # Filterparameter
    status_filter = request.args.get('status')
    
    with get_db_connection() as conn:
        # Sichtbare Abteilungen für den Mitarbeiter ermitteln (eigene + alle Unterabteilungen)
        from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        
        # BIS-Admin sieht alle Angebote
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Basis-Query mit Bestellnummer und Bezeichnung der ersten Position
        query = '''
            SELECT 
                a.ID,
                a.Status,
                a.ErstelltAm,
                a.VersendetAm,
                a.AngebotErhaltenAm,
                l.Name AS LieferantName,
                m.Vorname || ' ' || m.Nachname AS ErstelltVon,
                abt.Bezeichnung AS Abteilung,
                COUNT(p.ID) AS PositionenAnzahl,
                (SELECT e.Bestellnummer FROM AngebotsanfragePosition ap 
                 JOIN Ersatzteil e ON ap.ErsatzteilID = e.ID 
                 WHERE ap.AngebotsanfrageID = a.ID LIMIT 1) AS ErsteBestellnummer,
                (SELECT e.Bezeichnung FROM AngebotsanfragePosition ap 
                 JOIN Ersatzteil e ON ap.ErsatzteilID = e.ID 
                 WHERE ap.AngebotsanfrageID = a.ID LIMIT 1) AS ErsteBezeichnung
            FROM Angebotsanfrage a
            LEFT JOIN Lieferant l ON a.LieferantID = l.ID
            LEFT JOIN Mitarbeiter m ON a.ErstelltVonID = m.ID
            LEFT JOIN Abteilung abt ON a.ErstellerAbteilungID = abt.ID
            LEFT JOIN AngebotsanfragePosition p ON a.ID = p.AngebotsanfrageID
            WHERE 1=1
        '''
        params = []
        
        # Abteilungsfilter: Nur Angebote aus sichtbaren Abteilungen (außer Admin)
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f' AND a.ErstellerAbteilungID IN ({placeholders})'
            params.extend(sichtbare_abteilungen)
        elif not is_admin:
            # Keine Berechtigung - keine Angebote anzeigen
            query += ' AND 1=0'
        
        # Status-Filter
        if status_filter:
            # Spezifischer Status gewählt
            query += ' AND a.Status = ?'
            params.append(status_filter)
        else:
            # Standard: "-- Alle in Arbeit --" - alle außer Abgeschlossen
            query += ' AND a.Status != ?'
            params.append('Abgeschlossen')
        
        query += ' GROUP BY a.ID ORDER BY a.ErstelltAm DESC'
        
        angebotsanfragen = conn.execute(query, params).fetchall()
    
    return render_template(
        'angebotsanfrage_liste.html',
        angebotsanfragen=angebotsanfragen,
        status_filter=status_filter
    )


@ersatzteile_bp.route('/angebotsanfragen/smart-add/<int:ersatzteil_id>')
@login_required
def angebotsanfrage_smart_add(ersatzteil_id):
    """Smart-Link: Prüft ob offene Anfrage existiert, sonst erstellt neue (JSON Response)"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Ersatzteil laden
            ersatzteil = conn.execute(
                'SELECT LieferantID, Bestellnummer, Bezeichnung, Einheit, Link FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0',
                (ersatzteil_id,)
            ).fetchone()
            
            if not ersatzteil:
                return jsonify({
                    'success': False,
                    'message': 'Ersatzteil nicht gefunden.'
                }), 404
            
            lieferant_id = ersatzteil['LieferantID']
            
            if not lieferant_id:
                return jsonify({
                    'success': False,
                    'message': 'Dieses Ersatzteil hat keinen Lieferanten zugeordnet.'
                }), 400
            
            # Lieferant-Name laden
            lieferant = conn.execute('SELECT Name FROM Lieferant WHERE ID = ?', (lieferant_id,)).fetchone()
            lieferant_name = lieferant['Name'] if lieferant else 'Unbekannt'
            
            # Prüfe ob offene Anfrage existiert
            offene_anfrage = conn.execute('''
                SELECT ID FROM Angebotsanfrage 
                WHERE LieferantID = ? AND Status = 'Offen'
                ORDER BY ErstelltAm DESC LIMIT 1
            ''', (lieferant_id,)).fetchone()
            
            if offene_anfrage:
                # Position zu bestehender Anfrage hinzufügen
                anfrage_id = offene_anfrage['ID']
                
                # Prüfe ob Ersatzteil bereits in dieser Anfrage ist
                vorhanden = conn.execute('''
                    SELECT ID FROM AngebotsanfragePosition
                    WHERE AngebotsanfrageID = ? AND ErsatzteilID = ?
                ''', (anfrage_id, ersatzteil_id)).fetchone()
                
                if vorhanden:
                    return jsonify({
                        'success': True,
                        'message': 'Dieses Ersatzteil ist bereits in der offenen Angebotsanfrage enthalten.',
                        'anfrage_id': anfrage_id,
                        'action': 'bereits_vorhanden'
                    })
                else:
                    # Ersatzteil-Daten laden für Bestellnummer, Bezeichnung, Einheit und Link
                    bestellnummer = ersatzteil['Bestellnummer']
                    bezeichnung = ersatzteil['Bezeichnung']
                    einheit = ersatzteil['Einheit'] if 'Einheit' in ersatzteil.keys() and ersatzteil['Einheit'] else 'Stück'
                    link = ersatzteil['Link'] if 'Link' in ersatzteil.keys() else None
                    
                    # Position hinzufügen
                    conn.execute('''
                        INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Link)
                        VALUES (?, ?, 1, ?, ?, ?, ?)
                    ''', (anfrage_id, ersatzteil_id, einheit, bestellnummer, bezeichnung, link))
                    conn.commit()
                    
                    return jsonify({
                        'success': True,
                        'message': f'Ersatzteil zur bestehenden Angebotsanfrage #{anfrage_id} hinzugefügt.',
                        'anfrage_id': anfrage_id,
                        'action': 'hinzugefuegt'
                    })
            else:
                # Primärabteilung des Mitarbeiters ermitteln
                mitarbeiter = conn.execute(
                    'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
                    (mitarbeiter_id,)
                ).fetchone()
                abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
                
                # Neue Anfrage erstellen
                cursor = conn.execute('''
                    INSERT INTO Angebotsanfrage (LieferantID, ErstelltVonID, ErstellerAbteilungID, Status)
                    VALUES (?, ?, ?, 'Offen')
                ''', (lieferant_id, mitarbeiter_id, abteilung_id))
                anfrage_id = cursor.lastrowid
                
                # Ersatzteil-Daten laden für Bestellnummer, Bezeichnung, Einheit und Link
                bestellnummer = ersatzteil['Bestellnummer']
                bezeichnung = ersatzteil['Bezeichnung']
                einheit = ersatzteil['Einheit'] if 'Einheit' in ersatzteil.keys() and ersatzteil['Einheit'] else 'Stück'
                link = ersatzteil['Link'] if 'Link' in ersatzteil.keys() else None
                
                # Ersatzteil als Position hinzufügen
                conn.execute('''
                    INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Link)
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                ''', (anfrage_id, ersatzteil_id, einheit, bestellnummer, bezeichnung, link))
                conn.commit()
                
                return jsonify({
                    'success': True,
                    'message': f'Neue Angebotsanfrage #{anfrage_id} erstellt und Ersatzteil hinzugefügt.',
                    'anfrage_id': anfrage_id,
                    'action': 'neu_erstellt'
                })
                
    except Exception as e:
        print(f"Smart-Add Fehler: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Fehler: {str(e)}'
        }), 500


@ersatzteile_bp.route('/angebotsanfragen/neu', methods=['GET', 'POST'])
@login_required
def angebotsanfrage_neu():
    """Neue Angebotsanfrage erstellen"""
    mitarbeiter_id = session.get('user_id')
    
    # Query-Parameter für Smart-Erstellung
    ersatzteil_id_param = request.args.get('ersatzteil_id', type=int)
    lieferant_id_param = request.args.get('lieferant_id', type=int)
    
    if request.method == 'POST':
        lieferant_id = request.form.get('lieferant_id', type=int)
        bemerkung = request.form.get('bemerkung', '').strip()
        
        # Ersatzteil-Positionen aus Formular
        ersatzteil_ids = request.form.getlist('ersatzteil_id[]')
        mengen = request.form.getlist('menge[]')
        einheiten = request.form.getlist('einheit[]')
        bestellnummern = request.form.getlist('bestellnummer[]')
        bezeichnungen = request.form.getlist('bezeichnung[]')
        positionen_bemerkungen = request.form.getlist('position_bemerkung[]')
        links = request.form.getlist('link[]')
        
        if not lieferant_id:
            flash('Bitte wählen Sie einen Lieferanten aus.', 'danger')
            return redirect(url_for('ersatzteile.angebotsanfrage_neu'))
        
        # Mindestens eine Position muss vorhanden sein (mit oder ohne ErsatzteilID)
        # Prüfe ob mindestens eine Position mit ErsatzteilID oder Bestellnummer vorhanden ist
        has_positions = False
        for i in range(max(len(ersatzteil_ids), len(bestellnummern))):
            ersatzteil_id_str = ersatzteil_ids[i] if i < len(ersatzteil_ids) else ''
            bestellnummer = bestellnummern[i].strip() if i < len(bestellnummern) and bestellnummern[i] else ''
            if (ersatzteil_id_str and ersatzteil_id_str.strip()) or bestellnummer:
                has_positions = True
                break
        
        if not has_positions:
            flash('Bitte fügen Sie mindestens eine Position hinzu (mit ErsatzteilID oder Bestellnummer).', 'danger')
            return redirect(url_for('ersatzteile.angebotsanfrage_neu'))
        
        try:
            with get_db_connection() as conn:
                # Primärabteilung des Mitarbeiters ermitteln
                mitarbeiter = conn.execute(
                    'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
                    (mitarbeiter_id,)
                ).fetchone()
                abteilung_id = mitarbeiter['PrimaerAbteilungID'] if mitarbeiter else None
                
                # Angebotsanfrage erstellen
                cursor = conn.execute('''
                    INSERT INTO Angebotsanfrage (LieferantID, ErstelltVonID, ErstellerAbteilungID, Status, Bemerkung)
                    VALUES (?, ?, ?, 'Offen', ?)
                ''', (lieferant_id, mitarbeiter_id, abteilung_id, bemerkung))
                anfrage_id = cursor.lastrowid
                
                # Positionen hinzufügen
                for i, ersatzteil_id_str in enumerate(ersatzteil_ids):
                    # Position muss mindestens ErsatzteilID oder Bestellnummer haben
                    if not ersatzteil_id_str and (i >= len(bestellnummern) or not bestellnummern[i] or not bestellnummern[i].strip()):
                        continue
                    
                    try:
                        ersatzteil_id = int(ersatzteil_id_str) if ersatzteil_id_str and ersatzteil_id_str.strip() else None
                        menge = int(mengen[i]) if i < len(mengen) and mengen[i] else 1
                        einheit = einheiten[i].strip() if i < len(einheiten) and einheiten[i] else None
                        bestellnummer = bestellnummern[i].strip() if i < len(bestellnummern) and bestellnummern[i] else None
                        bezeichnung = bezeichnungen[i].strip() if i < len(bezeichnungen) and bezeichnungen[i] else None
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
                            INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Bemerkung, Link)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (anfrage_id, ersatzteil_id, menge, einheit, bestellnummer, bezeichnung, pos_bemerkung, link))
                    except (ValueError, IndexError):
                        continue
                
                conn.commit()
                
                # Benachrichtigungen erstellen
                try:
                    from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_angebotsanfrage
                    erstelle_benachrichtigung_fuer_angebotsanfrage(anfrage_id, 'neue_angebotsanfrage', conn)
                except Exception as e:
                    print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
                
                flash('Angebotsanfrage erfolgreich erstellt.', 'success')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=anfrage_id))
                
        except Exception as e:
            flash(f'Fehler beim Erstellen: {str(e)}', 'danger')
            print(f"Angebotsanfrage neu Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    # GET: Formular anzeigen
    with get_db_connection() as conn:
        lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
        
        # Wenn Query-Parameter vorhanden, vorausgefüllte Daten laden
        vorausgefuelltes_ersatzteil = None
        if ersatzteil_id_param:
            vorausgefuelltes_ersatzteil = conn.execute('''
                SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.LieferantID
                FROM Ersatzteil e
                WHERE e.ID = ? AND e.Gelöscht = 0
            ''', (ersatzteil_id_param,)).fetchone()
            
            # Wenn kein lieferant_id_param, aber Ersatzteil hat Lieferant, diesen verwenden
            if vorausgefuelltes_ersatzteil and not lieferant_id_param:
                lieferant_id_param = vorausgefuelltes_ersatzteil['LieferantID']
    
    return render_template(
        'angebotsanfrage_neu.html',
        lieferanten=lieferanten,
        vorausgefuelltes_ersatzteil=vorausgefuelltes_ersatzteil,
        vorausgefuellter_lieferant_id=lieferant_id_param
    )


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>')
@login_required
def angebotsanfrage_detail(angebotsanfrage_id):
    """Detailansicht einer Angebotsanfrage"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Angebotsanfrage laden
        anfrage = conn.execute('''
            SELECT 
                a.*,
                l.Name AS LieferantName,
                l.Kontaktperson AS LieferantKontakt,
                l.Telefon AS LieferantTelefon,
                l.Email AS LieferantEmail,
                m.Vorname || ' ' || m.Nachname AS ErstelltVon,
                abt.Bezeichnung AS Abteilung
            FROM Angebotsanfrage a
            LEFT JOIN Lieferant l ON a.LieferantID = l.ID
            LEFT JOIN Mitarbeiter m ON a.ErstelltVonID = m.ID
            LEFT JOIN Abteilung abt ON a.ErstellerAbteilungID = abt.ID
            WHERE a.ID = ?
        ''', (angebotsanfrage_id,)).fetchone()
        
        if not anfrage:
            flash('Angebotsanfrage nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
        
        # Berechtigungsprüfung: Nur Angebote der eigenen Abteilung(en) + Unterabteilungen
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        if not is_admin:
            from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            
            if anfrage['ErstellerAbteilungID'] not in sichtbare_abteilungen:
                flash('Sie haben keine Berechtigung, diese Angebotsanfrage zu sehen.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
        
        # Positionen laden
        positionen = conn.execute('''
            SELECT 
                p.*,
                e.ID AS ErsatzteilID,
                COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
                COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
                COALESCE(p.Einheit, e.Einheit, 'Stück') AS Einheit,
                e.Preis AS AktuellerPreis,
                e.Waehrung AS AktuelleWaehrung,
                COALESCE(p.Link, e.Link) AS Link
            FROM AngebotsanfragePosition p
            LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
            WHERE p.AngebotsanfrageID = ?
            ORDER BY p.ID
        ''', (angebotsanfrage_id,)).fetchall()
        
        # PDF-Dateien aus Ordner laden
        # Dateien aus Datei-Tabelle laden
        dateien_db = get_dateien_fuer_bereich('Angebotsanfrage', angebotsanfrage_id, conn)
        
        # In das Format konvertieren, das das Template erwartet (für Rückwärtskompatibilität)
        # Aber auch die originalen Datenbankfelder beibehalten für das Template
        dateien = []
        for d in dateien_db:
            # Dateigröße aus Dateisystem ermitteln
            filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], d['Dateipfad'].replace('/', os.sep))
            file_size = 0
            modified = None
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                modified = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            # Beide Formate unterstützen: Dictionary mit allen Feldern
            datei_dict = dict(d)  # Alle Datenbankfelder kopieren
            datei_dict.update({
                'name': d['Dateiname'],
                'path': d['Dateipfad'],
                'size': file_size,
                'modified': modified,
                'id': d['ID'],
                'beschreibung': d['Beschreibung'] or ''
            })
            dateien.append(datei_dict)
        
        is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    return render_template(
        'angebotsanfrage_detail.html',
        anfrage=anfrage,
        positionen=positionen,
        dateien=dateien,
        is_admin=is_admin
    )


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/bearbeiten', methods=['POST'])
@login_required
def angebotsanfrage_bearbeiten(angebotsanfrage_id):
    """Status einer Angebotsanfrage ändern"""
    mitarbeiter_id = session.get('user_id')
    
    neuer_status = request.form.get('status')
    
    if not neuer_status:
        flash('Bitte wählen Sie einen Status aus.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert
            anfrage = conn.execute('SELECT Status FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,)).fetchone()
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Status aktualisieren und Datum setzen
            update_fields = ['Status = ?']
            params = [neuer_status, angebotsanfrage_id]
            
            if neuer_status == 'Versendet':
                update_fields.append('VersendetAm = datetime("now")')
            elif neuer_status == 'Angebot erhalten':
                update_fields.append('AngebotErhaltenAm = datetime("now")')
            
            conn.execute(f'''
                UPDATE Angebotsanfrage 
                SET {', '.join(update_fields)}
                WHERE ID = ?
            ''', params)
            conn.commit()
            
            # Benachrichtigungen erstellen
            try:
                from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_angebotsanfrage
                erstelle_benachrichtigung_fuer_angebotsanfrage(angebotsanfrage_id, 'angebotsanfrage_bearbeitet', conn)
            except Exception as e:
                print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
            
            flash(f'Status erfolgreich auf "{neuer_status}" geändert.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Ändern des Status: {str(e)}', 'danger')
        print(f"Angebotsanfrage bearbeiten Fehler: {e}")
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/position-hinzufuegen', methods=['POST'])
@login_required
def angebotsanfrage_position_hinzufuegen(angebotsanfrage_id):
    """Position zu bestehender Angebotsanfrage hinzufügen"""
    mitarbeiter_id = session.get('user_id')
    
    ersatzteil_id_str = request.form.get('ersatzteil_id', '').strip()
    ersatzteil_id = int(ersatzteil_id_str) if ersatzteil_id_str else None
    menge = request.form.get('menge', type=int) or 1
    einheit = request.form.get('einheit', '').strip() or None
    bestellnummer = request.form.get('bestellnummer', '').strip() or None
    bezeichnung = request.form.get('bezeichnung', '').strip() or None
    bemerkung = request.form.get('bemerkung', '').strip() or None
    link = request.form.get('link', '').strip() or None
    
    if not ersatzteil_id and not bestellnummer:
        flash('Bitte geben Sie entweder eine ErsatzteilID oder eine Bestellnummer ein.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert
            anfrage = conn.execute('SELECT ID FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,)).fetchone()
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Prüfe ob Position bereits vorhanden (nur wenn ErsatzteilID vorhanden)
            vorhanden = None
            if ersatzteil_id:
                vorhanden = conn.execute('''
                    SELECT ID FROM AngebotsanfragePosition
                    WHERE AngebotsanfrageID = ? AND ErsatzteilID = ?
                ''', (angebotsanfrage_id, ersatzteil_id)).fetchone()
            
            if vorhanden:
                flash('Dieses Ersatzteil ist bereits in der Angebotsanfrage enthalten.', 'warning')
            else:
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
                
                # Position hinzufügen (Link wird aus Formular oder Ersatzteil übernommen)
                conn.execute('''
                    INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Einheit, Bestellnummer, Bezeichnung, Bemerkung, Link)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (angebotsanfrage_id, ersatzteil_id, menge, einheit, bestellnummer, bezeichnung, bemerkung, link))
                conn.commit()
                flash('Position erfolgreich hinzugefügt.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Hinzufügen: {str(e)}', 'danger')
        print(f"Position hinzufügen Fehler: {e}")
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/position/<int:position_id>/bearbeiten', methods=['POST'])
@login_required
def angebotsanfrage_position_bearbeiten(angebotsanfrage_id, position_id):
    """Position in Angebotsanfrage bearbeiten"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert und im Status "Offen" ist
            anfrage = conn.execute('SELECT Status FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,)).fetchone()
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Nur im Status "Offen" bearbeitbar
            if anfrage['Status'] != 'Offen':
                flash('Positionen können nur bei offenen Anfragen bearbeitet werden.', 'warning')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            ersatzteil_id = request.form.get('ersatzteil_id', '').strip()
            bestellnummer = request.form.get('bestellnummer', '').strip()
            bezeichnung = request.form.get('bezeichnung', '').strip()
            menge = request.form.get('menge')
            einheit = request.form.get('einheit', '').strip() or None
            bemerkung = request.form.get('bemerkung', '').strip() or None
            link = request.form.get('link', '').strip() or None
            
            # Validierung
            if not bestellnummer or not bezeichnung:
                flash('Bestellnummer und Bezeichnung sind erforderlich.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            try:
                menge = int(menge)
                if menge < 1:
                    raise ValueError()
            except (ValueError, TypeError):
                flash('Ungültige Menge.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # ErsatzteilID optional
            ersatzteil_id_int = None
            if ersatzteil_id:
                try:
                    ersatzteil_id_int = int(ersatzteil_id)
                except ValueError:
                    flash('Ungültige ErsatzteilID.', 'danger')
                    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Einheit aus Formular oder Ersatzteil laden, falls nicht vorhanden
            if not einheit:
                if ersatzteil_id_int:
                    ersatzteil = conn.execute('SELECT Einheit FROM Ersatzteil WHERE ID = ?', (ersatzteil_id_int,)).fetchone()
                    if ersatzteil:
                        einheit = ersatzteil['Einheit'] if ersatzteil['Einheit'] else 'Stück'
            
            if not einheit:
                # Einheit aus bestehender Position übernehmen oder Standard
                alte_position = conn.execute('SELECT Einheit FROM AngebotsanfragePosition WHERE ID = ?', (position_id,)).fetchone()
                einheit = alte_position['Einheit'] if alte_position and alte_position['Einheit'] else 'Stück'
            
            # Position aktualisieren
            conn.execute('''
                UPDATE AngebotsanfragePosition SET
                    ErsatzteilID = ?,
                    Bestellnummer = ?,
                    Bezeichnung = ?,
                    Menge = ?,
                    Einheit = ?,
                    Bemerkung = ?,
                    Link = ?
                WHERE ID = ? AND AngebotsanfrageID = ?
            ''', (ersatzteil_id_int, bestellnummer, bezeichnung, menge, einheit, bemerkung, link, position_id, angebotsanfrage_id))
            
            conn.commit()
            flash('Position erfolgreich aktualisiert.', 'success')
    except Exception as e:
        flash(f'Fehler beim Aktualisieren: {str(e)}', 'danger')
        print(f"Position bearbeiten Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/position/<int:position_id>/artikel-erstellen', methods=['POST'])
@login_required
def angebotsanfrage_position_artikel_erstellen(angebotsanfrage_id, position_id):
    """Erstellt einen neuen Artikel aus einer Position (wenn keine ErsatzteilID vorhanden)"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert
            anfrage = conn.execute('''
                SELECT a.Status, a.LieferantID, a.ErstellerAbteilungID 
                FROM Angebotsanfrage a 
                WHERE a.ID = ?
            ''', (angebotsanfrage_id,)).fetchone()
            
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Status-Prüfung entfernt - Artikel können auch bei "Versendet" erstellt werden
            # (Status-Prüfung wurde bereits in der Template-Logik implementiert)
            
            # Position laden
            position = conn.execute('''
                SELECT ID, ErsatzteilID, Bestellnummer, Bezeichnung, Menge, Bemerkung, Link
                FROM AngebotsanfragePosition
                WHERE ID = ? AND AngebotsanfrageID = ?
            ''', (position_id, angebotsanfrage_id)).fetchone()
            
            if not position:
                flash('Position nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Prüfungen
            if position['ErsatzteilID']:
                flash('Position hat bereits eine ErsatzteilID.', 'warning')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            if not position['Bestellnummer'] or not position['Bezeichnung']:
                flash('Bestellnummer und Bezeichnung müssen vorhanden sein.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Prüfe ob Bestellnummer bereits existiert
            duplikat = conn.execute('''
                SELECT ID, Bezeichnung FROM Ersatzteil 
                WHERE Bestellnummer = ? AND Gelöscht = 0
            ''', (position['Bestellnummer'],)).fetchone()
            
            if duplikat:
                flash(f'Bestellnummer "{position["Bestellnummer"]}" ist bereits vergeben (Artikel #{duplikat["ID"]}: {duplikat["Bezeichnung"]}).', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Stammabteilung ermitteln: ErstellerAbteilungID der Anfrage oder PrimaerAbteilungID des Mitarbeiters
            stammabteilung_id = anfrage['ErstellerAbteilungID']
            if not stammabteilung_id:
                # Fallback: PrimaerAbteilungID des Mitarbeiters
                mitarbeiter = conn.execute('SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?', (mitarbeiter_id,)).fetchone()
                if mitarbeiter:
                    stammabteilung_id = mitarbeiter['PrimaerAbteilungID']
            
            # Neuen Artikel erstellen
            link = position['Link'] if 'Link' in position.keys() else None
            cursor = conn.execute('''
                INSERT INTO Ersatzteil (
                    Bestellnummer, Bezeichnung, Beschreibung, LieferantID, 
                    AktuellerBestand, Mindestbestand, Einheit, ErstelltVonID, Aktiv, Gelöscht, Link
                ) VALUES (?, ?, ?, ?, 0, 0, 'Stück', ?, 1, 0, ?)
            ''', (position['Bestellnummer'], position['Bezeichnung'], position['Bemerkung'], 
                  anfrage['LieferantID'], mitarbeiter_id, link))
            
            neuer_artikel_id = cursor.lastrowid
            
            # Stammabteilung setzen (ErsatzteilAbteilungZugriff)
            if stammabteilung_id:
                try:
                    conn.execute('''
                        INSERT INTO ErsatzteilAbteilungZugriff (ErsatzteilID, AbteilungID)
                        VALUES (?, ?)
                    ''', (neuer_artikel_id, stammabteilung_id))
                except:
                    pass  # Duplikat ignorieren
            
            # Position mit neuer ErsatzteilID aktualisieren
            conn.execute('''
                UPDATE AngebotsanfragePosition
                SET ErsatzteilID = ?
                WHERE ID = ?
            ''', (neuer_artikel_id, position_id))
            
            conn.commit()
            flash(f'Artikel #{neuer_artikel_id} erfolgreich erstellt und mit Position verknüpft.', 'success')
    except Exception as e:
        flash(f'Fehler beim Erstellen: {str(e)}', 'danger')
        print(f"Artikel aus Position erstellen Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/position/<int:position_id>/loeschen', methods=['POST'])
@login_required
def angebotsanfrage_position_loeschen(angebotsanfrage_id, position_id):
    """Position aus Angebotsanfrage löschen (nur wenn Status 'Offen')"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert und Status 'Offen' ist
            anfrage = conn.execute('SELECT Status FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,)).fetchone()
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            if anfrage['Status'] != 'Offen':
                flash('Positionen können nur bei offenen Angebotsanfragen gelöscht werden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Prüfe ob Position existiert und zur Anfrage gehört
            position = conn.execute('''
                SELECT ID FROM AngebotsanfragePosition
                WHERE ID = ? AND AngebotsanfrageID = ?
            ''', (position_id, angebotsanfrage_id)).fetchone()
            
            if not position:
                flash('Position nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Position löschen
            conn.execute('DELETE FROM AngebotsanfragePosition WHERE ID = ?', (position_id,))
            conn.commit()
            flash('Position erfolgreich gelöscht.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
        print(f"Position löschen Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/loeschen', methods=['POST'])
@login_required
def angebotsanfrage_loeschen(angebotsanfrage_id):
    """Angebotsanfrage löschen (unabhängig vom Status)"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert
            anfrage = conn.execute('''
                SELECT ErstellerAbteilungID 
                FROM Angebotsanfrage 
                WHERE ID = ?
            ''', (angebotsanfrage_id,)).fetchone()
            
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Berechtigungsprüfung: Nur Angebote der eigenen Abteilung(en) + Unterabteilungen
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            if not is_admin:
                from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
                sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
                
                if anfrage['ErstellerAbteilungID'] not in sichtbare_abteilungen:
                    flash('Sie haben keine Berechtigung, diese Angebotsanfrage zu löschen.', 'danger')
                    return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Alle Positionen löschen
            conn.execute('DELETE FROM AngebotsanfragePosition WHERE AngebotsanfrageID = ?', (angebotsanfrage_id,))
            
            # Angebotsanfrage löschen
            conn.execute('DELETE FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,))
            conn.commit()
            
            flash('Angebotsanfrage erfolgreich gelöscht.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
        print(f"Angebotsanfrage löschen Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.angebotsanfrage_liste'))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/preise-eingeben', methods=['POST'])
@login_required
def angebotsanfrage_preise_eingeben(angebotsanfrage_id):
    """Preise eingeben und in Ersatzteile übernehmen"""
    mitarbeiter_id = session.get('user_id')
    
    position_ids = request.form.getlist('position_id[]')
    preise = request.form.getlist('preis[]')
    waehrungen = request.form.getlist('waehrung[]')
    preise_uebernehmen = request.form.get('preise_uebernehmen') == 'on'
    status_abschliessen = request.form.get('status_abschliessen') == 'on'
    
    try:
        with get_db_connection() as conn:
            # Preise in Positionen speichern
            for i, position_id_str in enumerate(position_ids):
                if not position_id_str:
                    continue
                
                try:
                    position_id = int(position_id_str)
                    preis_str = preise[i] if i < len(preise) else ''
                    waehrung = waehrungen[i] if i < len(waehrungen) else 'EUR'
                    
                    preis = None
                    if preis_str and preis_str.strip():
                        preis = float(preis_str.replace(',', '.'))
                    
                    conn.execute('''
                        UPDATE AngebotsanfragePosition
                        SET Angebotspreis = ?, Angebotswaehrung = ?
                        WHERE ID = ?
                    ''', (preis, waehrung, position_id))
                except (ValueError, IndexError):
                    continue
            
            # Preise in Ersatzteile übernehmen (wenn gewünscht)
            if preise_uebernehmen:
                positionen = conn.execute('''
                    SELECT p.ErsatzteilID, p.Bestellnummer, p.Angebotspreis, p.Angebotswaehrung
                    FROM AngebotsanfragePosition p
                    WHERE p.AngebotsanfrageID = ? AND p.Angebotspreis IS NOT NULL
                ''', (angebotsanfrage_id,)).fetchall()
                
                erfolgreich = 0
                fehlgeschlagen = []
                
                for pos in positionen:
                    ersatzteil_id = pos['ErsatzteilID']
                    bestellnummer = pos['Bestellnummer']
                    
                    # Prüfe ob ErsatzteilID vorhanden ist
                    if not ersatzteil_id:
                        # Versuche Ersatzteil über Bestellnummer zu finden
                        if bestellnummer:
                            ersatzteil = conn.execute('SELECT ID FROM Ersatzteil WHERE Bestellnummer = ?', (bestellnummer,)).fetchone()
                            if ersatzteil:
                                ersatzteil_id = ersatzteil['ID']
                            else:
                                fehlgeschlagen.append(f"Bestellnummer '{bestellnummer}' nicht gefunden")
                                continue
                        else:
                            fehlgeschlagen.append("Keine ErsatzteilID und keine Bestellnummer vorhanden")
                            continue
                    
                    # Prüfe ob Ersatzteil existiert
                    ersatzteil_existiert = conn.execute('SELECT ID FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                    if not ersatzteil_existiert:
                        fehlgeschlagen.append(f"ErsatzteilID {ersatzteil_id} nicht gefunden")
                        continue
                    
                    # Preis übernehmen
                    conn.execute('''
                        UPDATE Ersatzteil
                        SET Preis = ?, Waehrung = ?, Preisstand = datetime("now")
                        WHERE ID = ?
                    ''', (pos['Angebotspreis'], pos['Angebotswaehrung'] or 'EUR', ersatzteil_id))
                    erfolgreich += 1
                
                if erfolgreich > 0:
                    flash(f'Preise erfolgreich für {erfolgreich} Ersatzteil(e) übernommen.', 'success')
                if fehlgeschlagen:
                    flash(f'{len(fehlgeschlagen)} Position(en) konnten nicht übernommen werden: {", ".join(fehlgeschlagen)}', 'warning')
            
            # Status auf Abgeschlossen setzen (wenn gewünscht)
            if status_abschliessen:
                conn.execute('''
                    UPDATE Angebotsanfrage
                    SET Status = 'Abgeschlossen'
                    WHERE ID = ?
                ''', (angebotsanfrage_id,))
                flash('Angebotsanfrage als abgeschlossen markiert.', 'success')
            
            conn.commit()
            
            # Benachrichtigungen erstellen
            try:
                from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_angebotsanfrage
                erstelle_benachrichtigung_fuer_angebotsanfrage(angebotsanfrage_id, 'angebotsanfrage_preise_eingegeben', conn)
            except Exception as e:
                print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
            
    except Exception as e:
        flash(f'Fehler beim Speichern: {str(e)}', 'danger')
        print(f"Preise eingeben Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/datei/upload', methods=['POST'])
@login_required
def angebotsanfrage_datei_upload(angebotsanfrage_id):
    """PDF-Datei für Angebotsanfrage hochladen"""
    mitarbeiter_id = session.get('user_id')
    beschreibung = request.form.get('beschreibung', '').strip()
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    
    # Nur PDF erlauben
    if not file.filename.lower().endswith('.pdf'):
        flash('Nur PDF-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    
    try:
        with get_db_connection() as conn:
            # Prüfe ob Anfrage existiert
            anfrage = conn.execute('SELECT ID FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,)).fetchone()
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Ordner erstellen
            upload_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Angebote', str(angebotsanfrage_id))
            create_upload_folder(upload_folder)
            
            # Datei speichern mit Timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            original_filename = file.filename
            file.filename = timestamp + secure_filename(original_filename)
            
            success_upload, filename, error_message = save_uploaded_file(
                file,
                upload_folder,
                allowed_extensions={'pdf'}
            )
            
            if not success_upload or error_message:
                flash(f'Fehler beim Hochladen: {error_message}', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Datenbankeintrag in Datei-Tabelle
            relative_path = f'Bestellwesen/Angebote/{angebotsanfrage_id}/{filename}'
            speichere_datei(
                bereich_typ='Angebotsanfrage',
                bereich_id=angebotsanfrage_id,
                dateiname=original_filename,
                dateipfad=relative_path,
                beschreibung=beschreibung,
                typ='PDF',
                mitarbeiter_id=mitarbeiter_id,
                conn=conn
            )
            
            flash('PDF erfolgreich hochgeladen.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Datei upload Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))


@ersatzteile_bp.route('/angebotsanfragen/datei/<path:filepath>')
@login_required
def angebotsanfrage_datei_anzeigen(filepath):
    """PDF-Datei anzeigen/herunterladen"""
    mitarbeiter_id = session.get('user_id')
    
    # Normalisiere den Pfad: Backslashes zu Forward-Slashes (für Windows-Kompatibilität)
    filepath = filepath.replace('\\', '/')
    
    # Sicherheitsprüfung: Dateipfad muss mit Bestellwesen/Angebote beginnen
    if not filepath.startswith('Bestellwesen/Angebote/'):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
    
    # Pfad für Dateisystem: Backslashes für Windows
    filepath_for_fs = filepath.replace('/', os.sep)
    full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath_for_fs)
    
    if not os.path.exists(full_path):
        flash('Datei nicht gefunden.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
    
    # Angebotsanfrage-ID aus Pfad extrahieren (Bestellwesen/Angebote/{id}/...)
    parts = filepath.split('/')
    if len(parts) >= 3:
        angebotsanfrage_id = parts[2]
        try:
            angebotsanfrage_id = int(angebotsanfrage_id)
            with get_db_connection() as conn:
                # Prüfe ob Anfrage existiert (Berechtigung)
                anfrage = conn.execute('SELECT ID FROM Angebotsanfrage WHERE ID = ?', (angebotsanfrage_id,)).fetchone()
                if not anfrage:
                    flash('Sie haben keine Berechtigung für diese Datei.', 'danger')
                    return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
        except:
            pass
    
    return send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path)
    )


@ersatzteile_bp.route('/angebotsanfragen/<int:angebotsanfrage_id>/pdf')
@login_required
def angebotsanfrage_pdf_export(angebotsanfrage_id):
    """PDF-Export für eine Angebotsanfrage mit docx-Vorlage"""
    try:
        with get_db_connection() as conn:
            content, filename, mimetype, is_pdf = generate_angebotsanfrage_pdf(angebotsanfrage_id, conn)
            
            response = make_response(content)
            response.headers['Content-Type'] = mimetype
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
    except FileNotFoundError as e:
        flash(str(e), 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
    except Exception as e:
        flash(f'Fehler beim Erstellen des Berichts: {str(e)}', 'danger')
        print(f"Angebots-Export Fehler: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
