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
from utils.file_handling import save_uploaded_file, create_upload_folder
from ..services import (
    build_ersatzteil_liste_query, 
    get_ersatzteil_liste_filter_options, 
    get_ersatzteil_detail_data
)
from ..utils import hat_ersatzteil_zugriff, get_datei_anzahl, allowed_file


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
