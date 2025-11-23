"""
Ersatzteile Routes - Ersatzteilverwaltung, Lagerbuchungen, Verknüpfungen
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app, make_response
from datetime import datetime
import os
import base64
import tempfile
import subprocess
import shutil
import sys
from io import BytesIO
from werkzeug.utils import secure_filename
from . import ersatzteile_bp
from utils import get_db_connection, login_required, permission_required, get_sichtbare_abteilungen_fuer_mitarbeiter, ist_admin
from utils.firmendaten import get_firmendaten
from utils.helpers import build_sichtbarkeits_filter_query, build_ersatzteil_zugriff_filter, row_to_dict
from utils.file_handling import save_uploaded_file, validate_file_extension, create_upload_folder
from .services import (
    build_ersatzteil_liste_query, 
    get_ersatzteil_liste_filter_options, 
    get_ersatzteil_detail_data,
    create_lagerbuchung,
    create_inventur_buchung
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from docxtpl import DocxTemplate
try:
    from docx2pdf import convert
    DOCX2PDF_AVAILABLE = True
    # COM-Initialisierung für Windows
    if sys.platform == 'win32':
        try:
            import pythoncom
            COM_INITIALIZED = False
        except ImportError:
            COM_INITIALIZED = False
    else:
        COM_INITIALIZED = True
except ImportError:
    DOCX2PDF_AVAILABLE = False
    COM_INITIALIZED = False


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


def convert_docx_to_pdf(docx_path, pdf_path):
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


def safe_get(row, key, default=None):
    """Sichere Zugriff auf sqlite3.Row oder dict Objekte"""
    if row is None:
        return default
    if hasattr(row, 'get'):
        return row.get(key, default)
    else:
        # sqlite3.Row - prüfe ob Key existiert und Wert nicht None ist
        try:
            value = row[key]
            return value if value is not None else default
        except (KeyError, IndexError):
            return default


# Hilfsfunktionen wurden nach utils.py verschoben
from .utils import hat_ersatzteil_zugriff, get_datei_anzahl, allowed_file


@ersatzteile_bp.route('/')
@login_required
def ersatzteil_liste():
    """Ersatzteil-Liste mit Filtern"""
    mitarbeiter_id = session.get('user_id')
    
    # Filterparameter
    kategorie_filter = request.args.get('kategorie')
    lieferant_filter = request.args.get('lieferant')
    lagerort_filter = request.args.get('lagerort')
    lagerplatz_filter = request.args.get('lagerplatz')
    kennzeichen_filter = request.args.get('kennzeichen')
    bestandswarnung = request.args.get('bestandswarnung') == '1'
    q_filter = request.args.get('q')
    sort_by = request.args.get('sort', 'kategorie')  # Standard: Kategorie
    sort_dir = request.args.get('dir', 'asc')  # Standard: aufsteigend
    
    with get_db_connection() as conn:
        # Berechtigte Abteilungen ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Query über Service aufbauen
        query, params = build_ersatzteil_liste_query(
            mitarbeiter_id,
            sichtbare_abteilungen,
            is_admin,
            kategorie_filter=kategorie_filter,
            lieferant_filter=lieferant_filter,
            lagerort_filter=lagerort_filter,
            lagerplatz_filter=lagerplatz_filter,
            kennzeichen_filter=kennzeichen_filter,
            bestandswarnung=bestandswarnung,
            q_filter=q_filter,
            sort_by=sort_by,
            sort_dir=sort_dir
        )
        
        ersatzteile = conn.execute(query, params).fetchall()
        
        # Filter-Optionen über Service laden
        filter_options = get_ersatzteil_liste_filter_options(conn)
    
    return render_template(
        'ersatzteil_liste.html',
        ersatzteile=ersatzteile,
        kategorien=filter_options['kategorien'],
        lieferanten=filter_options['lieferanten'],
        lagerorte=filter_options['lagerorte'],
        lagerplaetze=filter_options['lagerplaetze'],
        kennzeichen_liste=filter_options['kennzeichen_liste'],
        kategorie_filter=kategorie_filter,
        lieferant_filter=lieferant_filter,
        lagerort_filter=lagerort_filter,
        lagerplatz_filter=lagerplatz_filter,
        kennzeichen_filter=kennzeichen_filter,
        bestandswarnung=bestandswarnung,
        q_filter=q_filter,
        sort_by=sort_by,
        sort_dir=sort_dir,
        is_admin=is_admin
    )


@ersatzteile_bp.route('/lagerbuchungen')
@login_required
def lagerbuchungen_liste():
    """Liste aller Lagerbuchungen mit Filtern"""
    mitarbeiter_id = session.get('user_id')
    
    # Filterparameter
    ersatzteil_filter = request.args.get('ersatzteil')
    typ_filter = request.args.get('typ')  # 'Eingang', 'Ausgang' oder 'Inventur'
    # Kein Standard-Filter mehr - alle Typen werden angezeigt wenn kein Filter gesetzt ist
    kostenstelle_filter = request.args.get('kostenstelle')
    datum_von = request.args.get('datum_von')
    datum_bis = request.args.get('datum_bis')
    # Limit: Standardmäßig aktiviert mit 200 Einträgen
    # Wenn limit_aktiv nicht im Request ist, prüfe ob andere Filter gesetzt sind
    # Wenn keine Filter gesetzt sind = erster Aufruf, dann aktiviert
    # Wenn Filter gesetzt sind aber limit_aktiv fehlt = deaktiviert
    has_any_filter = any([ersatzteil_filter, typ_filter, kostenstelle_filter, datum_von, datum_bis])
    limit_aktiv_param = request.args.get('limit_aktiv')
    if limit_aktiv_param is not None:
        limit_aktiv = limit_aktiv_param == '1'
    else:
        # Standardmäßig aktiviert beim ersten Aufruf (keine Filter)
        limit_aktiv = not has_any_filter
    limit_wert = request.args.get('limit_wert', type=int) or 200
    
    with get_db_connection() as conn:
        # Berechtigte Abteilungen ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Basis-Query
        query = '''
            SELECT 
                l.ID,
                l.Typ,
                l.Menge,
                l.Grund,
                l.Buchungsdatum,
                l.Bemerkung,
                l.ErsatzteilID,
                l.Preis,
                l.Waehrung,
                e.Bestellnummer,
                e.Bezeichnung AS ErsatzteilBezeichnung,
                m.Vorname || ' ' || m.Nachname AS VerwendetVon,
                k.Bezeichnung AS Kostenstelle,
                t.ID AS ThemaID
            FROM Lagerbuchung l
            JOIN Ersatzteil e ON l.ErsatzteilID = e.ID
            LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
            LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
            LEFT JOIN SchichtbuchThema t ON l.ThemaID = t.ID
            WHERE e.Gelöscht = 0
        '''
        params = []
        
        # Berechtigungsfilter: Nur Ersatzteile, auf die der Benutzer Zugriff hat
        query, params = build_ersatzteil_zugriff_filter(
            query,
            mitarbeiter_id,
            sichtbare_abteilungen,
            is_admin,
            params
        )
        
        # Filter anwenden
        if ersatzteil_filter:
            query += ' AND e.ID = ?'
            params.append(ersatzteil_filter)
        
        if typ_filter and typ_filter.strip():
            query += ' AND l.Typ = ?'
            params.append(typ_filter)
        
        if kostenstelle_filter:
            query += ' AND l.KostenstelleID = ?'
            params.append(kostenstelle_filter)
        
        if datum_von:
            query += ' AND DATE(l.Buchungsdatum) >= ?'
            params.append(datum_von)
        
        if datum_bis:
            query += ' AND DATE(l.Buchungsdatum) <= ?'
            params.append(datum_bis)
        
        query += ' ORDER BY COALESCE(l.Buchungsdatum, l.ErstelltAm, datetime("1970-01-01")) DESC'
        
        # Limit anwenden wenn aktiviert
        if limit_aktiv:
            query += ' LIMIT ?'
            params.append(limit_wert)
        else:
            # Standard-Limit von 500 wenn kein Limit aktiviert ist
            query += ' LIMIT 500'
        
        lagerbuchungen = conn.execute(query, params).fetchall()
        
        # Filter-Optionen laden
        # Nur Ersatzteile, auf die der Benutzer Zugriff hat
        ersatzteile_query = '''
            SELECT DISTINCT e.ID, e.Bestellnummer, e.Bezeichnung
            FROM Ersatzteil e
            JOIN Lagerbuchung l ON e.ID = l.ErsatzteilID
            WHERE e.Gelöscht = 0
        '''
        ersatzteile_params = []
        
        # Berechtigungsfilter
        ersatzteile_query, ersatzteile_params = build_ersatzteil_zugriff_filter(
            ersatzteile_query,
            mitarbeiter_id,
            sichtbare_abteilungen,
            is_admin,
            ersatzteile_params
        )
        
        ersatzteile_query += ' ORDER BY e.Bestellnummer'
        ersatzteile = conn.execute(ersatzteile_query, ersatzteile_params).fetchall()
        
        kostenstellen = conn.execute('SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    
    return render_template(
        'lagerbuchungen_liste.html',
        lagerbuchungen=lagerbuchungen,
        ersatzteile=ersatzteile,
        kostenstellen=kostenstellen,
        ersatzteil_filter=ersatzteil_filter,
        typ_filter=typ_filter,
        kostenstelle_filter=kostenstelle_filter,
        datum_von=datum_von,
        datum_bis=datum_bis,
        limit_aktiv=limit_aktiv,
        limit_wert=limit_wert
    )


@ersatzteile_bp.route('/<int:ersatzteil_id>')
@login_required
def ersatzteil_detail(ersatzteil_id):
    """Ersatzteil-Detailansicht"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Berechtigung prüfen
        if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
            flash('Sie haben keine Berechtigung, dieses Ersatzteil zu sehen.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_liste'))
        
        # Detail-Daten über Service laden
        detail_data = get_ersatzteil_detail_data(
            ersatzteil_id,
            mitarbeiter_id,
            conn,
            current_app.config['ERSATZTEIL_UPLOAD_FOLDER']
        )
        
        if not detail_data or not detail_data['ersatzteil']:
            flash('Ersatzteil nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_liste'))
        
        datei_anzahl_bilder = get_datei_anzahl(ersatzteil_id, 'bilder')
        datei_anzahl_dokumente = get_datei_anzahl(ersatzteil_id, 'dokumente')
    
    return render_template(
        'ersatzteil_detail.html',
        ersatzteil=detail_data['ersatzteil'],
        bilder=detail_data['bilder'],
        dokumente=detail_data['dokumente'],
        lagerbuchungen=detail_data['lagerbuchungen'],
        verknuepfungen=detail_data['verknuepfungen'],
        zugriffe=detail_data['zugriffe'],
        kostenstellen=detail_data['kostenstellen'],
        datei_anzahl_bilder=datei_anzahl_bilder,
        datei_anzahl_dokumente=datei_anzahl_dokumente
    )


