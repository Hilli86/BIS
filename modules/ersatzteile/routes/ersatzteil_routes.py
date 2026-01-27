"""
Ersatzteil-Routen - CRUD-Operationen für Ersatzteile
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app
from datetime import datetime
import os
import re
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


# Feste Kennzeichen-Optionen A-Z für Artikel
KENNZEICHEN_OPTIONEN = [
    {"wert": "A", "label": "A - "},
    {"wert": "B", "label": "B - Batterien und Akkus"},
    {"wert": "C", "label": "C - Chemische Produkte"},
    {"wert": "D", "label": "D - Dichtungen und O-Ringe"},
    {"wert": "E", "label": "E - Elektrische Ersatzteile"},
    {"wert": "F", "label": "F - "},
    {"wert": "G", "label": "G - "},
    {"wert": "H", "label": "H - "},
    {"wert": "I", "label": "I - "},
    {"wert": "J", "label": "J - "},
    {"wert": "K", "label": "K - Kabel und Leitungen"},
    {"wert": "L", "label": "L - Kugellager"},
    {"wert": "M", "label": "M - Mechanische Ersatzteile"},
    {"wert": "N", "label": "N - "},
    {"wert": "O", "label": "O - Öle und Schmierstoffe"},
    {"wert": "P", "label": "P - Pneumatik"},
    {"wert": "Q", "label": "Q - "},
    {"wert": "R", "label": "R - Riemen und Ketten"},
    {"wert": "S", "label": "S - Sonderteile"},
    {"wert": "T", "label": "T - Transport(Bänder, Mattenketten, etc.)"},
    {"wert": "U", "label": "U - "},
    {"wert": "V", "label": "V - Verbrauchsmaterial"},
    {"wert": "W", "label": "W - Wasser und Sanitär"},
    {"wert": "X", "label": "X - "},
    {"wert": "Y", "label": "Y - "},
    {"wert": "Z", "label": "Z - "},
]


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
    nur_ohne_preis = request.args.get('nur_ohne_preis') == '1'
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
            sort_dir=sort_dir,
            nur_ohne_preis=nur_ohne_preis,
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
        nur_ohne_preis=nur_ohne_preis,
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
    
    # Anzahl aus Request-Body lesen (Standard: 1)
    data = request.get_json() or {}
    anzahl = data.get('anzahl', 1)
    
    # Validierung: Anzahl muss zwischen 1 und 100 sein
    try:
        anzahl = int(anzahl)
        if anzahl < 1 or anzahl > 100:
            return jsonify({'success': False, 'message': 'Anzahl muss zwischen 1 und 100 liegen.'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Ungültige Anzahl.'}), 400
    
    with get_db_connection() as conn:
        # Berechtigung prüfen
        if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
            return jsonify({'success': False, 'message': 'Keine Berechtigung für dieses Ersatzteil.'}), 403
        
        # Wiederverwendbare Service-Funktion verwenden
        from ..services import drucke_ersatzteil_etikett_intern
        success, message = drucke_ersatzteil_etikett_intern(ersatzteil_id, anzahl, conn, mitarbeiter_id)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message}), 500


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
    nur_ohne_preis = request.args.get('nur_ohne_preis')
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
        # Prüfe ob Benutzer bearbeiten darf (Admin oder hat Zugriff)
        kann_bearbeiten = is_admin or hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn)
    
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
        'dir': request.args.get('dir', ''),
        'nur_ohne_preis': request.args.get('nur_ohne_preis', '')
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
        kann_bearbeiten=kann_bearbeiten,
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
        vorlage_abteilungen=vorlage_abteilungen,
        kennzeichen_optionen=KENNZEICHEN_OPTIONEN
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
    nur_ohne_preis_filter = request.args.get('nur_ohne_preis') or request.form.get('nur_ohne_preis')
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
        'dir': request.args.get('dir', ''),
        'nur_ohne_preis': request.args.get('nur_ohne_preis', '')
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
                
                # Artikelfoto hochladen (falls ausgewählt)
                if 'artikelfoto_file' in request.files:
                    file = request.files['artikelfoto_file']
                    if file and file.filename != '':
                        try:
                            allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                            original_filename = file.filename
                            file_ext = os.path.splitext(original_filename)[1].lower().lstrip('.')
                            
                            # Validierung
                            if file_ext not in allowed_image_extensions:
                                flash(f'Dateityp nicht erlaubt. Erlaubt sind: {", ".join(allowed_image_extensions)}', 'warning')
                            else:
                                # Altes Artikelfoto laden und löschen falls vorhanden
                                altes_foto = conn.execute('SELECT ArtikelfotoPfad FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                                if altes_foto and altes_foto['ArtikelfotoPfad']:
                                    alter_pfad = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], altes_foto['ArtikelfotoPfad'].replace('/', os.sep))
                                    if os.path.exists(alter_pfad):
                                        try:
                                            os.remove(alter_pfad)
                                        except Exception as e:
                                            print(f"Warnung: Konnte altes Artikelfoto nicht löschen: {e}")
                                
                                # Ordner erstellen
                                upload_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id))
                                create_upload_folder(upload_folder)
                                
                                # Datei speichern als artikelfoto.{ext}
                                filename = f'artikelfoto.{file_ext}'
                                file.filename = filename
                                
                                success_upload, saved_filename, error_message = save_uploaded_file(
                                    file,
                                    upload_folder,
                                    allowed_extensions=allowed_image_extensions
                                )
                                
                                if success_upload and not error_message:
                                    # Datenbank aktualisieren
                                    relative_path = f'Ersatzteile/{ersatzteil_id}/{saved_filename}'
                                    conn.execute('UPDATE Ersatzteil SET ArtikelfotoPfad = ? WHERE ID = ?', (relative_path, ersatzteil_id))
                                    flash('Artikelfoto erfolgreich hochgeladen.', 'success')
                                else:
                                    flash(f'Fehler beim Hochladen des Artikelfotos: {error_message}', 'warning')
                        except Exception as e:
                            flash(f'Fehler beim Hochladen des Artikelfotos: {str(e)}', 'warning')
                            print(f"Artikelfoto-Upload Fehler beim Speichern: {e}")
                
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
                    'dir': request.form.get('dir') or request.args.get('dir', ''),
                    'nur_ohne_preis': request.form.get('nur_ohne_preis') or request.args.get('nur_ohne_preis', '')
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
        from_page=from_page,
        kennzeichen_optionen=KENNZEICHEN_OPTIONEN
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


@ersatzteile_bp.route('/<int:ersatzteil_id>/artikelfoto/upload', methods=['POST'])
@login_required
def ersatzteil_artikelfoto_upload(ersatzteil_id):
    """Artikelfoto für Ersatzteil hochladen"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    # Filter-Parameter aus request.form oder request.args lesen
    filter_params = {
        'kategorie': request.form.get('kategorie') or request.args.get('kategorie', ''),
        'lieferant': request.form.get('lieferant') or request.args.get('lieferant', ''),
        'lagerort': request.form.get('lagerort') or request.args.get('lagerort', ''),
        'lagerplatz': request.form.get('lagerplatz') or request.args.get('lagerplatz', ''),
        'q': request.form.get('q') or request.args.get('q', ''),
        'bestandswarnung': request.form.get('bestandswarnung') or request.args.get('bestandswarnung', ''),
        'kennzeichen': request.form.get('kennzeichen') or request.args.get('kennzeichen', ''),
        'sort': request.form.get('sort') or request.args.get('sort', ''),
        'dir': request.form.get('dir') or request.args.get('dir', ''),
        'nur_ohne_preis': request.form.get('nur_ohne_preis') or request.args.get('nur_ohne_preis', '')
    }
    
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
        filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
        if filter_query:
            detail_url += '?' + filter_query
        return redirect(detail_url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
        filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
        if filter_query:
            detail_url += '?' + filter_query
        return redirect(detail_url)
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen (gleiche wie Bearbeiten)
            if not is_admin and not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            
            original_filename = file.filename
            file_ext = os.path.splitext(original_filename)[1].lower().lstrip('.')
            
            # Validierung
            if file_ext not in allowed_image_extensions:
                flash(f'Dateityp nicht erlaubt. Erlaubt sind: {", ".join(allowed_image_extensions)}', 'danger')
                detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
                filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
                if filter_query:
                    detail_url += '?' + filter_query
                return redirect(detail_url)
            
            # Altes Artikelfoto laden und löschen falls vorhanden
            altes_foto = conn.execute('SELECT ArtikelfotoPfad FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
            if altes_foto and altes_foto['ArtikelfotoPfad']:
                alter_pfad = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], altes_foto['ArtikelfotoPfad'].replace('/', os.sep))
                if os.path.exists(alter_pfad):
                    try:
                        os.remove(alter_pfad)
                    except Exception as e:
                        print(f"Warnung: Konnte altes Artikelfoto nicht löschen: {e}")
            
            # Ordner erstellen
            upload_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id))
            create_upload_folder(upload_folder)
            
            # Datei speichern als artikelfoto.{ext}
            filename = f'artikelfoto.{file_ext}'
            file.filename = filename
            
            success_upload, saved_filename, error_message = save_uploaded_file(
                file,
                upload_folder,
                allowed_extensions=allowed_image_extensions
            )
            
            if not success_upload or error_message:
                flash(f'Fehler beim Hochladen: {error_message}', 'danger')
                detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
                filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
                if filter_query:
                    detail_url += '?' + filter_query
                return redirect(detail_url)
            
            # Datenbank aktualisieren
            relative_path = f'Ersatzteile/{ersatzteil_id}/{saved_filename}'
            conn.execute('UPDATE Ersatzteil SET ArtikelfotoPfad = ? WHERE ID = ?', (relative_path, ersatzteil_id))
            conn.commit()
            
            flash('Artikelfoto erfolgreich hochgeladen.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Hochladen: {str(e)}', 'danger')
        print(f"Artikelfoto-Upload Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    # Redirect mit Filter-Parametern
    detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
    filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
    if filter_query:
        detail_url += '?' + filter_query
    return redirect(detail_url)


@ersatzteile_bp.route('/<int:ersatzteil_id>/artikelfoto/loeschen', methods=['POST'])
@login_required
def ersatzteil_artikelfoto_loeschen(ersatzteil_id):
    """Artikelfoto für Ersatzteil löschen"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    
    # Filter-Parameter aus request.form oder request.args lesen
    filter_params = {
        'kategorie': request.form.get('kategorie') or request.args.get('kategorie', ''),
        'lieferant': request.form.get('lieferant') or request.args.get('lieferant', ''),
        'lagerort': request.form.get('lagerort') or request.args.get('lagerort', ''),
        'lagerplatz': request.form.get('lagerplatz') or request.args.get('lagerplatz', ''),
        'q': request.form.get('q') or request.args.get('q', ''),
        'bestandswarnung': request.form.get('bestandswarnung') or request.args.get('bestandswarnung', ''),
        'kennzeichen': request.form.get('kennzeichen') or request.args.get('kennzeichen', ''),
        'sort': request.form.get('sort') or request.args.get('sort', ''),
        'dir': request.form.get('dir') or request.args.get('dir', ''),
        'nur_ohne_preis': request.form.get('nur_ohne_preis') or request.args.get('nur_ohne_preis', '')
    }
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen (gleiche wie Bearbeiten)
            if not is_admin and not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            # Artikelfoto-Pfad laden
            ersatzteil = conn.execute('SELECT ArtikelfotoPfad FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
            
            if not ersatzteil or not ersatzteil['ArtikelfotoPfad']:
                flash('Kein Artikelfoto vorhanden.', 'warning')
                detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
                filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
                if filter_query:
                    detail_url += '?' + filter_query
                return redirect(detail_url)
            
            # Datei physisch löschen
            filepath = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], ersatzteil['ArtikelfotoPfad'].replace('/', os.sep))
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"Warnung: Konnte Artikelfoto nicht löschen: {e}")
                    flash(f'Fehler beim Löschen der Datei: {str(e)}', 'danger')
                    detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
                    filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
                    if filter_query:
                        detail_url += '?' + filter_query
                    return redirect(detail_url)
            
            # Datenbank aktualisieren
            conn.execute('UPDATE Ersatzteil SET ArtikelfotoPfad = NULL WHERE ID = ?', (ersatzteil_id,))
            conn.commit()
            
            flash('Artikelfoto erfolgreich gelöscht.', 'success')
            
    except Exception as e:
        flash(f'Fehler beim Löschen: {str(e)}', 'danger')
        print(f"Artikelfoto-Lösch Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    # Redirect mit Filter-Parametern
    detail_url = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id)
    filter_query = '&'.join([f'{k}={v}' for k, v in filter_params.items() if v])
    if filter_query:
        detail_url += '?' + filter_query
    return redirect(detail_url)


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


@ersatzteile_bp.route('/api/ersatzteil/<int:ersatzteil_id>/angebote-bestellungen')
@login_required
def api_ersatzteil_angebote_bestellungen(ersatzteil_id):
    """API: Liefert alle Angebotsanfragen und Bestellungen, die dieses Ersatzteil enthalten (Lazy-Load für Detailansicht)."""
    mitarbeiter_id = session.get('user_id')

    try:
        with get_db_connection() as conn:
            # Berechtigte Abteilungen und Admin-Status ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            is_admin = 'admin' in session.get('user_berechtigungen', [])

            # Angebotsanfragen mit diesem Ersatzteil
            angebote_query = '''
                SELECT DISTINCT
                    a.ID,
                    a.Status,
                    a.ErstelltAm,
                    l.Name AS LieferantName
                FROM AngebotsanfragePosition p
                JOIN Angebotsanfrage a ON p.AngebotsanfrageID = a.ID
                LEFT JOIN Lieferant l ON a.LieferantID = l.ID
                WHERE p.ErsatzteilID = ?
            '''
            angebote_params = [ersatzteil_id]

            if not is_admin:
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    angebote_query += f' AND a.ErstellerAbteilungID IN ({placeholders})'
                    angebote_params.extend(sichtbare_abteilungen)
                else:
                    # Keine sichtbaren Abteilungen -> keine Angebote
                    angebote_query += ' AND 1=0'

            angebote_query += ' ORDER BY a.ErstelltAm DESC'
            angebote = conn.execute(angebote_query, angebote_params).fetchall()

            # Bestellungen mit diesem Ersatzteil
            bestellungen_query = '''
                SELECT DISTINCT
                    b.ID,
                    b.Status,
                    b.ErstelltAm,
                    l.Name AS LieferantName
                FROM BestellungPosition p
                JOIN Bestellung b ON p.BestellungID = b.ID
                LEFT JOIN Lieferant l ON b.LieferantID = l.ID
                WHERE p.ErsatzteilID = ? AND b.Gelöscht = 0
            '''
            bestellungen_params = [ersatzteil_id]

            if not is_admin:
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    bestellungen_query += f'''
                        AND EXISTS (
                            SELECT 1 FROM BestellungSichtbarkeit bs
                            WHERE bs.BestellungID = b.ID
                            AND bs.AbteilungID IN ({placeholders})
                        )
                    '''
                    bestellungen_params.extend(sichtbare_abteilungen)
                else:
                    bestellungen_query += ' AND 1=0'

            bestellungen_query += ' ORDER BY b.ErstelltAm DESC'
            bestellungen = conn.execute(bestellungen_query, bestellungen_params).fetchall()

            # In JSON-konvertierbares Format bringen
            angebote_list = []
            for a in angebote:
                angebote_list.append({
                    'id': a['ID'],
                    'status': a['Status'],
                    'erstellt_am': a['ErstelltAm'],
                    'lieferant': a['LieferantName'],
                    'detail_url': url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=a['ID'])
                })

            bestellungen_list = []
            for b in bestellungen:
                bestellungen_list.append({
                    'id': b['ID'],
                    'status': b['Status'],
                    'erstellt_am': b['ErstelltAm'],
                    'lieferant': b['LieferantName'],
                    'detail_url': url_for('ersatzteile.bestellung_detail', bestellung_id=b['ID'])
                })

            return jsonify({
                'success': True,
                'angebote': angebote_list,
                'bestellungen': bestellungen_list
            })

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Fehler in api_ersatzteil_angebote_bestellungen: {e}")
        print(error_trace)
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
