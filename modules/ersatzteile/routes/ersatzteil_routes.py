"""
Ersatzteil-Routen - CRUD-Operationen für Ersatzteile
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from .. import ersatzteile_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_ersatzteil_zugriff_filter, row_to_dict
from utils.file_handling import save_uploaded_file, create_upload_folder, validate_file_extension
from ..services import (
    build_ersatzteil_liste_query, 
    get_ersatzteil_liste_filter_options, 
    get_ersatzteil_detail_data,
    get_dateien_fuer_bereich,
    speichere_datei,
    loesche_datei,
    get_datei_typ_aus_dateiname
)
from ..utils import hat_ersatzteil_zugriff, get_datei_anzahl, allowed_file
from utils.zebra_client import send_zpl_to_printer, build_test_label


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

        # Zebra-Defaults für Etikettendruck
        default_printer = conn.execute('SELECT id, name FROM zebra_printers WHERE active = 1 ORDER BY id LIMIT 1').fetchone()
        default_label = conn.execute('SELECT id, name FROM label_formats WHERE name = ? LIMIT 1', ('30x30 mm',)).fetchone()
    
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
        is_admin=is_admin,
        default_printer=default_printer,
        default_label=default_label
    )


@ersatzteile_bp.route('/<int:ersatzteil_id>/druck_label', methods=['POST'])
@login_required
def ersatzteil_druck_label(ersatzteil_id):
    """Druckt ein 30x30-Etikett für ein Ersatzteil über Zebra."""
    mitarbeiter_id = session.get('user_id')

    with get_db_connection() as conn:
        # Berechtigung prüfen
        if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
            return jsonify({'success': False, 'message': 'Keine Berechtigung für dieses Ersatzteil.'}), 403

        # Ersatzteil-Daten laden (für Inhalt)
        et = conn.execute('''
            SELECT e.ID, e.Bezeichnung, e.Bestellnummer, lo.Bezeichnung AS LagerortName, lp.Bezeichnung AS LagerplatzName
            FROM Ersatzteil e
            LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
            LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
            WHERE e.ID = ? AND e.Gelöscht = 0
        ''', (ersatzteil_id,)).fetchone()

        if not et:
            return jsonify({'success': False, 'message': 'Ersatzteil nicht gefunden.'}), 404

        # Etikett "ErsatzteilLabel" aus der DB laden
        etikett = conn.execute('''
            SELECT e.*, p.ip_address, lf.zpl_header
            FROM Etikett e
            JOIN zebra_printers p ON e.drucker_id = p.id
            JOIN label_formats lf ON e.etikettformat_id = lf.id
            WHERE e.bezeichnung = ? AND p.active = 1
            LIMIT 1
        ''', ('ErsatzteilLabel',)).fetchone()

        if not etikett:
            return jsonify({'success': False, 'message': 'Etikett "ErsatzteilLabel" nicht gefunden oder Drucker nicht aktiv.'}), 400

        # Daten für Platzhalter vorbereiten
        artnr = str(et['ID'])
        bestellnummer = et['Bestellnummer'] or ''
        bezeichnung = et['Bezeichnung'] or ''
        lagerort = et['LagerortName'] or ''
        lagerplatz = et['LagerplatzName'] or ''

        # Bezeichnung auf 3 Zeilen umbrechen
        max_len = 28
        words = (bezeichnung or "").split()
        lines = ["", "", ""]
        current_line = 0

        for w in words:
            sep = "" if len(lines[current_line]) == 0 else " "
            if len(lines[current_line]) + len(sep) + len(w) <= max_len:
                lines[current_line] += sep + w
            elif current_line < 2:
                current_line += 1
                lines[current_line] = w
            else:
                break

        line1, line2, line3 = lines

        # ZPL-Template aus DB laden und Platzhalter ersetzen
        zpl_template = etikett['druckbefehle']
        zpl = zpl_template.format(
            artnr=artnr,
            bestellnummer=bestellnummer,
            line1=line1,
            line2=line2,
            line3=line3,
            lagerort=lagerort,
            lagerplatz=lagerplatz,
            zpl_header=etikett['zpl_header']
        )

        # Kompletten ZPL-Befehl in der Konsole ausgeben (für Debugging)
        print("===== ERSATZTEIL LABEL ZPL =====")
        print(zpl)
        print("===== END ERSATZTEIL LABEL ZPL =====")

        try:
            send_zpl_to_printer(etikett['ip_address'], zpl)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Fehler beim Senden an Drucker: {e}'}), 500

    return jsonify({'success': True, 'message': f'Etikett für Artikel {artnr} gedruckt.'})


@ersatzteile_bp.route('/<int:ersatzteil_id>')
@login_required
def ersatzteil_detail(ersatzteil_id):
    """Ersatzteil-Detailansicht"""
    mitarbeiter_id = session.get('user_id')
    
    # Filter-Parameter aus URL lesen (für "Zurück zur Liste" Button)
    kategorie_filter = request.args.get('kategorie')
    lieferant_filter = request.args.get('lieferant')
    lagerort_filter = request.args.get('lagerort')
    lagerplatz_filter = request.args.get('lagerplatz')
    kennzeichen_filter = request.args.get('kennzeichen')
    bestandswarnung = request.args.get('bestandswarnung')
    q_filter = request.args.get('q')
    sort_by = request.args.get('sort')
    sort_dir = request.args.get('dir')
    
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
        
        # Dateien aus Datei-Tabelle laden
        alle_dateien_db = get_dateien_fuer_bereich('Ersatzteil', ersatzteil_id, conn)
        
        # In das Format konvertieren, das das Template erwartet (konsistent mit Bestellungen/Angeboten)
        dateien = []
        for d in alle_dateien_db:
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
    
    # Filter-Parameter aus Query-String lesen (für Zurück-Button)
    filter_params = {
        'kategorie': request.args.get('kategorie', ''),
        'lieferant': request.args.get('lieferant', ''),
        'lagerort': request.args.get('lagerort', ''),
        'lagerplatz': request.args.get('lagerplatz', ''),
        'q': request.args.get('q', ''),
        'bestandswarnung': request.args.get('bestandswarnung', ''),
        'kennzeichen': request.args.get('kennzeichen', ''),
        'sort': request.args.get('sort', ''),
        'dir': request.args.get('dir', '')
    }
    
    return render_template(
        'ersatzteil_detail.html',
        ersatzteil=detail_data['ersatzteil'],
        dateien=dateien,
        lagerbuchungen=detail_data['lagerbuchungen'],
        verknuepfungen=detail_data['verknuepfungen'],
        zugriffe=detail_data['zugriffe'],
        kostenstellen=detail_data['kostenstellen'],
        is_admin=is_admin,
        filter_params=filter_params
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
                        Kennzeichen, ArtikelnummerHersteller, Link, ErstelltAm
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
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
    
    # Filter-Parameter aus URL oder Formular lesen (für "Zurück zur Liste" Button)
    kategorie_filter = request.args.get('kategorie') or request.form.get('kategorie')
    lieferant_filter = request.args.get('lieferant') or request.form.get('lieferant')
    lagerort_filter = request.args.get('lagerort') or request.form.get('lagerort')
    lagerplatz_filter = request.args.get('lagerplatz') or request.form.get('lagerplatz')
    kennzeichen_filter = request.args.get('kennzeichen') or request.form.get('kennzeichen')
    bestandswarnung = request.args.get('bestandswarnung') or request.form.get('bestandswarnung')
    q_filter = request.args.get('q') or request.form.get('q')
    sort_by = request.args.get('sort') or request.form.get('sort')
    sort_dir = request.args.get('dir') or request.form.get('dir')
    
    # Filter-Parameter aus Query-String lesen (für Zurück-Button)
    filter_params = {
        'kategorie': request.args.get('kategorie', ''),
        'lieferant': request.args.get('lieferant', ''),
        'lagerort': request.args.get('lagerort', ''),
        'lagerplatz': request.args.get('lagerplatz', ''),
        'q': request.args.get('q', ''),
        'bestandswarnung': request.args.get('bestandswarnung', ''),
        'kennzeichen': request.args.get('kennzeichen', ''),
        'sort': request.args.get('sort', ''),
        'dir': request.args.get('dir', '')
    }
    
    # Prüfen, ob man von der Liste oder vom Detail kommt
    from_page = request.args.get('from') or 'list'  # Standard: Liste
    
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
                
                # Prüfen, ob man von der Liste oder vom Detail kommt
                from_page = request.form.get('from', 'list')
                
                # Filter-Parameter für Redirect aus request.form ODER request.args lesen
                # request.form hat Vorrang (beim POST)
                filter_params = {
                    'kategorie': request.form.get('kategorie') or request.args.get('kategorie', ''),
                    'lieferant': request.form.get('lieferant') or request.args.get('lieferant', ''),
                    'lagerort': request.form.get('lagerort') or request.args.get('lagerort', ''),
                    'lagerplatz': request.form.get('lagerplatz') or request.args.get('lagerplatz', ''),
                    'q': request.form.get('q') or request.args.get('q', ''),
                    'bestandswarnung': request.form.get('bestandswarnung') or request.args.get('bestandswarnung', ''),
                    'kennzeichen': request.form.get('kennzeichen_filter') or request.args.get('kennzeichen', ''),
                    'sort': request.form.get('sort') or request.args.get('sort', ''),
                    'dir': request.form.get('dir') or request.args.get('dir', '')
                }
                
                if from_page == 'detail':
                    # Zurück zum Detail mit Filter-Parametern
                    detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
                    filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
                    if filter_query:
                        detail_url += '?' + filter_query
                    return redirect(detail_url)
                else:
                    # Zurück zur gefilterten Liste
                    liste_url = url_for('ersatzteile.ersatzteil_liste')
                    filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
                    if filter_query:
                        liste_url += '?' + filter_query
                    return redirect(liste_url)
                
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
        filter_params=filter_params,
        from_page=from_page
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


@ersatzteile_bp.route('/<int:ersatzteil_id>/datei/upload', methods=['POST'])
@login_required
def ersatzteil_datei_upload(ersatzteil_id):
    """Datei(en) (Bild oder Dokument) für Ersatzteil hochladen - unterstützt mehrere Dateien"""
    mitarbeiter_id = session.get('user_id')
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    # Mehrere Dateien können hochgeladen werden
    files = request.files.getlist('file')
    beschreibung = request.form.get('beschreibung', '').strip()
    typ = request.form.get('typ', '').strip()
    
    # Filtere leere Dateien heraus
    files = [f for f in files if f.filename != '']
    
    if not files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen
            if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            allowed_document_extensions = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
            
            erfolgreich = 0
            fehler = []
            
            for file in files:
                try:
                    original_filename = file.filename
                    
                    # Dateityp erkennen und validieren
                    datei_typ = get_datei_typ_aus_dateiname(original_filename)
                    
                    # Bestimme Zielordner basierend auf Dateityp
                    if datei_typ == 'Bild' or any(original_filename.lower().endswith(f'.{ext}') for ext in allowed_image_extensions):
                        # Bild
                        upload_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), 'bilder')
                        subfolder = 'bilder'
                        allowed_extensions = allowed_image_extensions
                    else:
                        # Dokument
                        upload_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), 'dokumente')
                        subfolder = 'dokumente'
                        allowed_extensions = allowed_document_extensions
                    
                    # Validierung mit Original-Dateinamen
                    if not validate_file_extension(original_filename, allowed_extensions):
                        fehler.append(f'{original_filename}: Dateityp nicht erlaubt')
                        continue
                    
                    # Ordner erstellen
                    create_upload_folder(upload_folder)
                    
                    # Datei speichern mit Timestamp
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    file.filename = timestamp + secure_filename(original_filename)
                    
                    success_upload, filename, error_message = save_uploaded_file(
                        file,
                        upload_folder,
                        allowed_extensions=None  # Bereits validiert
                    )
                    
                    if not success_upload or error_message:
                        fehler.append(f'{original_filename}: {error_message}')
                        continue
                    
                    # Datenbankeintrag in Datei-Tabelle - Pfad mit Forward-Slashes für URLs
                    relative_path = f'Ersatzteile/{ersatzteil_id}/{subfolder}/{filename}'
                    datei_typ_final = typ if typ else datei_typ
                    speichere_datei(
                        bereich_typ='Ersatzteil',
                        bereich_id=ersatzteil_id,
                        dateiname=original_filename,
                        dateipfad=relative_path,
                        beschreibung=beschreibung,
                        typ=datei_typ_final,
                        mitarbeiter_id=mitarbeiter_id,
                        conn=conn
                    )
                    
                    erfolgreich += 1
                except Exception as e:
                    fehler.append(f'{file.filename if hasattr(file, "filename") else "Unbekannt"}: {str(e)}')
                    print(f"Datei-Upload Fehler für {file.filename}: {e}")
            
            # Feedback an Benutzer
            if erfolgreich > 0:
                if len(files) == 1:
                    flash('Datei erfolgreich hochgeladen.', 'success')
                else:
                    flash(f'{erfolgreich} Datei(en) erfolgreich hochgeladen.', 'success')
            
            if fehler:
                fehler_text = '; '.join(fehler[:5])  # Maximal 5 Fehler anzeigen
                if len(fehler) > 5:
                    fehler_text += f' ... und {len(fehler) - 5} weitere Fehler'
                flash(f'Fehler beim Hochladen: {fehler_text}', 'danger')
                
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Datei-Upload Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/datei/<int:datei_id>/loeschen', methods=['POST'])
@login_required
def datei_loeschen(datei_id):
    """Datei löschen (einheitlich für alle Dateitypen)"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    if not is_admin:
        flash('Nur Administratoren können Dateien löschen.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    try:
        with get_db_connection() as conn:
            # Datei-Informationen laden
            datei = conn.execute('''
                SELECT BereichTyp, BereichID, Dateipfad 
                FROM Datei 
                WHERE ID = ?
            ''', (datei_id,)).fetchone()
            
            if not datei:
                flash('Datei nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            # Datei physisch löschen
            filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], datei['Dateipfad'].replace('/', os.sep))
            if os.path.exists(filepath):
                os.remove(filepath)
            
            # Datenbankeintrag löschen
            loesche_datei(datei_id, conn)
            
            # Zurück zur entsprechenden Detail-Seite
            if datei['BereichTyp'] == 'Ersatzteil':
                flash('Datei erfolgreich gelöscht.', 'success')
                return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=datei['BereichID']))
            elif datei['BereichTyp'] == 'Bestellung':
                flash('Datei erfolgreich gelöscht.', 'success')
                return redirect(url_for('ersatzteile.bestellung_detail', bestellung_id=datei['BereichID']))
            elif datei['BereichTyp'] == 'Lieferschein':
                flash('Datei erfolgreich gelöscht.', 'success')
                return redirect(url_for('ersatzteile.wareneingang_bestellung', bestellung_id=datei['BereichID']))
            elif datei['BereichTyp'] == 'Thema':
                flash('Datei erfolgreich gelöscht.', 'success')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=datei['BereichID']))
            else:
                flash('Datei erfolgreich gelöscht.', 'success')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
        print(f"Datei löschen Fehler: {e}")
    
    return redirect(url_for('ersatzteile.ersatzteil_liste'))