@ersatzteile_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def ersatzteil_neu():
    """Neues Ersatzteil anlegen"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    if not is_admin:
        flash('Nur Administratoren können Ersatzteile anlegen.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    # Vorlage-Artikel laden (falls angegeben)
    vorlage_id = request.args.get('vorlage', type=int)
    vorlage = None
    vorlage_abteilungen = []
    
    # Eigene Abteilung des Benutzers ermitteln
    with get_db_connection() as conn:
        user_abteilung_row = conn.execute('SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?', (mitarbeiter_id,)).fetchone()
        user_abteilung = row_to_dict(user_abteilung_row)
        eigene_abteilung_id = user_abteilung.get('PrimaerAbteilungID') if user_abteilung else None
        
        if vorlage_id:
            vorlage = conn.execute('''
                SELECT e.*, k.Bezeichnung as KategorieBezeichnung, l.Name as LieferantName
                FROM Ersatzteil e
                LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
                LEFT JOIN Lieferant l ON e.LieferantID = l.ID
                WHERE e.ID = ? AND e.Gelöscht = 0
            ''', (vorlage_id,)).fetchone()
            
            if vorlage:
                # Abteilungen der Vorlage laden
                vorlage_abteilungen_rows = conn.execute('''
                    SELECT AbteilungID FROM ErsatzteilAbteilungZugriff
                    WHERE ErsatzteilID = ?
                ''', (vorlage_id,)).fetchall()
                vorlage_abteilungen = [row['AbteilungID'] for row in vorlage_abteilungen_rows]
        
        # Wenn keine Vorlage geladen wurde oder Vorlage keine Abteilungen hat, eigene Abteilung vorauswählen
        if not vorlage_id and eigene_abteilung_id:
            vorlage_abteilungen = [eigene_abteilung_id]
        elif vorlage_id and not vorlage_abteilungen and eigene_abteilung_id:
            # Vorlage hat keine Abteilungen, eigene Abteilung vorauswählen
            vorlage_abteilungen = [eigene_abteilung_id]
    
    if request.method == 'POST':
        bestellnummer = request.form.get('bestellnummer', '').strip()
        bezeichnung = request.form.get('bezeichnung', '').strip()
        beschreibung = request.form.get('beschreibung', '').strip()
        kategorie_id = request.form.get('kategorie_id') or None
        hersteller = request.form.get('hersteller', '').strip()
        lieferant_id = request.form.get('lieferant_id') or None
        preis = request.form.get('preis') or None
        waehrung = request.form.get('waehrung', 'EUR')
        lagerort_id = request.form.get('lagerort_id') or None
        lagerplatz_id = request.form.get('lagerplatz_id') or None
        mindestbestand = request.form.get('mindestbestand', 0) or 0
        einheit = request.form.get('einheit', 'Stück')
        abteilungen = request.form.getlist('abteilungen')
        
        # Neue Felder
        end_of_life = 1 if request.form.get('end_of_life') == 'on' else 0
        nachfolgeartikel_id_raw = request.form.get('nachfolgeartikel_id', '').strip()
        try:
            nachfolgeartikel_id = int(nachfolgeartikel_id_raw) if nachfolgeartikel_id_raw else None
        except ValueError:
            flash('Ungültige Nachfolgeartikel-ID. Bitte geben Sie eine Zahl ein.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_neu'))
        kennzeichen = request.form.get('kennzeichen', '').strip().upper()[:1] if request.form.get('kennzeichen') else None  # Nur ein Zeichen A-Z
        artikelnummer_hersteller = request.form.get('artikelnummer_hersteller', '').strip() or None
        link = request.form.get('link', '').strip() or None
        
        # Validierung
        if not bestellnummer or not bezeichnung:
            flash('Bestellnummer und Bezeichnung sind erforderlich.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_neu'))
        
        # Kennzeichen validieren (nur A-Z)
        if kennzeichen and not kennzeichen.isalpha():
            flash('Kennzeichen darf nur ein Buchstabe (A-Z) sein.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_neu'))
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Prüfe ob Bestellnummer bereits existiert
                existing = cursor.execute('SELECT ID FROM Ersatzteil WHERE Bestellnummer = ?', (bestellnummer,)).fetchone()
                if existing:
                    flash('Bestellnummer existiert bereits.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_neu'))
                
                # Prüfe ob Nachfolgeartikel existiert (falls angegeben)
                if nachfolgeartikel_id:
                    nachfolge = cursor.execute('SELECT ID FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (nachfolgeartikel_id,)).fetchone()
                    if not nachfolge:
                        flash('Nachfolgeartikel nicht gefunden.', 'danger')
                        return redirect(url_for('ersatzteile.ersatzteil_neu'))
                
                # Ersatzteil anlegen
                cursor.execute('''
                    INSERT INTO Ersatzteil (
                        Bestellnummer, Bezeichnung, Beschreibung, KategorieID, Hersteller,
                        LieferantID, Preis, Waehrung, LagerortID, LagerplatzID, Mindestbestand,
                        AktuellerBestand, Einheit, ErstelltVonID, EndOfLife, NachfolgeartikelID,
                        Kennzeichen, ArtikelnummerHersteller, Link
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
                ''', (bestellnummer, bezeichnung, beschreibung, kategorie_id, hersteller,
                      lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand, 
                      einheit, mitarbeiter_id, end_of_life, nachfolgeartikel_id, kennzeichen, artikelnummer_hersteller, link))
                
                ersatzteil_id = cursor.lastrowid
                
                # Abteilungszugriffe setzen
                for abteilung_id in abteilungen:
                    if abteilung_id:
                        try:
                            cursor.execute('''
                                INSERT INTO ErsatzteilAbteilungZugriff (ErsatzteilID, AbteilungID)
                                VALUES (?, ?)
                            ''', (ersatzteil_id, abteilung_id))
                        except:
                            pass  # Duplikat ignorieren
                
                conn.commit()
                flash('Ersatzteil erfolgreich angelegt.', 'success')
                return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
                
        except Exception as e:
            flash(f'Fehler beim Anlegen: {str(e)}', 'danger')
            print(f"Ersatzteil neu Fehler: {e}")
    
    # GET: Formular anzeigen
    with get_db_connection() as conn:
        kategorien = conn.execute('SELECT ID, Bezeichnung FROM ErsatzteilKategorie WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
        abteilungen = conn.execute('SELECT ID, Bezeichnung FROM Abteilung WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
        lagerorte = conn.execute('SELECT ID, Bezeichnung FROM Lagerort WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        lagerplaetze = conn.execute('SELECT ID, Bezeichnung FROM Lagerplatz WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
    
    return render_template(
        'ersatzteil_neu.html',
        kategorien=kategorien,
        lieferanten=lieferanten,
        abteilungen=abteilungen,
        lagerorte=lagerorte,
        lagerplaetze=lagerplaetze,
        vorlage=vorlage,
        vorlage_abteilungen=vorlage_abteilungen
    )


@ersatzteile_bp.route('/api/suche-vorlage', methods=['GET'])
@login_required
def api_suche_vorlage():
    """AJAX-Endpoint: Suche nach Ersatzteilen für Vorlage"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    with get_db_connection() as conn:
        # Admin sieht alle Artikel, normale User nur ihre sichtbaren
        if is_admin:
            ersatzteile = conn.execute('''
                SELECT ID, Bestellnummer, Bezeichnung, Hersteller, Kennzeichen
                FROM Ersatzteil
                WHERE Gelöscht = 0 
                  AND (
                    CAST(ID AS TEXT) = ? 
                    OR Bestellnummer LIKE ? 
                    OR Bezeichnung LIKE ?
                    OR Hersteller LIKE ?
                  )
                ORDER BY 
                  CASE WHEN CAST(ID AS TEXT) = ? THEN 0 ELSE 1 END,
                  CASE WHEN Bestellnummer LIKE ? THEN 0 ELSE 1 END,
                  Bezeichnung
                LIMIT 10
            ''', (query, f'%{query}%', f'%{query}%', f'%{query}%', query, f'{query}%')).fetchall()
        else:
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            if not sichtbare_abteilungen:
                return jsonify([])
            
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            ersatzteile = conn.execute(f'''
                SELECT DISTINCT e.ID, e.Bestellnummer, e.Bezeichnung, e.Hersteller, e.Kennzeichen
                FROM Ersatzteil e
                LEFT JOIN ErsatzteilAbteilungZugriff eza ON e.ID = eza.ErsatzteilID
                WHERE e.Gelöscht = 0 
                  AND (e.ErstelltVonID = ? OR eza.AbteilungID IN ({placeholders}))
                  AND (
                    CAST(e.ID AS TEXT) = ? 
                    OR e.Bestellnummer LIKE ? 
                    OR e.Bezeichnung LIKE ?
                    OR e.Hersteller LIKE ?
                  )
                ORDER BY 
                  CASE WHEN CAST(e.ID AS TEXT) = ? THEN 0 ELSE 1 END,
                  CASE WHEN e.Bestellnummer LIKE ? THEN 0 ELSE 1 END,
                  e.Bezeichnung
                LIMIT 10
            ''', [mitarbeiter_id] + sichtbare_abteilungen + [query, f'%{query}%', f'%{query}%', f'%{query}%', query, f'{query}%']).fetchall()
        
        result = []
        for e in ersatzteile:
            label = f"{e['ID']}"
            if e['Kennzeichen']:
                label += f" ({e['Kennzeichen']})"
            label += f" - {e['Bestellnummer']} - {e['Bezeichnung']}"
            if e['Hersteller']:
                label += f" ({e['Hersteller']})"
            
            result.append({
                'id': e['ID'],
                'label': label,
                'bestellnummer': e['Bestellnummer'],
                'bezeichnung': e['Bezeichnung']
            })
        
        return jsonify(result)


