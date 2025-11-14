"""
Ersatzteile Routes - Ersatzteilverwaltung, Lagerbuchungen, Verknüpfungen
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app, make_response
from datetime import datetime
import os
from io import BytesIO
from werkzeug.utils import secure_filename
from . import ersatzteile_bp
from utils import get_db_connection, login_required, permission_required, get_sichtbare_abteilungen_fuer_mitarbeiter, ist_admin
from utils.firmendaten import get_firmendaten
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER


def hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
    """Prüft ob Mitarbeiter Zugriff auf Ersatzteil hat"""
    # Admin hat immer Zugriff
    if 'admin' in session.get('user_berechtigungen', []):
        return True
    
    # Prüfe ob Benutzer der Ersteller ist
    ersatzteil = conn.execute('SELECT ErstelltVonID FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
    if ersatzteil and ersatzteil['ErstelltVonID'] == mitarbeiter_id:
        return True
    
    # Prüfe ob Ersatzteil für Abteilungen des Mitarbeiters freigegeben ist
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    if not sichtbare_abteilungen:
        return False
    
    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
    zugriff = conn.execute(f'''
        SELECT COUNT(*) as count FROM ErsatzteilAbteilungZugriff
        WHERE ErsatzteilID = ? AND AbteilungID IN ({placeholders})
    ''', [ersatzteil_id] + sichtbare_abteilungen).fetchone()
    
    return zugriff['count'] > 0


def get_datei_anzahl(ersatzteil_id, typ='bild'):
    """Ermittelt die Anzahl der Dateien für ein Ersatzteil"""
    ersatzteil_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), typ)
    if not os.path.exists(ersatzteil_folder):
        return 0
    try:
        files = os.listdir(ersatzteil_folder)
        return len([f for f in files if os.path.isfile(os.path.join(ersatzteil_folder, f))])
    except:
        return 0


@ersatzteile_bp.route('/')
@login_required
def ersatzteil_liste():
    """Ersatzteil-Liste mit Filtern"""
    mitarbeiter_id = session.get('user_id')
    
    # Filterparameter
    kategorie_filter = request.args.get('kategorie')
    lieferant_filter = request.args.get('lieferant')
    bestandswarnung = request.args.get('bestandswarnung') == '1'
    q_filter = request.args.get('q')
    sort_by = request.args.get('sort', 'kategorie')  # Standard: Kategorie
    sort_dir = request.args.get('dir', 'asc')  # Standard: aufsteigend
    
    with get_db_connection() as conn:
        # Berechtigte Abteilungen ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Basis-Query
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
                e.Kennzeichen,
                e.LieferantID,
                k.Bezeichnung AS Kategorie,
                l.Name AS Lieferant,
                lo.Bezeichnung AS LagerortName,
                lp.Bezeichnung AS LagerplatzName,
                e.Aktiv,
                e.Gelöscht
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            LEFT JOIN Lieferant l ON e.LieferantID = l.ID
            LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
            LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
            WHERE e.Gelöscht = 0
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
                # Nur selbst erstellte Artikel
                query += ' AND e.ErstelltVonID = ?'
                params.append(mitarbeiter_id)
        
        # Filter anwenden
        if kategorie_filter:
            query += ' AND e.KategorieID = ?'
            params.append(kategorie_filter)
        
        if lieferant_filter:
            query += ' AND e.LieferantID = ?'
            params.append(lieferant_filter)
        
        if bestandswarnung:
            query += ' AND e.AktuellerBestand <= e.Mindestbestand AND e.Mindestbestand > 0 AND e.EndOfLife = 0'
        
        if q_filter:
            query += ' AND (e.Bestellnummer LIKE ? OR e.Bezeichnung LIKE ? OR e.Beschreibung LIKE ?)'
            search_term = f'%{q_filter}%'
            params.extend([search_term, search_term, search_term])
        
        # Sortierung
        sort_mapping = {
            'id': 'e.ID',
            'artikelnummer': 'e.Bestellnummer',
            'kategorie': 'k.Bezeichnung',
            'bezeichnung': 'e.Bezeichnung',
            'lieferant': 'l.Name',
            'bestand': 'e.AktuellerBestand',
            'lagerort': 'lo.Bezeichnung',
            'lagerplatz': 'lp.Bezeichnung'
        }
        
        sort_column = sort_mapping.get(sort_by, 'k.Bezeichnung')
        sort_direction = 'DESC' if sort_dir == 'desc' else 'ASC'
        
        # Sekundäre Sortierung nach Bezeichnung, wenn nicht bereits danach sortiert wird
        if sort_by != 'bezeichnung':
            query += f' ORDER BY {sort_column} {sort_direction}, e.Bezeichnung ASC'
        else:
            query += f' ORDER BY {sort_column} {sort_direction}'
        
        ersatzteile = conn.execute(query, params).fetchall()
        
        # Filter-Optionen laden
        kategorien = conn.execute('SELECT ID, Bezeichnung FROM ErsatzteilKategorie WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        lieferanten = conn.execute('SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name').fetchall()
    
    return render_template(
        'ersatzteil_liste.html',
        ersatzteile=ersatzteile,
        kategorien=kategorien,
        lieferanten=lieferanten,
        kategorie_filter=kategorie_filter,
        lieferant_filter=lieferant_filter,
        bestandswarnung=bestandswarnung,
        q_filter=q_filter,
        sort_by=sort_by,
        sort_dir=sort_dir
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
        
        if not is_admin:
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                ersatzteile_query += f'''
                    AND (
                        e.ErstelltVonID = ? OR
                        e.ID IN (
                            SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                            WHERE AbteilungID IN ({placeholders})
                        )
                    )
                '''
                ersatzteile_params.append(mitarbeiter_id)
                ersatzteile_params.extend(sichtbare_abteilungen)
            else:
                # Nur selbst erstellte Artikel
                ersatzteile_query += ' AND e.ErstelltVonID = ?'
                ersatzteile_params.append(mitarbeiter_id)
        
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
        
        # Ersatzteil laden
        ersatzteil = conn.execute('''
            SELECT 
                e.*,
                k.Bezeichnung AS Kategorie,
                l.Name AS Lieferant,
                l.Kontaktperson AS LieferantKontakt,
                l.Telefon AS LieferantTelefon,
                l.Email AS LieferantEmail,
                lo.Bezeichnung AS LagerortName,
                lp.Bezeichnung AS LagerplatzName,
                m.Vorname || ' ' || m.Nachname AS ErstelltVon,
                n.Bestellnummer AS NachfolgeartikelNummer,
                n.Bezeichnung AS NachfolgeartikelBezeichnung
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            LEFT JOIN Lieferant l ON e.LieferantID = l.ID
            LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
            LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
            LEFT JOIN Mitarbeiter m ON e.ErstelltVonID = m.ID
            LEFT JOIN Ersatzteil n ON e.NachfolgeartikelID = n.ID
            WHERE e.ID = ? AND e.Gelöscht = 0
        ''', (ersatzteil_id,)).fetchone()
        
        if not ersatzteil:
            flash('Ersatzteil nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_liste'))
        
        # Bilder laden
        bilder = conn.execute('''
            SELECT ID, Dateiname, Dateipfad FROM ErsatzteilBild
            WHERE ErsatzteilID = ?
            ORDER BY ErstelltAm DESC
        ''', (ersatzteil_id,)).fetchall()
        
        # Dokumente laden
        dokumente = conn.execute('''
            SELECT ID, Dateiname, Dateipfad, Typ FROM ErsatzteilDokument
            WHERE ErsatzteilID = ?
            ORDER BY ErstelltAm DESC
        ''', (ersatzteil_id,)).fetchall()
        
        # Lagerbuchungen laden
        lagerbuchungen = conn.execute('''
            SELECT 
                l.ID,
                l.Typ,
                l.Menge,
                l.Grund,
                l.Buchungsdatum,
                l.Bemerkung,
                l.Preis,
                l.Waehrung,
                m.Vorname || ' ' || m.Nachname AS VerwendetVon,
                k.Bezeichnung AS Kostenstelle,
                t.ID AS ThemaID
            FROM Lagerbuchung l
            LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
            LEFT JOIN Kostenstelle k ON l.KostenstelleID = k.ID
            LEFT JOIN SchichtbuchThema t ON l.ThemaID = t.ID
            WHERE l.ErsatzteilID = ?
            ORDER BY l.Buchungsdatum DESC
            LIMIT 50
        ''', (ersatzteil_id,)).fetchall()
        
        # Thema-Verknüpfungen laden (aus Lagerbuchungen)
        verknuepfungen = conn.execute('''
            SELECT 
                l.ID,
                l.Menge,
                l.Buchungsdatum AS VerwendetAm,
                l.Bemerkung,
                l.ThemaID,
                l.Typ,
                m.Vorname || ' ' || m.Nachname AS VerwendetVon
            FROM Lagerbuchung l
            JOIN SchichtbuchThema t ON l.ThemaID = t.ID
            LEFT JOIN Mitarbeiter m ON l.VerwendetVonID = m.ID
            WHERE l.ErsatzteilID = ? AND l.ThemaID IS NOT NULL
            ORDER BY l.Buchungsdatum DESC
        ''', (ersatzteil_id,)).fetchall()
        
        # Abteilungszugriffe laden
        zugriffe = conn.execute('''
            SELECT a.ID, a.Bezeichnung
            FROM ErsatzteilAbteilungZugriff ez
            JOIN Abteilung a ON ez.AbteilungID = a.ID
            WHERE ez.ErsatzteilID = ?
            ORDER BY a.Bezeichnung
        ''', (ersatzteil_id,)).fetchall()
        
        # Kostenstellen für Dropdown
        kostenstellen = conn.execute('SELECT ID, Bezeichnung FROM Kostenstelle WHERE Aktiv = 1 ORDER BY Sortierung, Bezeichnung').fetchall()
        
        datei_anzahl_bilder = get_datei_anzahl(ersatzteil_id, 'bilder')
        datei_anzahl_dokumente = get_datei_anzahl(ersatzteil_id, 'dokumente')
    
    return render_template(
        'ersatzteil_detail.html',
        ersatzteil=ersatzteil,
        bilder=bilder,
        dokumente=dokumente,
        lagerbuchungen=lagerbuchungen,
        verknuepfungen=verknuepfungen,
        zugriffe=zugriffe,
        kostenstellen=kostenstellen,
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
    
    if vorlage_id:
        with get_db_connection() as conn:
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
                        Kennzeichen, ArtikelnummerHersteller
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                ''', (bestellnummer, bezeichnung, beschreibung, kategorie_id, hersteller,
                      lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand, 
                      einheit, mitarbeiter_id, end_of_life, nachfolgeartikel_id, kennzeichen, artikelnummer_hersteller))
                
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
                        NachfolgeartikelID = ?, Kennzeichen = ?, ArtikelnummerHersteller = ?
                    WHERE ID = ?
                ''', (bestellnummer, bezeichnung, beschreibung, kategorie_id, hersteller,
                      lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand, 
                      einheit, aktiv, end_of_life, nachfolgeartikel_id, kennzeichen, artikelnummer_hersteller, ersatzteil_id))
                
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
        zugriff_ids=zugriff_ids
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
            
            aktueller_bestand = ersatzteil['AktuellerBestand']
            artikel_preis = ersatzteil['Preis']
            artikel_waehrung = ersatzteil['Waehrung'] or 'EUR'
            
            # Bestand aktualisieren
            if typ == 'Eingang':
                neuer_bestand = aktueller_bestand + menge
                buchungsmenge = menge
            elif typ == 'Inventur':
                # Bei Inventur wird der Bestand auf den eingegebenen Wert gesetzt
                neuer_bestand = menge
                if neuer_bestand < 0:
                    flash('Bestand kann nicht negativ werden.', 'danger')
                    return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
                # Für die Buchung: Die eingegebene Menge (neuer Lagerstand) speichern
                buchungsmenge = menge
            else:  # Ausgang
                if aktueller_bestand < menge:
                    flash(f'Nicht genug Bestand verfügbar! Verfügbar: {aktueller_bestand}, benötigt: {menge}. Die Buchung wurde nicht durchgeführt.', 'danger')
                    return redirect(url_for('ersatzteile.lagerbuchungen_liste'))
                neuer_bestand = aktueller_bestand - menge
                buchungsmenge = menge
            
            # Lagerbuchung erstellen
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (ersatzteil_id, typ, buchungsmenge, grund, thema_id, kostenstelle_id, mitarbeiter_id, bemerkung, artikel_preis, artikel_waehrung))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            
            conn.commit()
            flash(f'Lagerbuchung erfolgreich durchgeführt. Neuer Bestand: {neuer_bestand}', 'success')
            
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
            
            aktueller_bestand = ersatzteil['AktuellerBestand']
            artikel_preis = ersatzteil['Preis']
            artikel_waehrung = ersatzteil['Waehrung'] or 'EUR'
            
            # Bestand aktualisieren
            if typ == 'Eingang':
                neuer_bestand = aktueller_bestand + menge
                buchungsmenge = menge
            elif typ == 'Inventur':
                # Bei Inventur wird der Bestand auf den eingegebenen Wert gesetzt
                neuer_bestand = menge
                if neuer_bestand < 0:
                    flash('Bestand kann nicht negativ werden.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
                # Für die Buchung: Die eingegebene Menge (neuer Lagerstand) speichern
                buchungsmenge = menge
            else:  # Ausgang
                if aktueller_bestand < menge:
                    flash(f'Nicht genug Bestand verfügbar! Verfügbar: {aktueller_bestand}, benötigt: {menge}. Die Buchung wurde nicht durchgeführt.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
                neuer_bestand = aktueller_bestand - menge
                buchungsmenge = menge
            
            # Lagerbuchung erstellen (NICHT löschbar!)
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (ersatzteil_id, typ, buchungsmenge, grund, thema_id, kostenstelle_id, mitarbeiter_id, bemerkung, artikel_preis, artikel_waehrung))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            
            conn.commit()
            flash(f'Lagerbuchung erfolgreich durchgeführt. Neuer Bestand: {neuer_bestand}', 'success')
            
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
            
            aktueller_bestand = ersatzteil['AktuellerBestand']
            artikel_preis = ersatzteil['Preis']
            artikel_waehrung = ersatzteil['Waehrung'] or 'EUR'
            
            if aktueller_bestand < menge:
                flash(f'Nicht genug Bestand verfügbar! Verfügbar: {aktueller_bestand}, benötigt: {menge}. Die Buchung wurde nicht durchgeführt.', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            # Automatische Lagerbuchung (Ausgang) mit Thema-Verknüpfung
            neuer_bestand = aktueller_bestand - menge
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
                ) VALUES (?, 'Ausgang', ?, 'Thema', ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (ersatzteil_id, menge, thema_id, kostenstelle_id, mitarbeiter_id, bemerkung, artikel_preis, artikel_waehrung))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            
            conn.commit()
            flash(f'Ersatzteil erfolgreich zugeordnet. Bestand reduziert um {menge}.', 'success')
            
    except Exception as e:
        flash(f'Fehler bei der Verknüpfung: {str(e)}', 'danger')
        print(f"Thema verknüpfen Fehler: {e}")
    
    return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))


@ersatzteile_bp.route('/inventurliste')
@login_required
def inventurliste():
    """Inventurliste - Gruppiert nach Lagerort + Lagerplatz, sortiert nach Artikel-ID"""
    mitarbeiter_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Berechtigte Abteilungen ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
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
    
    return render_template('inventurliste.html', inventur_gruppiert=inventur_gruppiert)


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
            
            aktueller_bestand = ersatzteil['AktuellerBestand']
            artikel_preis = ersatzteil['Preis']
            artikel_waehrung = ersatzteil['Waehrung']
            
            # Bei Inventur wird der Bestand auf den eingegebenen Wert gesetzt
            # Für die Buchung: Die eingegebene Menge (neuer Lagerstand) speichern
            buchungsmenge = neuer_bestand
            
            # Lagerbuchung erstellen
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (ersatzteil_id, 'Inventur', buchungsmenge, 'Inventur aus Inventurliste', None, None, mitarbeiter_id, f'Inventur: Bestand von {aktueller_bestand} auf {neuer_bestand} geändert', artikel_preis, artikel_waehrung))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            
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
                SELECT e.ID, e.Bestellnummer, e.Bezeichnung
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
                    'bezeichnung': ersatzteil['Bezeichnung']
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


@ersatzteile_bp.route('/api/ersatzteile/lieferant/<int:lieferant_id>')
@login_required
def api_ersatzteile_lieferant(lieferant_id):
    """API: Alle Ersatzteile eines Lieferanten abrufen"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Berechtigte Abteilungen ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            
            # Ersatzteile laden
            query = '''
                SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.Preis, e.Waehrung
                FROM Ersatzteil e
                WHERE e.LieferantID = ? AND e.Gelöscht = 0
            '''
            params = [lieferant_id]
            
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
                    'waehrung': e['Waehrung'] or 'EUR'
                })
            
            return jsonify({
                'success': True,
                'ersatzteile': result
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Fehler: {str(e)}'
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


@ersatzteile_bp.route('/lieferanten')
@login_required
def lieferanten_liste():
    """Lieferanten-Liste (für alle Benutzer sichtbar, keine Abteilungsfilterung)"""
    with get_db_connection() as conn:
        lieferanten = conn.execute('''
            SELECT 
                l.ID,
                l.Name,
                l.Kontaktperson,
                l.Telefon,
                l.Email,
                l.Strasse,
                l.PLZ,
                l.Ort,
                l.Aktiv,
                COUNT(e.ID) AS ErsatzteilAnzahl
            FROM Lieferant l
            LEFT JOIN Ersatzteil e ON l.ID = e.LieferantID AND e.Gelöscht = 0
            WHERE l.Gelöscht = 0
            GROUP BY l.ID
            ORDER BY l.Name
        ''').fetchall()
    
    return render_template('lieferanten_liste.html', lieferanten=lieferanten)


@ersatzteile_bp.route('/lieferanten/<int:lieferant_id>')
@login_required
def lieferant_detail(lieferant_id):
    """Lieferant-Detailansicht mit zugehörigen Ersatzteilen"""
    with get_db_connection() as conn:
        lieferant = conn.execute('''
            SELECT ID, Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Aktiv
            FROM Lieferant
            WHERE ID = ? AND Gelöscht = 0
        ''', (lieferant_id,)).fetchone()
        
        if not lieferant:
            flash('Lieferant nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.lieferanten_liste'))
        
        # Ersatzteile dieses Lieferanten laden (nur die, auf die der Benutzer Zugriff hat)
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        query = '''
            SELECT 
                e.ID,
                e.Bestellnummer,
                e.Bezeichnung,
                e.AktuellerBestand,
                e.Mindestbestand,
                e.Einheit,
                k.Bezeichnung AS Kategorie
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            WHERE e.LieferantID = ? AND e.Gelöscht = 0
        '''
        params = [lieferant_id]
        
        # Berechtigungsfilter für Ersatzteile
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
        
        query += ' ORDER BY e.Bezeichnung'
        ersatzteile = conn.execute(query, params).fetchall()
    
    return render_template('lieferant_detail.html', lieferant=lieferant, ersatzteile=ersatzteile)


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
                os.makedirs(upload_folder, exist_ok=True)
                
                # Datei speichern
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                # Datenbankeintrag
                relative_path = os.path.join('Ersatzteile', str(ersatzteil_id), 'bilder', filename)
                conn.execute('''
                    INSERT INTO ErsatzteilBild (ErsatzteilID, Dateiname, Dateipfad)
                    VALUES (?, ?, ?)
                ''', (ersatzteil_id, file.filename, relative_path))
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
                os.makedirs(upload_folder, exist_ok=True)
                
                # Datei speichern
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                # Datenbankeintrag
                relative_path = os.path.join('Ersatzteile', str(ersatzteil_id), 'dokumente', filename)
                conn.execute('''
                    INSERT INTO ErsatzteilDokument (ErsatzteilID, Dateiname, Dateipfad, Typ)
                    VALUES (?, ?, ?, ?)
                ''', (ersatzteil_id, file.filename, relative_path, typ))
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
    
    # Sicherheitsprüfung: Dateipfad muss mit Ersatzteile beginnen
    if not filepath.startswith('Ersatzteile/'):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath)
    
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

