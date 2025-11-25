"""
Lagerbuchungs-Routen - Verwaltung von Lagerbuchungen
"""

from flask import render_template, request, redirect, url_for, session, flash, jsonify
from .. import ersatzteile_bp
from utils import get_db_connection, login_required, permission_required, get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_ersatzteil_zugriff_filter
from ..services import create_lagerbuchung, create_inventur_buchung
from ..utils import hat_ersatzteil_zugriff


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
                l.BestellungID,
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
            thema = conn.execute('SELECT ID FROM SchichtbuchThema WHERE ID = ? AND Gelöscht = 0', (thema_id,)).fetchone()
            if not thema:
                flash('Thema nicht gefunden.', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            # Prüfe ob Ersatzteil existiert
            ersatzteil = conn.execute('SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil WHERE ID = ? AND Gelöscht = 0', (ersatzteil_id,)).fetchone()
            if not ersatzteil:
                flash('Ersatzteil nicht gefunden.', 'danger')
                return redirect(url_for('schichtbuch.thema_detail', thema_id=thema_id))
            
            # Lagerbuchung über Service erstellen (Ausgang, da Ersatzteil für Thema verwendet wird)
            success, message, neuer_bestand = create_lagerbuchung(
                ersatzteil_id=ersatzteil_id,
                typ='Ausgang',
                menge=menge,
                grund='Thema-Verknüpfung',
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
                
    except Exception as e:
        flash(f'Fehler bei der Verknüpfung: {str(e)}', 'danger')
        print(f"Thema verknüpfen Fehler: {e}")
        import traceback
        traceback.print_exc()
    
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
            
            aktueller_bestand = ersatzteil['AktuellerBestand'] or 0
            
            # Inventur-Buchung über Service erstellen
            success, message = create_inventur_buchung(
                ersatzteil_id=ersatzteil_id,
                neuer_bestand=neuer_bestand,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                bemerkung=f'Inventur: Bestand von {aktueller_bestand} auf {neuer_bestand} geändert'
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
