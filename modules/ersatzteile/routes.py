"""
Ersatzteile Routes - Ersatzteilverwaltung, Lagerbuchungen, Verknüpfungen
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory, current_app
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from . import ersatzteile_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter


def hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
    """Prüft ob Mitarbeiter Zugriff auf Ersatzteil hat"""
    # Admin hat immer Zugriff
    mitarbeiter = conn.execute('SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?', (mitarbeiter_id,)).fetchone()
    if mitarbeiter:
        abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        if 'BIS-Admin' in [a for a in abteilungen if isinstance(a, str)]:
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
        is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
        
        # Basis-Query
        query = '''
            SELECT 
                e.ID,
                e.Artikelnummer,
                e.Bezeichnung,
                e.Hersteller,
                e.AktuellerBestand,
                e.Mindestbestand,
                e.Einheit,
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
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f'''
                AND e.ID IN (
                    SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                    WHERE AbteilungID IN ({placeholders})
                )
            '''
            params.extend(sichtbare_abteilungen)
        elif not is_admin:
            # Keine Berechtigung
            query += ' AND 1=0'
        
        # Filter anwenden
        if kategorie_filter:
            query += ' AND e.KategorieID = ?'
            params.append(kategorie_filter)
        
        if lieferant_filter:
            query += ' AND e.LieferantID = ?'
            params.append(lieferant_filter)
        
        if bestandswarnung:
            query += ' AND e.AktuellerBestand <= e.Mindestbestand AND e.Mindestbestand > 0'
        
        if q_filter:
            query += ' AND (e.Artikelnummer LIKE ? OR e.Bezeichnung LIKE ? OR e.Beschreibung LIKE ?)'
            search_term = f'%{q_filter}%'
            params.extend([search_term, search_term, search_term])
        
        # Sortierung
        sort_mapping = {
            'id': 'e.ID',
            'artikelnummer': 'e.Artikelnummer',
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
    typ_filter = request.args.get('typ')  # 'Eingang' oder 'Ausgang'
    kostenstelle_filter = request.args.get('kostenstelle')
    datum_von = request.args.get('datum_von')
    datum_bis = request.args.get('datum_bis')
    
    with get_db_connection() as conn:
        # Berechtigte Abteilungen ermitteln
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
        
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
                e.Artikelnummer,
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
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f'''
                AND e.ID IN (
                    SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                    WHERE AbteilungID IN ({placeholders})
                )
            '''
            params.extend(sichtbare_abteilungen)
        elif not is_admin:
            # Keine Berechtigung
            query += ' AND 1=0'
        
        # Filter anwenden
        if ersatzteil_filter:
            query += ' AND e.ID = ?'
            params.append(ersatzteil_filter)
        
        if typ_filter:
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
        
        query += ' ORDER BY l.Buchungsdatum DESC LIMIT 500'
        
        lagerbuchungen = conn.execute(query, params).fetchall()
        
        # Filter-Optionen laden
        # Nur Ersatzteile, auf die der Benutzer Zugriff hat
        ersatzteile_query = '''
            SELECT DISTINCT e.ID, e.Artikelnummer, e.Bezeichnung
            FROM Ersatzteil e
            JOIN Lagerbuchung l ON e.ID = l.ErsatzteilID
            WHERE e.Gelöscht = 0
        '''
        ersatzteile_params = []
        
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            ersatzteile_query += f'''
                AND e.ID IN (
                    SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                    WHERE AbteilungID IN ({placeholders})
                )
            '''
            ersatzteile_params.extend(sichtbare_abteilungen)
        elif not is_admin:
            ersatzteile_query += ' AND 1=0'
        
        ersatzteile_query += ' ORDER BY e.Artikelnummer'
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
        datum_bis=datum_bis
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
                m.Vorname || ' ' || m.Nachname AS ErstelltVon
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            LEFT JOIN Lieferant l ON e.LieferantID = l.ID
            LEFT JOIN Lagerort lo ON e.LagerortID = lo.ID
            LEFT JOIN Lagerplatz lp ON e.LagerplatzID = lp.ID
            LEFT JOIN Mitarbeiter m ON e.ErstelltVonID = m.ID
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
        
        # Thema-Verknüpfungen laden
        verknuepfungen = conn.execute('''
            SELECT 
                v.ID,
                v.Menge,
                v.VerwendetAm,
                v.Bemerkung,
                t.ID AS ThemaID,
                m.Vorname || ' ' || m.Nachname AS VerwendetVon
            FROM ErsatzteilThemaVerknuepfung v
            JOIN SchichtbuchThema t ON v.ThemaID = t.ID
            JOIN Mitarbeiter m ON v.VerwendetVonID = m.ID
            WHERE v.ErsatzteilID = ?
            ORDER BY v.VerwendetAm DESC
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
    is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
    
    if not is_admin:
        flash('Nur Administratoren können Ersatzteile anlegen.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_liste'))
    
    if request.method == 'POST':
        artikelnummer = request.form.get('artikelnummer', '').strip()
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
        
        # Validierung
        if not artikelnummer or not bezeichnung:
            flash('Artikelnummer und Bezeichnung sind erforderlich.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_neu'))
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Prüfe ob Artikelnummer bereits existiert
                existing = cursor.execute('SELECT ID FROM Ersatzteil WHERE Artikelnummer = ?', (artikelnummer,)).fetchone()
                if existing:
                    flash('Artikelnummer existiert bereits.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_neu'))
                
                # Ersatzteil anlegen
                cursor.execute('''
                    INSERT INTO Ersatzteil (
                        Artikelnummer, Bezeichnung, Beschreibung, KategorieID, Hersteller,
                        LieferantID, Preis, Waehrung, LagerortID, LagerplatzID, Mindestbestand,
                        AktuellerBestand, Einheit, ErstelltVonID
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ''', (artikelnummer, bezeichnung, beschreibung, kategorie_id, hersteller,
                      lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand, einheit, mitarbeiter_id))
                
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
        lagerplaetze=lagerplaetze
    )


@ersatzteile_bp.route('/<int:ersatzteil_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def ersatzteil_bearbeiten(ersatzteil_id):
    """Ersatzteil bearbeiten"""
    mitarbeiter_id = session.get('user_id')
    is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
    
    with get_db_connection() as conn:
        # Berechtigung prüfen
        if not is_admin and not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
            flash('Sie haben keine Berechtigung, dieses Ersatzteil zu bearbeiten.', 'danger')
            return redirect(url_for('ersatzteile.ersatzteil_liste'))
        
        if request.method == 'POST':
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
            
            if not bezeichnung:
                flash('Bezeichnung ist erforderlich.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_bearbeiten', ersatzteil_id=ersatzteil_id))
            
            try:
                # Ersatzteil aktualisieren
                conn.execute('''
                    UPDATE Ersatzteil SET
                        Bezeichnung = ?, Beschreibung = ?, KategorieID = ?, Hersteller = ?,
                        LieferantID = ?, Preis = ?, Waehrung = ?, LagerortID = ?, LagerplatzID = ?,
                        Mindestbestand = ?, Einheit = ?, Aktiv = ?
                    WHERE ID = ?
                ''', (bezeichnung, beschreibung, kategorie_id, hersteller,
                      lieferant_id, preis, waehrung, lagerort_id, lagerplatz_id, mindestbestand, einheit, aktiv, ersatzteil_id))
                
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
    is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
    
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


@ersatzteile_bp.route('/<int:ersatzteil_id>/lagerbuchung', methods=['POST'])
@login_required
def lagerbuchung(ersatzteil_id):
    """Lagerbuchung durchführen (Eingang/Ausgang)"""
    mitarbeiter_id = session.get('user_id')
    
    typ = request.form.get('typ')  # 'Eingang' oder 'Ausgang'
    menge = request.form.get('menge', type=int)
    grund = request.form.get('grund', '').strip()
    kostenstelle_id = request.form.get('kostenstelle_id') or None
    thema_id = request.form.get('thema_id') or None
    bemerkung = request.form.get('bemerkung', '').strip()
    
    if not typ or not menge or menge <= 0:
        flash('Typ und Menge sind erforderlich.', 'danger')
        return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
    
    try:
        with get_db_connection() as conn:
            # Berechtigung prüfen
            if not hat_ersatzteil_zugriff(mitarbeiter_id, ersatzteil_id, conn):
                flash('Sie haben keine Berechtigung für dieses Ersatzteil.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            # Aktuellen Bestand ermitteln
            ersatzteil = conn.execute('SELECT AktuellerBestand FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                flash('Ersatzteil nicht gefunden.', 'danger')
                return redirect(url_for('ersatzteile.ersatzteil_liste'))
            
            aktueller_bestand = ersatzteil['AktuellerBestand']
            
            # Bestand aktualisieren
            if typ == 'Eingang':
                neuer_bestand = aktueller_bestand + menge
            else:  # Ausgang
                neuer_bestand = aktueller_bestand - menge
                if neuer_bestand < 0:
                    flash('Bestand kann nicht negativ werden.', 'danger')
                    return redirect(url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil_id))
            
            # Lagerbuchung erstellen (NICHT löschbar!)
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ersatzteil_id, typ, menge, grund, thema_id, kostenstelle_id, mitarbeiter_id, bemerkung))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            
            conn.commit()
            flash(f'Lagerbuchung erfolgreich durchgeführt. Neuer Bestand: {neuer_bestand}', 'success')
            
    except Exception as e:
        flash(f'Fehler bei der Lagerbuchung: {str(e)}', 'danger')
        print(f"Lagerbuchung Fehler: {e}")
    
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
            ersatzteil = conn.execute('SELECT AktuellerBestand FROM Ersatzteil WHERE ID = ?', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                flash('Ersatzteil nicht gefunden.', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            aktueller_bestand = ersatzteil['AktuellerBestand']
            if aktueller_bestand < menge:
                flash(f'Nicht genug Bestand verfügbar. Verfügbar: {aktueller_bestand}', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            # Verknüpfung erstellen
            conn.execute('''
                INSERT INTO ErsatzteilThemaVerknuepfung (
                    ErsatzteilID, ThemaID, Menge, VerwendetVonID, Bemerkung
                ) VALUES (?, ?, ?, ?, ?)
            ''', (ersatzteil_id, thema_id, menge, mitarbeiter_id, bemerkung))
            
            # Automatische Lagerbuchung (Ausgang)
            neuer_bestand = aktueller_bestand - menge
            conn.execute('''
                INSERT INTO Lagerbuchung (
                    ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
                    VerwendetVonID, Bemerkung
                ) VALUES (?, 'Ausgang', ?, 'Thema', ?, ?, ?, ?)
            ''', (ersatzteil_id, menge, thema_id, kostenstelle_id, mitarbeiter_id, bemerkung))
            
            # Bestand aktualisieren
            conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', (neuer_bestand, ersatzteil_id))
            
            conn.commit()
            flash(f'Ersatzteil erfolgreich zugeordnet. Bestand reduziert um {menge}.', 'success')
            
    except Exception as e:
        flash(f'Fehler bei der Verknüpfung: {str(e)}', 'danger')
        print(f"Thema verknüpfen Fehler: {e}")
    
    return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))


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
        is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
        
        query = '''
            SELECT 
                e.ID,
                e.Artikelnummer,
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
        if not is_admin and sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f'''
                AND e.ID IN (
                    SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                    WHERE AbteilungID IN ({placeholders})
                )
            '''
            params.extend(sichtbare_abteilungen)
        elif not is_admin:
            query += ' AND 1=0'
        
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
    is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
    
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
    is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
    
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