@ersatzteile_bp.route('/<int:ersatzteil_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def ersatzteil_bearbeiten(ersatzteil_id):
    """Ersatzteil bearbeiten"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    # Next-Parameter lesen (für Redirect nach Speichern)
    next_url = request.args.get('next') or request.form.get('next')
    
    with get_db_connection() as conn:
        # Berechtigung prüfen
        if not is_admin and not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
            flash('Sie haben keine Berechtigung, dieses Ersatzteil zu bearbeiten.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_liste'))
        
        if request.method == 'POST':
            bestellnummer = request.form.get('bestellnummer', '').strip()
            bezeichnung = request.form.get('bezeichnung', '').strip()
            beschreibung = request.form.get('beschreibung', '').strip()
            kategorie_id = request.form.get('kategorie_id') or None
            hersteller = request.form.get('hersteller', '').strip()
            lieferant_id = request.form.get('lieferant_id') or None
            preis = request.form.get('preis') or None
            waehrung = request.form.get('waehrung', 'EUR')
            lagerort_id = request.form.get('lagerort_id') or None
            lagerplatz_id = request.form.get('lagerplatz_id') or None
            mindestbestand = request.form.get('mindestbestand', 0) or 0
            einheit = request.form.get('einheit', 'Stück')
            aktiv = 1 if request.form.get('aktiv') == 'on' else 0
            abteilungen = request.form.getlist('abteilungen')
            
            # Neue Felder
            end_of_life = 1 if request.form.get('end_of_life') == 'on' else 0
            nachfolgeartikel_id_raw = request.form.get('nachfolgeartikel_id', '').strip()
            try:
                nachfolgeartikel_id = int(nachfolgeartikel_id_raw) if nachfolgeartikel_id_raw else None
            except ValueError:
                flash('Ungültige Nachfolgeartikel-ID. Bitte geben Sie eine Zahl ein.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_bearbeiten', ersatzteil_id=ersatzteil_id))
            kennzeichen = request.form.get('kennzeichen', '').strip().upper()[:1] if request.form.get('kennzeichen') else None  # Nur ein Zeichen A-Z
            artikelnummer_hersteller = request.form.get('artikelnummer_hersteller', '').strip() or None
            link = request.form.get('link', '').strip() or None
            
            if not bestellnummer or not bezeichnung:
                flash('Bestellnummer und Bezeichnung sind erforderlich.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_bearbeiten', ersatzteil_id=ersatzteil_id))
            
            # Prüfe ob Bestellnummer bereits von einem anderen Artikel verwendet wird
            duplikat = conn.execute('SELECT ID FROM Ersatzteil WHERE Bestellnummer = ? AND ID != ? AND Gelöscht = 0', 
                                   (bestellnummer, ersatzteil_id)).fetchone()
            if duplikat:
                flash(f'Bestellnummer "{bestellnummer}" wird bereits von einem anderen Artikel verwendet.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_bearbeiten', ersatzteil_id=ersatzteil_id))
            
            # Kennzeichen validieren (nur A-Z)
            if kennzeichen and not kennzeichen.isalpha():
                flash('Kennzeichen darf nur ein Buchstabe (A-Z) sein.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_bearbeiten', ersatzteil_id=ersatzteil_id))
            
            # Prüfe ob Nachfolgeartikel existiert (falls angegeben)
            if nachfolgeartikel_id:
                nachfolge = conn.execute('SELECT ID FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0 AND ID != ?', (nachfolgeartikel_id, ersatzteil_id)).fetchone()
                if not nachfolge:
                    flash('Nachfolgeartikel nicht gefunden oder ungültig.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_bearbeiten', ersatzteil_id=ersatzteil_id))
            
            try:
                # Ersatzteil aktualisieren
                conn.execute('''
                    UPDATE Ersatzteil SET
                        Bestellnummer = ?, Bezeichnung = ?, Beschreibung = ?, KategorieID = ?, Hersteller = ?,
                        LieferantID = ?, Preis = ?, Waehrung = ?, LagerortID = ?, LagerplatzID = ?,
                        Mindestbestand = ?, Einheit = ?, Aktiv = ?, EndOfLife = ?,
                        NachfolgeartikelID = ?, Kennzeichen = ?, ArtikelnummerHersteller = ?, Link = ?
                    WHERE ID = ?
                ''', (bestellnummer, bezeichnung, beschreibung, kategorie_id, hersteller,
                      lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand, 
                      einheit, aktiv, end_of_life, nachfolgeartikel_id, kennzeichen, artikelnummer_hersteller, link, ersatzteil_id))
                
                # Abteilungszugriffe aktualisieren (nur Admin)
                if is_admin:
                    conn.execute('DELETE FROM ErsatzteilAbteilungZugriff WHERE ErsatzteilID = ?', (ersatzteil_id,))
                    for abteilung_id in abteilungen:
                        if abteilung_id:
                            try:
                                conn.execute('''
                                    INSERT INTO ErsatzteilAbteilungZugriff (ErsatzteilID, AbteilungID)
                                    VALUES (?, ?)
                                ''', (ersatzteil_id, abteilung_id))
                            except:
                                pass
                
                conn.commit()
                flash('Ersatzteil erfolgreich aktualisiert.', 'success')
                # Zurück zur Artikelliste, wenn man von dort kam, sonst zur Detail-Seite
                if next_url:
                    return redirect(next_url)
                return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
                
            except Exception as e:
                flash(f'Fehler beim Aktualisieren: {str(e)}', 'danger')
                print(f"Ersatzteil bearbeiten Fehler: {e}")
        
        # GET: Formular anzeigen
        ersatzteil = conn.execute('SELECT * FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
        if not ersatzteil:
            flash('Ersatzteil nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_liste'))
        
        kategorien = conn.execute('SELECT ID, Bezeichnung FROM ErsatzteilKategorie WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
        abteilungen = conn.execute('SELECT ID, Bezeichnung FROM Abteilung WHERE Aktiv = 1 ORDER BY Bezeichnung').fetchall()
        lagerorte = conn.execute('SELECT ID, Bezeichnung FROM Lagerort WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        lagerplaetze = conn.execute('SELECT ID, Bezeichnung FROM Lagerplatz WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        zugriffe = conn.execute('SELECT AbteilungID FROM ErsatzteilAbteilungZugriff WHERE ErsatzteilID = ?', (ersatzteil_id,)).fetchall()
        zugriff_ids = [z['AbteilungID'] for z in zugriffe]
    
    return render_template(
        'ersatzteil_bearbeiten.html',
        ersatzteil=ersatzteil,
        kategorien=kategorien,
        lieferanten=lieferanten,
        abteilungen=abteilungen,
        lagerorte=lagerorte,
        lagerplaetze=lagerplaetze,
        zugriff_ids=zugriff_ids,
        next_url=next_url
    )


@ersatzteile_bp.route('/<int:ersatzteil_id>/loeschen', methods=['POST'])
@login_required
def ersatzteil_loeschen(ersatzteil_id):
    """Ersatzteil soft-delete"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    if not is_admin:
        flash('Nur Administratoren können Ersatzteile löschen.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE Ersatzteil SET Gelöscht = 1 WHERE ID = ?', (ersatzteil_id,))
            conn.commit()
        flash('Ersatzteil erfolgreich gelöscht.', 'success')
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
    
    return redirect(url_for('ersatzteile.ersatzteil_liste'))


@ersatzteile_bp.route('/lagerbuchungen/schnellbuchung', methods=['POST'])
@login_required
@permission_required('artikel_buchen')
def schnellbuchung():
    """Schnelle Lagerbuchung durch Eingabe der Ersatzteil-ID"""
    mitarbeiter_id = session.get('user_id')
    
    ersatzteil_id_raw = request.form.get('ersatzteil_id', '').strip()
    typ = request.form.get('typ')  # 'Eingang' oder 'Ausgang'
    menge = request.form.get('menge', type=int)
    grund = request.form.get('grund', '').strip()
    kostenstelle_id = request.form.get('kostenstelle_id') or None
    thema_id_raw = request.form.get('thema_id', '').strip()
    bemerkung = request.form.get('bemerkung', '').strip()
    
    # Validierung
    if not ersatzteil_id_raw:
        flash('Ersatzteil-ID ist erforderlich.', 'danger')
        return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
    
    try:
        ersatzteil_id = int(ersatzteil_id_raw)
    except ValueError:
        flash('Ungültige Ersatzteil-ID. Bitte geben Sie eine Zahl ein.', 'danger')
        return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
    
    if not typ:
        flash('Typ ist erforderlich.', 'danger')
        return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
    
    # Bei Inventur ist auch 0 erlaubt, sonst muss Menge > 0 sein
    if typ == 'Inventur':
        if menge is None or menge < 0:
            flash('Lagerstand kann nicht negativ sein.', 'danger')
            return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
    else:
        if menge is None or menge <= 0:
            flash('Menge muss größer als 0 sein.', 'danger')
            return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
    
    thema_id = None
    if thema_id_raw:
        try:
            thema_id = int(thema_id_raw)
        except ValueError:
            flash('Ungültige Thema-ID. Bitte geben Sie eine Zahl ein.', 'danger')
            return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen
            if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
            
            # Prüfe ob Ersatzteil existiert
            ersatzteil = conn.execute('SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                flash('Ersatzteil nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
            
            # Prüfe ob Thema existiert (wenn ThemaID angegeben)
            if thema_id:
                thema = conn.execute('SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0', (thema_id,)).fetchone()
                if not thema:
                    flash(f'Thema-ID {thema_id} wurde nicht gefunden oder ist nicht aktiv. Bitte überprüfen Sie die Eingabe.', 'danger')
                    return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
            
            # Lagerbuchung über Service erstellen
            success, message, neuer_bestand = create_lagerbuchung(
                ersatzteil_id=ersatzteil_id,
                typ=typ,
                menge=menge,
                grund=grund,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                thema_id=thema_id,
                kostenstelle_id=kostenstelle_id,
                bemerkung=bemerkung
            )
            
            if success:
                conn.commit()
                flash(message, 'success')
            else:
                flash(message, 'danger')
                return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
            
    except Exception as e:
        flash(f'Fehler bei der Lagerbuchung: {str(e)}', 'danger')
        print(f"Schnellbuchung Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.lagerbuchungen_liste'))


@ersatzteile_bp.route('/<int:ersatzteil_id>/lagerbuchung', methods=['POST'])
@login_required
@permission_required('artikel_buchen')
def lagerbuchung(ersatzteil_id):
    """Lagerbuchung durchführen (Eingang/Ausgang)"""
    mitarbeiter_id = session.get('user_id')
    
    typ = request.form.get('typ')  # 'Eingang' oder 'Ausgang'
    menge = request.form.get('menge', type=int)
    grund = request.form.get('grund', '').strip()
    kostenstelle_id = request.form.get('kostenstelle_id') or None
    thema_id_raw = request.form.get('thema_id', '').strip()
    thema_id = None
    if thema_id_raw:
        try:
            thema_id = int(thema_id_raw)
        except ValueError:
            flash('Ungültige Thema-ID. Bitte geben Sie eine Zahl ein.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    bemerkung = request.form.get('bemerkung', '').strip()
    
    if not typ:
        flash('Typ ist erforderlich.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    if menge is None:
        flash('Menge ist erforderlich.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    # Bei Inventur ist auch 0 erlaubt, sonst muss Menge > 0 sein
    if typ == 'Inventur':
        if menge < 0:
            flash('Lagerstand kann nicht negativ sein.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    else:
        if menge <= 0:
            flash('Menge muss größer als 0 sein.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen
            if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            # Prüfe ob Thema existiert (wenn ThemaID angegeben)
            if thema_id:
                thema = conn.execute('SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0', (thema_id,)).fetchone()
                if not thema:
                    flash(f'Thema-ID {thema_id} wurde nicht gefunden oder ist nicht aktiv. Bitte überprüfen Sie die Eingabe.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
            
            # Aktuellen Bestand ermitteln
            ersatzteil = conn.execute('SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                flash('Ersatzteil nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            # Lagerbuchung über Service erstellen
            success, message, neuer_bestand = create_lagerbuchung(
                ersatzteil_id=ersatzteil_id,
                typ=typ,
                menge=menge,
                grund=grund,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                thema_id=thema_id,
                kostenstelle_id=kostenstelle_id,
                bemerkung=bemerkung
            )
            
            if success:
                conn.commit()
                flash(message, 'success')
            else:
                flash(message, 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
            
    except Exception as e:
        flash(f'Fehler bei der Lagerbuchung: {str(e)}', 'danger')
        print(f"Lagerbuchung Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/thema/<int:thema_id>/verknuepfen', methods=['POST'])
@login_required
def thema_verknuepfen(thema_id):
    """Ersatzteil mit Thema verknüpfen (mit automatischer Lagerbuchung)"""
    mitarbeiter_id = session.get('user_id')
    
    ersatzteil_id = request.form.get('ersatzteil_id', type=int)
    menge = request.form.get('menge', type=int)
    bemerkung = request.form.get('bemerkung', '').strip()
    kostenstelle_id = request.form.get('kostenstelle_id') or None
    
    if not ersatzteil_id or not menge or menge <= 0:
        flash('Ersatzteil und Menge sind erforderlich.', 'danger')
        return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen
            if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            # Prüfe ob Thema existiert
            thema = conn.execute('SELECT ID FROM SchichtbuchThema WHERE ID = ?', (thema_id,)).fetchone()
            if not thema:
                flash('Thema nicht gefunden.', 'danger')
                return redirect(url_for('schichtbuch.themaliste'))
            
            # Aktuellen Bestand prüfen
            ersatzteil = conn.execute('SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                flash('Ersatzteil nicht gefunden.', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            # Automatische Lagerbuchung (Ausgang) mit Thema-Verknüpfung über Service
            success, message, neuer_bestand = create_lagerbuchung(
                ersatzteil_id=ersatzteil_id,
                typ='Ausgang',
                menge=menge,
                grund=f'Verwendung für Thema {thema_id}',
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                thema_id=thema_id,
                kostenstelle_id=kostenstelle_id,
                bemerkung=bemerkung
            )
            
            if success:
                conn.commit()
                flash(f'Ersatzteil erfolgreich zugeordnet. Bestand reduziert um {menge}.', 'success')
            else:
                flash(message, 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
    except Exception as e:
        flash(f'Fehler bei der Verknüpfung: {str(e)}', 'danger')
        print(f"Thema verknüpfen Fehler: {e}")
    
    return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))


@ersatzteile_bp.route('/inventurliste')
@login_required
def inventurliste():
    """Inventurliste - Gruppiert nach Lagerort + Lagerplatz, sortiert nach Artikel-ID"""
    mitarbeiter_id = session.get('user_id')
    
    # Filterparameter aus der URL lesen
    lagerort_filter = request.args.get('lagerort')
    lagerplatz_filter = request.args.get('lagerplatz')
    
    with get_db_connection() as conn:
        # Berechtigte Abteilungen ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Verfügbare Lagerorte und Lagerplätze für Filter laden
        lagerorte = conn.execute('SELECT ID, Bezeichnung FROM Lagerort ORDER BY Bezeichnung').fetchall()
        lagerplaetze = conn.execute('SELECT ID, Bezeichnung FROM Lagerplatz ORDER BY Bezeichnung').fetchall()
        
        # Query für Inventurliste: Gruppiert nach Lagerort + Lagerplatz, sortiert nach Artikel-ID
        query = '''
            SELECT 
                e.ID,
                e.Bestellnummer,
                e.Bezeichnung,
                e.Hersteller,
                e.AktuellerBestand,
                e.Mindestbestand,
                e.Einheit,
                e.EndOfLife,
                e.Aktiv,
                e.Kennzeichen,
                k.Bezeichnung AS Kategorie,
                lo.Bezeichnung AS LagerortName,
                lo.ID AS LagerortID,
                lp.Bezeichnung AS LagerplatzName,
                lp.ID AS LagerplatzID,
                CASE 
                    WHEN lo.Bezeichnung IS NULL THEN 'Ohne Lagerort'
                    ELSE lo.Bezeichnung 
                END AS SortLagerort,
                CASE 
                    WHEN lp.Bezeichnung IS NULL THEN 'Ohne Lagerplatz'
                    ELSE lp.Bezeichnung 
                END AS SortLagerplatz
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
            LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
            WHERE e.Gelöscht = 0 AND e.Aktiv = 1
        '''
        params = []
        
        # Berechtigungsfilter
        query, params = build_ersatzteil_zugriff_filter(
            query,
            mitarbeiter_id,
            sichtbare_abteilungen,
            is_admin,
            params
        )
        
        # Lagerort-Filter
        if lagerort_filter:
            query += ' AND lo.ID = ?'
            params.append(lagerort_filter)
        
        # Lagerplatz-Filter
        if lagerplatz_filter:
            query += ' AND lp.ID = ?'
            params.append(lagerplatz_filter)
        
        # Sortierung: Erst nach Lagerort, dann Lagerplatz, dann Artikel-ID
        query += '''
            ORDER BY 
                SortLagerort ASC,
                SortLagerplatz ASC,
                e.ID ASC
        '''
        
        ersatzteile = conn.execute(query, params).fetchall()
        
        # Daten für Template gruppieren
        inventur_gruppiert = {}
        for ersatzteil in ersatzteile:
            lagerort_key = ersatzteil['SortLagerort']
            lagerplatz_key = ersatzteil['SortLagerplatz']
            
            if lagerort_key not in inventur_gruppiert:
                inventur_gruppiert[lagerort_key] = {}
            
            if lagerplatz_key not in inventur_gruppiert[lagerort_key]:
                inventur_gruppiert[lagerort_key][lagerplatz_key] = []
            
            inventur_gruppiert[lagerort_key][lagerplatz_key].append(ersatzteil)
    
    return render_template('inventurliste.html', 
                         inventur_gruppiert=inventur_gruppiert,
                         lagerorte=lagerorte,
                         lagerplaetze=lagerplaetze,
                         lagerort_filter=lagerort_filter,
                         lagerplatz_filter=lagerplatz_filter)


@ersatzteile_bp.route('/inventurliste/buchung', methods=['POST'])
@login_required
@permission_required('artikel_buchen')
def inventurliste_buchung():
    """Inventur-Buchung direkt aus der Inventurliste"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        ersatzteil_id = request.json.get('ersatzteil_id')
        neuer_bestand = request.json.get('neuer_bestand')
        
        if not ersatzteil_id or neuer_bestand is None:
            return jsonify({'success': False, 'message': 'Ersatzteil-ID und neuer Bestand sind erforderlich.'}), 400
        
        try:
            ersatzteil_id = int(ersatzteil_id)
            neuer_bestand = float(neuer_bestand)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Ungültige Werte für Ersatzteil-ID oder Bestand.'}), 400
        
        if neuer_bestand < 0:
            return jsonify({'success': False, 'message': 'Bestand kann nicht negativ sein.'}), 400
        
        with get_db_connection() as conn:
            # Berechtigung prüfen
            if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                return jsonify({'success': False, 'message': 'Sie haben keine Berechtigung für dieses Ersatzteil.'}), 403
            
            # Prüfe ob Ersatzteil existiert
            ersatzteil = conn.execute('SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                return jsonify({'success': False, 'message': 'Ersatzteil nicht gefunden.'}), 404
            
            # Inventur-Buchung über Service erstellen
            success, message = create_inventur_buchung(
                ersatzteil_id=ersatzteil_id,
                neuer_bestand=neuer_bestand,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                bemerkung=f'Inventur: Bestand von {ersatzteil["AktuellerBestand"]} auf {neuer_bestand} geändert'
            )
            
            if not success:
                return jsonify({'success': False, 'message': message}), 400
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Inventur erfolgreich durchgeführt. Neuer Bestand: {neuer_bestand}',
                'neuer_bestand': neuer_bestand,
                'alter_bestand': aktueller_bestand
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler bei der Inventur-Buchung: {str(e)}'}), 500


@ersatzteile_bp.route('/api/ersatzteil/<int:ersatzteil_id>')
@login_required
def api_ersatzteil_info(ersatzteil_id):
    """API-Endpunkt: Gibt Ersatzteil-Informationen zurück (für AJAX)"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Berechtigte Abteilungen ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            
            # Ersatzteil laden
            query = '''
                SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.Preis, e.Waehrung, e.AktuellerBestand, e.Einheit, e.Link
                FROM Ersatzteil e
                WHERE e.ID = ? AND e.Gelöscht = 0
            '''
            params = [ersatzteil_id]
            
            # Berechtigungsfilter
            if not is_admin:
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    query += f'''
                        AND (
                            e.ErstelltVonID = ? OR
                            e.ID IN (
                                SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                                WHERE AbteilungID IN ({placeholders})
                            )
                        )
                    '''
                    params.append(mitarbeiter_id)
                    params.extend(sichtbare_abteilungen)
                else:
                    query += ' AND e.ErstelltVonID = ?'
                    params.append(mitarbeiter_id)
            
            ersatzteil = conn.execute(query, params).fetchone()
            
            if ersatzteil:
                return jsonify({
                    'success': True,
                    'id': ersatzteil['ID'],
                    'bestellnummer': ersatzteil['Bestellnummer'],
                    'bezeichnung': ersatzteil['Bezeichnung'],
                    'preis': float(ersatzteil['Preis']) if ersatzteil['Preis'] else None,
                    'waehrung': ersatzteil['Waehrung'] or 'EUR',
                    'bestand': ersatzteil['AktuellerBestand'] or 0,
                    'einheit': ersatzteil['Einheit'] or '',
                    'link': ersatzteil['Link'] if 'Link' in ersatzteil.keys() else None
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Ersatzteil nicht gefunden oder keine Berechtigung'
                }), 404
                
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Fehler: {str(e)}'
        }), 500




@ersatzteile_bp.route('/api/ersatzteile/alle')
@login_required
def api_ersatzteile_alle():
    """API: Alle Ersatzteile abrufen (mit Berechtigungsfilter)"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Berechtigte Abteilungen ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            
            # Ersatzteile laden
            query = '''
                SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.Preis, e.Waehrung, e.AktuellerBestand, e.Einheit
                FROM Ersatzteil e
                WHERE e.Gelöscht = 0 AND e.Aktiv = 1
            '''
            params = []
            
            # Berechtigungsfilter
            if not is_admin:
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    query += f'''
                        AND (
                            e.ErstelltVonID = ? OR
                            e.ID IN (
                                SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                                WHERE AbteilungID IN ({placeholders})
                            )
                        )
                    '''
                    params.append(mitarbeiter_id)
                    params.extend(sichtbare_abteilungen)
                else:
                    query += ' AND e.ErstelltVonID = ?'
                    params.append(mitarbeiter_id)
            
            query += ' ORDER BY e.Bestellnummer, e.Bezeichnung'
            
            ersatzteile = conn.execute(query, params).fetchall()
            
            result = []
            for e in ersatzteile:
                result.append({
                    'id': e['ID'],
                    'bestellnummer': e['Bestellnummer'],
                    'bezeichnung': e['Bezeichnung'],
                    'preis': float(e['Preis']) if e['Preis'] else None,
                    'waehrung': e['Waehrung'] or 'EUR',
                    'bestand': e['AktuellerBestand'] or 0,
                    'einheit': e['Einheit'] or ''
                })
            
            return jsonify({
                'success': True,
                'ersatzteile': result
            })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Fehler in api_ersatzteile_alle: {e}")
        print(error_trace)
        return jsonify({
            'success': False,
            'message': f'Fehler: {str(e)}',
            'trace': error_trace
        }), 500


@ersatzteile_bp.route('/suche')
@login_required
def suche_artikel():
    """Suche nach Artikelnummer (Bestellnummer oder ID)"""
    mitarbeiter_id = session.get('user_id')
    artikelnummer = request.args.get('artikelnummer', '').strip()
    
    if artikelnummer:
        try:
            with get_db_connection() as conn:
                # Berechtigte Abteilungen ermitteln
                sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
                is_admin = 'admin' in session.get('user_berechtigungen', [])
                
                # Zuerst versuchen nach Bestellnummer zu suchen
                query = '''
                    SELECT e.ID
                    FROM Ersatzteil e
                    WHERE e.Gelöscht = 0 AND e.Bestellnummer = ?
                '''
                params = [artikelnummer]
                
                # Berechtigungsfilter
                if not is_admin:
                    if sichtbare_abteilungen:
                        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                        query += f'''
                            AND (
                                e.ErstelltVonID = ? OR
                                e.ID IN (
                                    SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                                    WHERE AbteilungID IN ({placeholders})
                                )
                            )
                        '''
                        params.append(mitarbeiter_id)
                        params.extend(sichtbare_abteilungen)
                    else:
                        # Nur selbst erstellte Artikel
                        query += ' AND e.ErstelltVonID = ?'
                        params.append(mitarbeiter_id)
                
                ersatzteil = conn.execute(query, params).fetchone()
                
                # Wenn nicht gefunden, versuche nach ID zu suchen
                if not ersatzteil:
                    try:
                        artikelnummer_int = int(artikelnummer)
                        query_id = '''
                            SELECT e.ID
                            FROM Ersatzteil e
                            WHERE e.Gelöscht = 0 AND e.ID = ?
                        '''
                        params_id = [artikelnummer_int]
                        
                        # Berechtigungsfilter
                        if not is_admin:
                            if sichtbare_abteilungen:
                                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                                query_id += f'''
                                    AND (
                                        e.ErstelltVonID = ? OR
                                        e.ID IN (
                                            SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                                            WHERE AbteilungID IN ({placeholders})
                                        )
                                    )
                                '''
                                params_id.append(mitarbeiter_id)
                                params_id.extend(sichtbare_abteilungen)
                            else:
                                # Nur selbst erstellte Artikel
                                query_id += ' AND e.ErstelltVonID = ?'
                                params_id.append(mitarbeiter_id)
                        
                        ersatzteil = conn.execute(query_id, params_id).fetchone()
                    except ValueError:
                        pass  # Keine gültige ID
                
                if ersatzteil:
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil['ID']))
                else:
                    flash('Artikelnummer nicht gefunden oder Sie haben keine Berechtigung.', 'danger')
        except Exception as e:
            flash(f'Fehler bei der Suche: {str(e)}', 'danger')
    
    return render_template('ersatzteil_suche.html')




def allowed_file(filename):
    """Prüft ob Dateityp erlaubt ist"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@ersatzteile_bp.route('/<int:ersatzteil_id>/bild/upload', methods=['POST'])
@login_required
def bild_upload(ersatzteil_id):
    """Bild für Ersatzteil hochladen"""
    mitarbeiter_id = session.get('user_id')
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    if file and allowed_file(file.filename):
        try:
            with get_db_connection() as conn:
                # Berechtigung prüfen
                if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                    flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_liste'))
                
                # Ordner erstellen
                upload_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), 'bilder')
                create_upload_folder(upload_folder)
                
                # Datei speichern mit Timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                original_filename = file.filename
                # Temporärer Dateiname mit Timestamp
                file.filename = timestamp + secure_filename(original_filename)
                
                filename, error_message = save_uploaded_file(
                    file,
                    upload_folder,
                    allowed_extensions=current_app.config['ALLOWED_EXTENSIONS']
                )
                
                if error_message:
                    flash(f'Fehler beim Hochladen: {error_message}', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
                
                # Datenbankeintrag - Pfad mit Forward-Slashes für URLs
                relative_path = f'Ersatzteile/{ersatzteil_id}/bilder/{filename}'
                conn.execute('''
                    INSERT INTO ErsatzteilBild (ErsatzteilID, Dateiname, Dateipfad)
                    VALUES (?, ?, ?)
                ''', (ersatzteil_id, original_filename, relative_path))
                conn.commit()
                
                flash('Bild erfolgreich hochgeladen.', 'success')
        except Exception as e:
            flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
            print(f"Bild upload Fehler: {e}")
    else:
        flash('Dateityp nicht erlaubt.', 'danger')
    
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/<int:ersatzteil_id>/dokument/upload', methods=['POST'])
@login_required
def dokument_upload(ersatzteil_id):
    """Dokument für Ersatzteil hochladen"""
    mitarbeiter_id = session.get('user_id')
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    file = request.files['file']
    typ = request.form.get('typ', '').strip()
    
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    if file and allowed_file(file.filename):
        try:
            with get_db_connection() as conn:
                # Berechtigung prüfen
                if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                    flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_liste'))
                
                # Ordner erstellen
                upload_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), 'dokumente')
                create_upload_folder(upload_folder)
                
                # Datei speichern mit Timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                original_filename = file.filename
                # Temporärer Dateiname mit Timestamp
                file.filename = timestamp + secure_filename(original_filename)
                
                filename, error_message = save_uploaded_file(
                    file,
                    upload_folder,
                    allowed_extensions=current_app.config['ALLOWED_EXTENSIONS']
                )
                
                if error_message:
                    flash(f'Fehler beim Hochladen: {error_message}', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
                
                # Datenbankeintrag - Pfad mit Forward-Slashes für URLs
                relative_path = f'Ersatzteile/{ersatzteil_id}/dokumente/{filename}'
                conn.execute('''
                    INSERT INTO ErsatzteilDokument (ErsatzteilID, Dateiname, Dateipfad, Typ)
                    VALUES (?, ?, ?, ?)
                ''', (ersatzteil_id, original_filename, relative_path, typ))
                conn.commit()
                
                flash('Dokument erfolgreich hochgeladen.', 'success')
        except Exception as e:
            flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
            print(f"Dokument upload Fehler: {e}")
    else:
        flash('Dateityp nicht erlaubt.', 'danger')
    
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/<int:ersatzteil_id>/bild/<int:bild_id>/loeschen', methods=['POST'])
@login_required
def bild_loeschen(ersatzteil_id, bild_id):
    """Bild löschen"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    if not is_admin:
        flash('Nur Administratoren können Bilder löschen.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    try:
        with get_db_connection() as conn:
            bild = conn.execute('SELECT Dateipfad FROM ErsatzteilBild WHERE ID = ? AND ErsatzteilID = ?', (bild_id, ersatzteil_id)).fetchone()
            if bild:
                # Datei löschen
                filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], bild['Dateipfad'])
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                # Datenbankeintrag löschen
                conn.execute('DELETE FROM ErsatzteilBild WHERE ID = ?', (bild_id,))
                conn.commit()
                flash('Bild erfolgreich gelöscht.', 'success')
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
    
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/<int:ersatzteil_id>/dokument/<int:dokument_id>/loeschen', methods=['POST'])
@login_required
def dokument_loeschen(ersatzteil_id, dokument_id):
    """Dokument löschen"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    if not is_admin:
        flash('Nur Administratoren können Dokumente löschen.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    try:
        with get_db_connection() as conn:
            dokument = conn.execute('SELECT Dateipfad FROM ErsatzteilDokument WHERE ID = ? AND ErsatzteilID = ?', (dokument_id, ersatzteil_id)).fetchone()
            if dokument:
                # Datei löschen
                filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], dokument['Dateipfad'])
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                # Datenbankeintrag löschen
                conn.execute('DELETE FROM ErsatzteilDokument WHERE ID = ?', (dokument_id,))
                conn.commit()
                flash('Dokument erfolgreich gelöscht.', 'success')
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
    
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/datei/<path:filepath>')
@login_required
def datei_anzeigen(filepath):
    """Datei anzeigen/herunterladen"""
    mitarbeiter_id = session.get('user_id')
    
    # Pfad normalisieren: Backslashes zu Forward-Slashes konvertieren (für Windows-Kompatibilität)
    filepath = filepath.replace('\\', '/')
    
    # Sicherheitsprüfung: Dateipfad muss mit Ersatzteile beginnen
    if not filepath.startswith('Ersatzteile/'):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    # Für Dateisystem: Backslashes für Windows verwenden
    filepath_fs = filepath.replace('/', os.sep)
    full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath_fs)
    
    if not os.path.exists(full_path):
        flash('Datei nicht gefunden.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    # Ersatzteil-ID aus Pfad extrahieren
    parts = filepath.split('/')
    if len(parts) >= 2:
        ersatzteil_id = parts[1]
        try:
            ersatzteil_id = int(ersatzteil_id)
            with get_db_connection() as conn:
                if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                    flash('Sie haben keine Berechtigung für diese Datei.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_liste'))
        except:
            pass
    
    return send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path)
    )


# ========== Angebotsanfragen ==========

def get_bestellung_dateien(bestellung_id):
    """Lädt alle PDF-Dateien für eine Bestellung"""
    dateien = []
    try:
        bestellung_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], 'Bestellungen', str(bestellung_id))
        if os.path.exists(bestellung_folder):
            for filename in os.listdir(bestellung_folder):
                filepath = os.path.join(bestellung_folder, filename)
                if os.path.isfile(filepath) and filename.lower().endswith('.pdf'):
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
        print(f"Fehler beim Laden der Bestellungs-Dateien: {e}")
    return dateien


# ========== Bestellungen ==========

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
                            datei_typ = 'pdf'
                        elif file_ext.endswith(('.jpeg', '.jpg')):
                            datei_typ = 'jpeg'
                        elif file_ext.endswith('.png'):
                            datei_typ = 'png'
                        else:
                            datei_typ = 'unknown'
                        
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime),
                            'typ': datei_typ
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Lieferschein-Ordners: {e}")
    
    return dateien


# ========== Wareneingang ==========
@ersatzteile_bp.route('/wareneingang')
@login_required
@permission_required('artikel_buchen')
def wareneingang():
    """Übersichtsseite für Wareneingang - Liste aller bestellten Bestellungen"""
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
            # Standard: Erledigt ausschließen
            query += " AND b.Status != 'Erledigt'"
        
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
        
        # PDF-Dateien aus Ordner laden
        dateien = get_bestellung_dateien(bestellung_id)
        
        # Auftragsbestätigungen laden (nur wenn Status "Bestellt" oder später)
        auftragsbestätigungen = []
        lieferscheine = []
        if bestellung['Status'] in ['Bestellt', 'Teilweise erhalten', 'Erhalten', 'Erledigt']:
            auftragsbestätigungen = get_auftragsbestätigung_dateien(bestellung_id)
            # Lieferscheine auch laden, wenn Auftragsbestätigungen angezeigt werden
            lieferscheine = get_lieferschein_dateien(bestellung_id)
        
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
        kann_freigabebemerkung_bearbeiten=kann_freigabebemerkung_bearbeiten
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
                    INSERT INTO Bestellung (LieferantID, ErstelltVonID, ErstellerAbteilungID, Status, Bemerkung)
                    VALUES (?, ?, ?, 'Erstellt', ?)
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
                    INSERT INTO Bestellung (AngebotsanfrageID, LieferantID, ErstelltVonID, ErstellerAbteilungID, Status, Bemerkung)
                    VALUES (?, ?, ?, ?, 'Erstellt', ?)
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
            SET Status = ?, FreigegebenAm = datetime('now'), FreigegebenVonID = ?, Unterschrift = ?
            WHERE ID = ?
        ''', ('Freigegeben', mitarbeiter_id, unterschrift, bestellung_id))
        conn.commit()
        
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
            SET Status = ?, BestelltAm = datetime('now'), BestelltVonID = ?
            WHERE ID = ?
        ''', ('Bestellt', mitarbeiter_id, bestellung_id))
        conn.commit()
        
        # Benachrichtigungen erstellen
        try:
            from utils.benachrichtigungen import erstelle_benachrichtigung_fuer_bestellung
            erstelle_benachrichtigung_fuer_bestellung(bestellung_id, 'bestellung_bestellt', conn)
        except Exception as e:
            print(f"Fehler beim Erstellen von Benachrichtigungen: {e}")
        
        flash('Bestellung wurde als bestellt markiert.', 'success')
    
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
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Bestellung laden
            bestellung = conn.execute("""
                SELECT 
                    b.*,
                    l.Name AS LieferantName,
                    l.Strasse AS LieferantStrasse,
                    l.PLZ AS LieferantPLZ,
                    l.Ort AS LieferantOrt,
                    l.Telefon AS LieferantTelefon,
                    l.Email AS LieferantEmail,
                    m1.Vorname || ' ' || m1.Nachname AS ErstelltVon,
                    m1.Email AS ErstelltVonEmail,
                    m1.Handynummer AS ErstelltVonHandy,
                    m2.Vorname || ' ' || m2.Nachname AS FreigegebenVon,
                    m3.Vorname || ' ' || m3.Nachname AS BestelltVon,
                    abt.Bezeichnung AS FreigegebenVonAbteilung
                FROM Bestellung b
                LEFT JOIN Lieferant l ON b.LieferantID = l.ID
                LEFT JOIN Mitarbeiter m1 ON b.ErstelltVonID = m1.ID
                LEFT JOIN Mitarbeiter m2 ON b.FreigegebenVonID = m2.ID
                LEFT JOIN Mitarbeiter m3 ON b.BestelltVonID = m3.ID
                LEFT JOIN Abteilung abt ON m2.PrimaerAbteilungID = abt.ID
                WHERE b.ID = ?
            """, (bestellung_id,)).fetchone()
            
            if not bestellung:
                flash('Bestellung nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_liste'))
            
            if bestellung['Status'] not in ['Freigegeben', 'Bestellt']:
                flash('PDF kann nur für freigegebene oder bestellte Bestellungen generiert werden.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
            
            # Positionen laden
            positionen = conn.execute("""
                SELECT 
                    p.*,
                    e.ID AS ErsatzteilID,
                    COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
                    COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
                    COALESCE(e.Einheit, 'Stück') AS Einheit
                FROM BestellungPosition p
                LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
                WHERE p.BestellungID = ?
                ORDER BY p.ID
            """, (bestellung_id,)).fetchall()
            
            # Firmendaten laden
            firmendaten = get_firmendaten()
            
            # Template-Pfad
            template_path = os.path.join(current_app.root_path, 'templates', 'reports', 'bestellung_template.docx')
            if not os.path.exists(template_path):
                flash('Bestellungsvorlage nicht gefunden. Bitte wenden Sie sich an den Administrator.', 'danger')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
            
            # Template laden
            doc = DocxTemplate(template_path)
            
            # Datum formatieren
            datum = ''
            if bestellung['ErstelltAm']:
                try:
                    datum = datetime.strptime(bestellung['ErstelltAm'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                except:
                    datum = bestellung['ErstelltAm'][:10] if bestellung['ErstelltAm'] else ''
            
            freigabe_datum = ''
            freigegeben_am = safe_get(bestellung, 'FreigegebenAm')
            if freigegeben_am:
                try:
                    freigabe_datum = datetime.strptime(freigegeben_am, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
                except:
                    freigabe_datum = freigegeben_am[:16] if freigegeben_am else ''
            
            # Kontaktdaten des Erstellers zusammenstellen
            kontakt_details = []
            erstellt_von_email = safe_get(bestellung, 'ErstelltVonEmail')
            erstellt_von_handy = safe_get(bestellung, 'ErstelltVonHandy')
            if erstellt_von_email:
                kontakt_details.append(f"E-Mail: {erstellt_von_email}")
            if erstellt_von_handy:
                kontakt_details.append(f"Tel: {erstellt_von_handy}")
            kontakt_text = ' | '.join(kontakt_details) if kontakt_details else ''
            
            # Positionen für Template vorbereiten mit Gesamtpreis
            positionen_liste = []
            gesamtbetrag = 0
            waehrung = 'EUR'
            
            for idx, pos in enumerate(positionen, 1):
                artikel_nr = pos['Bestellnummer'] or '-'
                bezeichnung = pos['Bezeichnung'] or '-'
                menge_val = pos['Menge'] if pos['Menge'] else 0
                preis_val = pos['Preis'] if pos['Preis'] else 0
                gesamt_preis = menge_val * preis_val
                gesamtbetrag += gesamt_preis
                
                pos_waehrung = safe_get(pos, 'Waehrung')
                if pos_waehrung:
                    waehrung = pos_waehrung
                
                einheit = safe_get(pos, 'Einheit', 'Stück')
                # Menge formatieren: Ganze Zahlen ohne Kommastellen, mit Einheit
                if menge_val == int(menge_val):
                    menge_text = f"{int(menge_val)} {einheit}"
                else:
                    menge_text = f"{menge_val} {einheit}"
                
                positionen_liste.append({
                    'position': idx,
                    'artikelnummer': artikel_nr,
                    'bezeichnung': bezeichnung,
                    'menge': menge_text,
                    'preis': f"{preis_val:.2f}",
                    'gesamtpreis': f"{gesamt_preis:.2f}",
                    'waehrung': waehrung
                })
            
            # Unterschrift als Bild vorbereiten (falls vorhanden)
            unterschrift_img = None
            tmp_img_path = None
            unterschrift_data_raw = safe_get(bestellung, 'Unterschrift')
            if unterschrift_data_raw:
                try:
                    from docxtpl import InlineImage
                    from docx.shared import Mm
                    
                    unterschrift_data = unterschrift_data_raw
                    if unterschrift_data.startswith('data:image'):
                        unterschrift_data = unterschrift_data.split(',')[1] if ',' in unterschrift_data else unterschrift_data
                    
                    img_data = base64.b64decode(unterschrift_data)
                    
                    # Temporäres Bild speichern für InlineImage
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
                        tmp_img.write(img_data)
                        tmp_img_path = os.path.abspath(tmp_img.name)  # Absoluten Pfad verwenden
                    
                    # Prüfen ob Datei existiert und lesbar ist
                    if not os.path.exists(tmp_img_path):
                        raise Exception(f"Temporäres Bild konnte nicht erstellt werden: {tmp_img_path}")
                    
                    # Dateigröße prüfen
                    file_size = os.path.getsize(tmp_img_path)
                    if file_size == 0:
                        raise Exception(f"Temporäres Bild ist leer: {tmp_img_path}")
                    
                    # InlineImage erstellen (Breite in mm, Höhe wird automatisch angepasst)
                    # Verwende Mm() für die Breite
                    unterschrift_img = InlineImage(doc, tmp_img_path, width=Mm(80))  # 80mm Breite
                    
                    if current_app.config.get('DEBUG'):
                        print(f"Unterschrift erfolgreich vorbereitet: {tmp_img_path}, Größe: {len(img_data)} bytes")
                except Exception as e:
                    print(f"Fehler beim Vorbereiten der Unterschrift: {e}")
                    import traceback
                    traceback.print_exc()
                    unterschrift_img = None
                    # Temporäres Bild aufräumen bei Fehler
                    if tmp_img_path and os.path.exists(tmp_img_path):
                        try:
                            os.unlink(tmp_img_path)
                        except:
                            pass
                    tmp_img_path = None
            
            # Footer-Informationen zusammenstellen
            footer_lines = []
            if firmendaten:
                if safe_get(firmendaten, 'Geschaeftsfuehrer'):
                    footer_lines.append(f"Geschäftsführer: {firmendaten['Geschaeftsfuehrer']}")
                if safe_get(firmendaten, 'UStIdNr'):
                    footer_lines.append(f"UStIdNr.: {firmendaten['UStIdNr']}")
                if safe_get(firmendaten, 'Steuernummer'):
                    footer_lines.append(f"Steuernr.: {firmendaten['Steuernummer']}")
                if safe_get(firmendaten, 'Telefon'):
                    footer_lines.append(f"Telefon: {firmendaten['Telefon']}")
                bank_name = safe_get(firmendaten, 'BankName')
                iban = safe_get(firmendaten, 'IBAN')
                if bank_name and iban:
                    footer_lines.append(f"Bankverbindung: {firmendaten['BankName']}")
                    footer_lines.append(f"IBAN: {firmendaten['IBAN']}")
                    bic = safe_get(firmendaten, 'BIC')
                    if bic:
                        footer_lines.append(f"BIC: {firmendaten['BIC']}")
            footer_text = ' | '.join(footer_lines) if footer_lines else ''
            
            # Lieferanschrift zusammenstellen (falls abweichend)
            lieferanschrift = []
            if firmendaten:
                liefer_strasse = safe_get(firmendaten, 'LieferStrasse')
                if liefer_strasse:
                    lieferanschrift.append(firmendaten['LieferStrasse'])
                liefer_plz = safe_get(firmendaten, 'LieferPLZ')
                liefer_ort = safe_get(firmendaten, 'LieferOrt')
                if liefer_plz and liefer_ort:
                    lieferanschrift.append(f"{firmendaten['LieferPLZ']} {firmendaten['LieferOrt']}")
            lieferanschrift_text = '\n'.join(lieferanschrift) if lieferanschrift else ''
            
            # Kontext für Template
            context = {
                # Bestellungs-Daten
                'bestellung_id': bestellung['ID'],
                'bestellnummer': safe_get(bestellung, 'Bestellnummer', ''),
                'datum': datum,
                'erstellt_von': safe_get(bestellung, 'ErstelltVon', ''),
                'erstellt_von_kontakt': kontakt_text,
                'status': safe_get(bestellung, 'Status', ''),
                'bemerkung': safe_get(bestellung, 'Bemerkung', ''),
                'freigabe_bemerkung': safe_get(bestellung, 'FreigabeBemerkung', ''),
                
                # Lieferant-Daten
                'lieferant_name': bestellung['LieferantName'] or '',
                'lieferant_strasse': bestellung['LieferantStrasse'] or '',
                'lieferant_plz': bestellung['LieferantPLZ'] or '',
                'lieferant_ort': bestellung['LieferantOrt'] or '',
                'lieferant_plz_ort': f"{bestellung['LieferantPLZ'] or ''} {bestellung['LieferantOrt'] or ''}".strip(),
                'lieferant_telefon': bestellung['LieferantTelefon'] or '',
                'lieferant_email': bestellung['LieferantEmail'] or '',
                
                # Firmendaten
                'firmenname': safe_get(firmendaten, 'Firmenname', '') if firmendaten else '',
                'firmenstrasse': safe_get(firmendaten, 'Strasse', '') if firmendaten else '',
                'firmenplz': safe_get(firmendaten, 'PLZ', '') if firmendaten else '',
                'firmenort': safe_get(firmendaten, 'Ort', '') if firmendaten else '',
                'firmenplz_ort': f"{safe_get(firmendaten, 'PLZ', '')} {safe_get(firmendaten, 'Ort', '')}".strip() if firmendaten else '',
                'firmen_telefon': safe_get(firmendaten, 'Telefon', '') if firmendaten else '',
                'firmen_website': safe_get(firmendaten, 'Website', '') if firmendaten else '',
                'firmen_email': safe_get(firmendaten, 'Email', '') if firmendaten else '',
                'firma_lieferstraße': safe_get(firmendaten, 'LieferStrasse', '') if firmendaten else '',
                'firma_lieferPLZ': safe_get(firmendaten, 'LieferPLZ', '') if firmendaten else '',
                'firma_lieferOrt': safe_get(firmendaten, 'LieferOrt', '') if firmendaten else '',
                'lieferanschrift': lieferanschrift_text,
                'footer': footer_text,
                
                # Positionen
                'positionen': positionen_liste,
                'hat_positionen': len(positionen_liste) > 0,
                'gesamtbetrag': f"{gesamtbetrag:.2f}",
                'waehrung': waehrung,
                
                # Freigabe-Daten
                'freigegeben_von': safe_get(bestellung, 'FreigegebenVon', ''),
                'freigegeben_von_abteilung': safe_get(bestellung, 'FreigegebenVonAbteilung', ''),
                'freigegeben_am': freigabe_datum,
                'hat_unterschrift': unterschrift_img is not None,
                'unterschrift': unterschrift_img,
            }
            
            # Template rendern
            doc.render(context)
            
            # WICHTIG: Temporäres Bild erst NACH dem Rendern löschen
            # Das Bild wird während des Renderings benötigt
            if tmp_img_path and os.path.exists(tmp_img_path):
                try:
                    os.unlink(tmp_img_path)
                except:
                    pass
            
            # Als PDF konvertieren oder DOCX zurückgeben
            # Hinweis: PDF-Konvertierung auf Windows benötigt Microsoft Word
            # Falls nicht verfügbar, wird DOCX zurückgegeben (kann im Browser zu PDF konvertiert werden)
            if DOCX2PDF_AVAILABLE:
                # PDF-Konvertierung versuchen
                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                
                # Temporäre DOCX-Datei erstellen
                with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_docx:
                    tmp_docx.write(buffer.getvalue())
                    tmp_docx_path = tmp_docx.name
                
                # PDF erstellen
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                    tmp_pdf_path = tmp_pdf.name
                
                try:
                    # PDF-Konvertierung (unterstützt Windows docx2pdf und Linux LibreOffice)
                    if not convert_docx_to_pdf(tmp_docx_path, tmp_pdf_path):
                        # PDF-Konvertierung fehlgeschlagen, Fallback zu DOCX
                        raise Exception("PDF-Konvertierung fehlgeschlagen")
                    
                    # PDF lesen
                    with open(tmp_pdf_path, 'rb') as f:
                        pdf_content = f.read()
                    
                    # Temporäre Dateien löschen
                    os.unlink(tmp_docx_path)
                    os.unlink(tmp_pdf_path)
                    
                    # PDF als Download senden
                    filename = f"Bestellung_{bestellung_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
                    response = make_response(pdf_content)
                    response.headers['Content-Type'] = 'application/pdf'
                    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
                except Exception as e:
                    # Falls PDF-Konvertierung fehlschlägt, DOCX zurückgeben
                    # Dies ist ein erwartetes Verhalten, wenn PDF-Konvertierung nicht verfügbar ist
                    # (z.B. wenn LibreOffice oder docx2pdf nicht installiert/konfiguriert sind)
                    pass
                    
                    # Temporäre Dateien aufräumen
                    if os.path.exists(tmp_docx_path):
                        try:
                            os.unlink(tmp_docx_path)
                        except:
                            pass
                    if os.path.exists(tmp_pdf_path):
                        try:
                            os.unlink(tmp_pdf_path)
                        except:
                            pass
                    
                    # COM aufräumen (Windows)
                    import sys
                    if sys.platform == 'win32':
                        try:
                            import pythoncom
                            pythoncom.CoUninitialize()
                        except:
                            pass
                    
                    # Fallback: DOCX zurückgeben
                    buffer = BytesIO()
                    doc.save(buffer)
                    buffer.seek(0)
                    filename = f"Bestellung_{bestellung_id}_{datetime.now().strftime('%Y%m%d')}.docx"
                    response = make_response(buffer.getvalue())
                    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
            
            # Keine PDF-Konvertierung verfügbar, DOCX zurückgeben
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            filename = f"Bestellung_{bestellung_id}_{datetime.now().strftime('%Y%m%d')}.docx"
            response = make_response(buffer.getvalue())
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
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
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    # Dateiendung prüfen
    if not validate_file_extension(file.filename, {'pdf'}):
        flash('Nur PDF-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    try:
        # Ordner erstellen
        bestellung_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], 'Bestellungen', str(bestellung_id))
        
        filename, error_message = save_uploaded_file(
            file,
            bestellung_folder,
            allowed_extensions={'pdf'}
        )
        
        if error_message:
            flash(f'Fehler beim Hochladen: {error_message}', 'danger')
        else:
            flash('Datei erfolgreich hochgeladen.', 'success')
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Datei-Upload Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


@ersatzteile_bp.route('/bestellungen/<int:bestellung_id>/auftragsbestätigung/upload', methods=['POST'])
@login_required
def bestellung_auftragsbestätigung_upload(bestellung_id):
    """Auftragsbestätigung-Upload für Bestellung"""
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
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    # Dateiendung prüfen
    if not validate_file_extension(file.filename, {'pdf', 'jpg', 'jpeg', 'png'}):
        flash('Nur PDF-, JPEG- oder PNG-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
    
    try:
        # Ordner erstellen
        auftragsbestätigung_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Auftragsbestätigungen', str(bestellung_id))
        
        filename, error_message = save_uploaded_file(
            file,
            auftragsbestätigung_folder,
            allowed_extensions={'pdf', 'jpg', 'jpeg', 'png'}
        )
        
        if error_message:
            flash(f'Fehler beim Hochladen: {error_message}', 'danger')
            return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))
        
        flash('Auftragsbestätigung erfolgreich hochgeladen.', 'success')
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Auftragsbestätigung-Upload Fehler: {e}")
    
    return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung_id))


# ========== Lieferanten ==========