def get_angebotsanfrage_dateien(angebotsanfrage_id):
    """Hilfsfunktion: Scannt Ordner nach PDF-Dateien für eine Angebotsanfrage"""
    angebote_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], str(angebotsanfrage_id))
    dateien = []
    
    if os.path.exists(angebote_folder):
        try:
            for filename in os.listdir(angebote_folder):
                if filename.lower().endswith('.pdf'):
                    filepath = os.path.join(angebote_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Angebote/{angebotsanfrage_id}/{filename}'
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
                'SELECT LieferantID, Bestellnummer, Bezeichnung FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0',
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
                    # Ersatzteil-Daten laden für Bestellnummer und Bezeichnung
                    bestellnummer = ersatzteil['Bestellnummer']
                    bezeichnung = ersatzteil['Bezeichnung']
                    
                    # Position hinzufügen
                    conn.execute('''
                        INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Bestellnummer, Bezeichnung)
                        VALUES (?, ?, 1, ?, ?)
                    ''', (anfrage_id, ersatzteil_id, bestellnummer, bezeichnung))
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
                
                # Ersatzteil-Daten laden für Bestellnummer und Bezeichnung
                bestellnummer = ersatzteil['Bestellnummer']
                bezeichnung = ersatzteil['Bezeichnung']
                
                # Ersatzteil als Position hinzufügen
                conn.execute('''
                    INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Bestellnummer, Bezeichnung)
                    VALUES (?, ?, 1, ?, ?)
                ''', (anfrage_id, ersatzteil_id, bestellnummer, bezeichnung))
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
        bestellnummern = request.form.getlist('bestellnummer[]')
        bezeichnungen = request.form.getlist('bezeichnung[]')
        positionen_bemerkungen = request.form.getlist('position_bemerkung[]')
        
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
                        bestellnummer = bestellnummern[i].strip() if i < len(bestellnummern) and bestellnummern[i] else None
                        bezeichnung = bezeichnungen[i].strip() if i < len(bezeichnungen) and bezeichnungen[i] else None
                        pos_bemerkung = positionen_bemerkungen[i].strip() if i < len(positionen_bemerkungen) and positionen_bemerkungen[i] else None
                        
                        # Wenn ErsatzteilID vorhanden, aber Bestellnummer/Bezeichnung fehlen, aus Ersatzteil laden
                        if ersatzteil_id and (not bestellnummer or not bezeichnung):
                            ersatzteil = conn.execute('SELECT Bestellnummer, Bezeichnung FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                            if ersatzteil:
                                if not bestellnummer:
                                    bestellnummer = ersatzteil['Bestellnummer']
                                if not bezeichnung:
                                    bezeichnung = ersatzteil['Bezeichnung']
                        
                        conn.execute('''
                            INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Bestellnummer, Bezeichnung, Bemerkung)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (anfrage_id, ersatzteil_id, menge, bestellnummer, bezeichnung, pos_bemerkung))
                    except (ValueError, IndexError):
                        continue
                
                conn.commit()
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
                e.Preis AS AktuellerPreis,
                e.Waehrung AS AktuelleWaehrung
            FROM AngebotsanfragePosition p
            LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
            WHERE p.AngebotsanfrageID = ?
            ORDER BY p.ID
        ''', (angebotsanfrage_id,)).fetchall()
        
        # PDF-Dateien aus Ordner laden
        dateien = get_angebotsanfrage_dateien(angebotsanfrage_id)
    
    return render_template(
        'angebotsanfrage_detail.html',
        anfrage=anfrage,
        positionen=positionen,
        dateien=dateien
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
    bestellnummer = request.form.get('bestellnummer', '').strip() or None
    bezeichnung = request.form.get('bezeichnung', '').strip() or None
    bemerkung = request.form.get('bemerkung', '').strip() or None
    
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
                # Falls ErsatzteilID vorhanden und Bestellnummer/Bezeichnung nicht angegeben, aus Ersatzteil laden
                if ersatzteil_id and (not bestellnummer or not bezeichnung):
                    ersatzteil = conn.execute('SELECT Bestellnummer, Bezeichnung FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
                    if ersatzteil:
                        if not bestellnummer:
                            bestellnummer = ersatzteil['Bestellnummer']
                        if not bezeichnung:
                            bezeichnung = ersatzteil['Bezeichnung']
                
                # Position hinzufügen
                conn.execute('''
                    INSERT INTO AngebotsanfragePosition (AngebotsanfrageID, ErsatzteilID, Menge, Bestellnummer, Bezeichnung, Bemerkung)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (angebotsanfrage_id, ersatzteil_id, menge, bestellnummer, bezeichnung, bemerkung))
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
            bemerkung = request.form.get('bemerkung', '').strip() or None
            
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
            
            # Position aktualisieren
            conn.execute('''
                UPDATE AngebotsanfragePosition SET
                    ErsatzteilID = ?,
                    Bestellnummer = ?,
                    Bezeichnung = ?,
                    Menge = ?,
                    Bemerkung = ?
                WHERE ID = ? AND AngebotsanfrageID = ?
            ''', (ersatzteil_id_int, bestellnummer, bezeichnung, menge, bemerkung, position_id, angebotsanfrage_id))
            
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
            # Prüfe ob Anfrage existiert und Status 'Offen' ist
            anfrage = conn.execute('''
                SELECT a.Status, a.LieferantID 
                FROM Angebotsanfrage a 
                WHERE a.ID = ?
            ''', (angebotsanfrage_id,)).fetchone()
            
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            if anfrage['Status'] != 'Offen':
                flash('Artikel können nur bei offenen Anfragen erstellt werden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
            
            # Position laden
            position = conn.execute('''
                SELECT ID, ErsatzteilID, Bestellnummer, Bezeichnung, Menge, Bemerkung
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
            
            # Neuen Artikel erstellen
            cursor = conn.execute('''
                INSERT INTO Ersatzteil (
                    Bestellnummer, Bezeichnung, Beschreibung, LieferantID, 
                    AktuellerBestand, Mindestbestand, Einheit, ErstelltVonID, Aktiv, Gelöscht
                ) VALUES (?, ?, ?, ?, 0, 0, 'Stück', ?, 1, 0)
            ''', (position['Bestellnummer'], position['Bezeichnung'], position['Bemerkung'], 
                  anfrage['LieferantID'], mitarbeiter_id))
            
            neuer_artikel_id = cursor.lastrowid
            
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
            upload_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], str(angebotsanfrage_id))
            os.makedirs(upload_folder, exist_ok=True)
            
            # Datei speichern
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
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
    
    # Sicherheitsprüfung: Dateipfad muss mit Angebote beginnen
    if not filepath.startswith('Angebote/'):
        flash('Ungültiger Dateipfad.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
    
    # Pfad für Dateisystem: Backslashes für Windows
    filepath_for_fs = filepath.replace('/', os.sep)
    full_path = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], filepath_for_fs)
    
    if not os.path.exists(full_path):
        flash('Datei nicht gefunden.', 'danger')
        return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
    
    # Angebotsanfrage-ID aus Pfad extrahieren
    parts = filepath.split('/')
    if len(parts) >= 2:
        angebotsanfrage_id = parts[1]
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
    """PDF-Export für eine Angebotsanfrage"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Angebotsanfrage laden
            anfrage = conn.execute("""
                SELECT 
                    a.*,
                    l.Name AS LieferantName,
                    l.Strasse AS LieferantStrasse,
                    l.PLZ AS LieferantPLZ,
                    l.Ort AS LieferantOrt,
                    l.Telefon AS LieferantTelefon,
                    l.Email AS LieferantEmail,
                    m.Vorname || ' ' || m.Nachname AS ErstelltVon,
                    m.Email AS ErstelltVonEmail,
                    m.Handynummer AS ErstelltVonHandy
                FROM Angebotsanfrage a
                LEFT JOIN Lieferant l ON a.LieferantID = l.ID
                LEFT JOIN Mitarbeiter m ON a.ErstelltVonID = m.ID
                WHERE a.ID = ?
            """, (angebotsanfrage_id,)).fetchone()
            
            if not anfrage:
                flash('Angebotsanfrage nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.angebotsanfrage_liste'))
            
            # Positionen laden
            positionen = conn.execute("""
                SELECT 
                    p.*,
                    e.ID AS ErsatzteilID,
                    COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
                    COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
                    e.Preis AS AktuellerPreis,
                    e.Waehrung AS AktuelleWaehrung
                FROM AngebotsanfragePosition p
                LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
                WHERE p.AngebotsanfrageID = ?
                ORDER BY p.ID
            """, (angebotsanfrage_id,)).fetchall()
            
            # Firmendaten laden
            firmendaten = get_firmendaten()
            
            # PDF erstellen
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4,
                                    rightMargin=2*cm, leftMargin=2*cm,
                                    topMargin=2*cm, bottomMargin=2*cm)
            
            story = []
            styles = getSampleStyleSheet()
            
            # Text-Styles
            normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, leading=14)
            small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10)
            bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold')
            
            # ========== HEADER: Logo rechts oben ==========
            if firmendaten and firmendaten['LogoPfad'] and os.path.exists(firmendaten['LogoPfad']):
                try:
                    logo = Image(firmendaten['LogoPfad'], width=5*cm, height=2.5*cm)
                    logo.hAlign = 'RIGHT'
                    story.append(logo)
                except:
                    pass
            story.append(Spacer(1, 0.3*cm))
            
            # ========== Firmendaten rechts, Lieferant links ==========
            # Firmendaten rechts
            firmen_text = []
            if firmendaten:
                if firmendaten['Firmenname']:
                    firmen_text.append(Paragraph(f"<b>{firmendaten['Firmenname']}</b>", small_style))
                if firmendaten['Strasse']:
                    firmen_text.append(Paragraph(firmendaten['Strasse'], small_style))
                if firmendaten['PLZ'] and firmendaten['Ort']:
                    firmen_text.append(Paragraph(f"{firmendaten['PLZ']} {firmendaten['Ort']}", small_style))
                
                # Lieferanschrift (falls abweichend)
                if firmendaten['LieferStrasse'] or firmendaten['LieferPLZ'] or firmendaten['LieferOrt']:
                    firmen_text.append(Spacer(1, 0.15*cm))
                    firmen_text.append(Paragraph('<b>Lieferanschrift:</b>', small_style))
                    if firmendaten['LieferStrasse']:
                        firmen_text.append(Paragraph(firmendaten['LieferStrasse'], small_style))
                    if firmendaten['LieferPLZ'] and firmendaten['LieferOrt']:
                        firmen_text.append(Paragraph(f"{firmendaten['LieferPLZ']} {firmendaten['LieferOrt']}", small_style))
                
                firmen_text.append(Spacer(1, 0.1*cm))
                if firmendaten['Telefon']:
                    firmen_text.append(Paragraph(f"Tel: {firmendaten['Telefon']}", small_style))
                if firmendaten['Website']:
                    firmen_text.append(Paragraph(f"Internet: {firmendaten['Website']}", small_style))
                if firmendaten['Email']:
                    firmen_text.append(Paragraph(f"E-Mail: {firmendaten['Email']}", small_style))
            
            # Lieferantendaten links
            lieferant_text = []
            if anfrage['LieferantName']:
                lieferant_text.append(Paragraph(f"<b>{anfrage['LieferantName']}</b>", normal_style))
                if anfrage['LieferantStrasse']:
                    lieferant_text.append(Paragraph(anfrage['LieferantStrasse'], normal_style))
                if anfrage['LieferantPLZ'] and anfrage['LieferantOrt']:
                    lieferant_text.append(Paragraph(f"{anfrage['LieferantPLZ']} {anfrage['LieferantOrt']}", normal_style))
            
            # Tabelle für Lieferant links, Firmendaten rechts
            left_col = [[p] for p in lieferant_text] if lieferant_text else [[Paragraph('', normal_style)]]
            right_col = [[p] for p in firmen_text] if firmen_text else [[Paragraph('', normal_style)]]
            
            left_table = Table(left_col, colWidths=[9*cm])
            right_table = Table(right_col, colWidths=[8*cm])
            
            top_table = Table([[left_table, right_table]], colWidths=[9*cm, 8*cm])
            top_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ]))
            story.append(top_table)
            story.append(Spacer(1, 1.5*cm))
            
            # ========== ANGEBOTSANFRAGE Titel ==========
            angebot_data = [[
                Paragraph(f'<font size="22"><b>ANGEBOTSANFRAGE</b></font>', bold_style),
                Paragraph(f'<font size="18"><b>{anfrage["ID"]}</b></font>', bold_style)
            ]]
            angebot_table = Table(angebot_data, colWidths=[12*cm, 5*cm])
            angebot_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ]))
            story.append(angebot_table)
            
            # Trennlinie unter Titel
            story.append(Table([['']], colWidths=[17*cm], style=TableStyle([
                ('LINEBELOW', (0, 0), (0, 0), 1, colors.black),
                ('TOPPADDING', (0, 0), (0, 0), 0),
                ('BOTTOMPADDING', (0, 0), (0, 0), 0),
            ])))
            story.append(Spacer(1, 0.5*cm))
            
            # ========== Datum und weitere Infos ==========
            info_data = []
            if anfrage['ErstelltAm']:
                datum = datetime.strptime(anfrage['ErstelltAm'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                info_data.append([Paragraph('<b>Datum:</b>', small_style), Paragraph(datum, small_style)])
            
            if anfrage['ErstelltVon']:
                angefragt_text = anfrage['ErstelltVon']
                kontakt_details = []
                if anfrage['ErstelltVonEmail']:
                    kontakt_details.append(f"E-Mail: {anfrage['ErstelltVonEmail']}")
                if anfrage['ErstelltVonHandy']:
                    kontakt_details.append(f"Tel: {anfrage['ErstelltVonHandy']}")
                
                if kontakt_details:
                    angefragt_text += f"<br/><font size='7' color='gray'>{' | '.join(kontakt_details)}</font>"
                
                info_data.append([Paragraph('<b>Angefragt von:</b>', small_style), Paragraph(angefragt_text, small_style)])
            
            if info_data:
                info_table = Table(info_data, colWidths=[3*cm, 14*cm])
                info_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(info_table)
            
            story.append(Spacer(1, 0.8*cm))
            
            # ========== Anrede und Einleitung ==========
            greeting = "Sehr geehrte Damen und Herren,<br/><br/>Ich bitte um Preis- und Lieferauskunft für folgende Ersatzteile:"
            story.append(Paragraph(greeting, normal_style))
            story.append(Spacer(1, 0.6*cm))
            
            # Bemerkung (falls vorhanden)
            if anfrage['Bemerkung']:
                story.append(Paragraph(anfrage['Bemerkung'], normal_style))
                story.append(Spacer(1, 0.6*cm))
            
            # ========== Positionstabelle ==========
            if positionen:
                pos_data = []
                # Header
                pos_data.append([
                    Paragraph('<b>Pos</b>', small_style),
                    Paragraph('<b>Artikel-Nr.</b>', small_style),
                    Paragraph('<b>Bezeichnung</b>', small_style),
                    Paragraph('<b>Menge</b>', small_style)
                ])
                
                # Positionen
                for idx, pos in enumerate(positionen, 1):
                    artikel_nr = pos['Bestellnummer'] or str(pos['ErsatzteilID']) if pos['ErsatzteilID'] else '-'
                    bezeichnung = pos['Bezeichnung'] or '-'
                    menge_val = pos['Menge'] if pos['Menge'] else 1.0
                    menge_text = f"{menge_val:.2f} Stück"
                    
                    # Bemerkung als Sub-Position
                    bez_text = bezeichnung
                    if pos['Bemerkung']:
                        bez_text += f"<br/><font size='7' color='gray'>{pos['Bemerkung']}</font>"
                    
                    pos_data.append([
                        Paragraph(str(idx), small_style),
                        Paragraph(f"<b>{artikel_nr}</b>", small_style),
                        Paragraph(bez_text, normal_style),
                        Paragraph(menge_text, small_style)
                    ])
                
                pos_table = Table(pos_data, colWidths=[1*cm, 2.5*cm, 10.5*cm, 3*cm])
                pos_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ]))
                story.append(pos_table)
                story.append(Spacer(1, 0.3*cm))
                
                # MwSt-Hinweis
                #story.append(Paragraph('<i>alle Preise verstehen sich zzgl. der gesetzl. MwSt.</i>', 
                #                     ParagraphStyle('Hinweis', parent=small_style, fontSize=8)))
            
            story.append(Spacer(1, 1*cm))
            
            # ========== Zahlungs- und Lieferbedingungen ==========
            # bedingungen = []
            # bedingungen.append([Paragraph('<b>Zahlungsbedingung:</b>', small_style), 
            #                   Paragraph('Zahlbar netto Kasse nach Erhalt der Rechnung.', small_style)])
            
            # bed_table = Table(bedingungen, colWidths=[4*cm, 13*cm])
            # bed_table.setStyle(TableStyle([
            #     ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            # ]))
            # story.append(bed_table)
            # story.append(Spacer(1, 1*cm))
            
            # ========== Footer mit rechtlichen Infos ==========
            footer_lines = []
            if firmendaten:
                if firmendaten['Geschaeftsfuehrer']:
                    footer_lines.append(f"Geschäftsführer: {firmendaten['Geschaeftsfuehrer']}")
                if firmendaten['UStIdNr']:
                    footer_lines.append(f"UStIdNr.: {firmendaten['UStIdNr']}")
                if firmendaten['Steuernummer']:
                    footer_lines.append(f"Steuernr.: {firmendaten['Steuernummer']}")
                if firmendaten['Telefon']:
                    footer_lines.append(f"Telefon: {firmendaten['Telefon']}")
                if firmendaten['BankName'] and firmendaten['IBAN']:
                    footer_lines.append(f"Bankverbindung: {firmendaten['BankName']}")
                    footer_lines.append(f"IBAN: {firmendaten['IBAN']}")
                    if firmendaten['BIC']:
                        footer_lines.append(f"BIC: {firmendaten['BIC']}")
            
            if footer_lines:
                # Footer-Text mit Pipe-Trennzeichen
                footer_text = ' | '.join(footer_lines)
                footer_para = Paragraph(footer_text, ParagraphStyle('Footer', parent=small_style, fontSize=7, alignment=TA_CENTER))
                story.append(Spacer(1, 1*cm))
                story.append(footer_para)
            
            # PDF generieren
            doc.build(story)
            
            # PDF als Download senden
            filename = f"Angebotsanfrage_{angebotsanfrage_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
            response = make_response(buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response
            
    except Exception as e:
        flash(f'Fehler beim Erstellen des PDFs: {str(e)}', 'danger')
        print(f"PDF-Export Fehler: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=angebotsanfrage_id))