# Alte Routen für Rückwärtskompatibilität (werden später entfernt)
@ersatzteile_bp.route('/<int:ersatzteil_id>/bild/<int:bild_id>/loeschen', methods=['POST'])
@login_required
def bild_loeschen(ersatzteil_id, bild_id):
    """Bild löschen (Legacy - Weiterleitung zu neuer Route)"""
    # Versuche Datei in Datei-Tabelle zu finden
    with get_db_connection() as conn:
        datei = conn.execute('''
            SELECT ID FROM Datei 
            WHERE BereichTyp = 'Ersatzteil' 
            AND BereichID = ? 
            AND Typ = 'Bild'
            LIMIT 1
        ''', (ersatzteil_id,)).fetchone()
        if datei:
            return datei_loeschen(datei['ID'])
    
    flash('Bild nicht gefunden.', 'danger')
    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))


@ersatzteile_bp.route('/<int:ersatzteil_id>/dokument/<int:dokument_id>/loeschen', methods=['POST'])
@login_required
def dokument_loeschen(ersatzteil_id, dokument_id):
    """Dokument löschen (Legacy - Weiterleitung zu neuer Route)"""
    # Versuche Datei in Datei-Tabelle zu finden
    with get_db_connection() as conn:
        datei = conn.execute('''
            SELECT ID FROM Datei 
            WHERE BereichTyp = 'Ersatzteil' 
            AND BereichID = ? 
            AND Typ != 'Bild'
            LIMIT 1
        ''', (ersatzteil_id,)).fetchone()
        if datei:
            return datei_loeschen(datei['ID'])
    
    flash('Dokument nicht gefunden.', 'danger')
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
