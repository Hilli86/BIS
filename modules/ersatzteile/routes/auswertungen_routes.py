"""
Auswertungen Routes - Auswertungen für Bestellungen und Ersatzteilwert
"""

from flask import render_template, request, session
from datetime import datetime
from .. import ersatzteile_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.abteilungen import get_untergeordnete_abteilungen
from ..services.auswertung_services import (
    get_bestellungen_auswertung,
    get_ersatzteilwert_auswertung,
    get_abteilungen_fuer_filter
)


@ersatzteile_bp.route('/auswertungen')
@login_required
def auswertungen():
    """Auswertungen für Bestellungen und Ersatzteilwert"""
    mitarbeiter_id = session.get('user_id')
    
    # Filter-Parameter aus Request lesen
    abteilung_filter_raw = request.args.get('abteilung', '').strip()
    lieferant_filter_raw = request.args.get('lieferant', '').strip()
    datum_von_raw = request.args.get('datum_von', '').strip()
    datum_bis_raw = request.args.get('datum_bis', '').strip()
    
    # Datum-Voreinstellungen
    heute = datetime.now()
    jahresbeginn = datetime(heute.year, 1, 1)
    
    # Datum-Parameter verarbeiten
    try:
        datum_von = datetime.strptime(datum_von_raw, '%Y-%m-%d') if datum_von_raw else jahresbeginn
    except ValueError:
        datum_von = jahresbeginn
    
    try:
        datum_bis = datetime.strptime(datum_bis_raw, '%Y-%m-%d') if datum_bis_raw else heute
    except ValueError:
        datum_bis = heute
    
    # Abteilungs-Filter verarbeiten
    abteilung_ids = None
    abteilung_filter = None
    if abteilung_filter_raw:
        try:
            abteilung_filter = int(abteilung_filter_raw)
        except ValueError:
            abteilung_filter = None
    
    # Lieferant-Filter verarbeiten
    lieferant_id = None
    lieferant_filter = None
    if lieferant_filter_raw:
        try:
            lieferant_filter = int(lieferant_filter_raw)
            lieferant_id = lieferant_filter
        except ValueError:
            lieferant_filter = None
    
    with get_db_connection() as conn:
        # Berechtigungen prüfen
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        # Wenn Abteilung gefiltert: Eigene Abteilung + alle Unterabteilungen rekursiv ermitteln
        if abteilung_filter:
            abteilung_ids = get_untergeordnete_abteilungen(abteilung_filter, conn)
        
        # Bestellungen-Auswertung berechnen
        bestellungen_auswertung = get_bestellungen_auswertung(
            abteilung_ids=abteilung_ids,
            lieferant_id=lieferant_id,
            datum_von=datum_von,
            datum_bis=datum_bis,
            conn=conn,
            is_admin=is_admin,
            sichtbare_abteilungen=sichtbare_abteilungen
        )
        
        # Ersatzteilwert-Auswertung berechnen
        ersatzteilwert_auswertung = get_ersatzteilwert_auswertung(
            abteilung_ids=abteilung_ids,
            lieferant_id=lieferant_id,
            conn=conn,
            mitarbeiter_id=mitarbeiter_id,
            is_admin=is_admin,
            sichtbare_abteilungen=sichtbare_abteilungen
        )
        
        # Filter-Optionen laden
        lieferanten = conn.execute(
            'SELECT ID, Name FROM Lieferant WHERE Aktiv = 1 AND Gelöscht = 0 ORDER BY Name'
        ).fetchall()
        
        abteilungen = get_abteilungen_fuer_filter(mitarbeiter_id, conn, is_admin=is_admin)
    
    return render_template(
        'auswertungen.html',
        bestellungen_auswertung=bestellungen_auswertung,
        ersatzteilwert_auswertung=ersatzteilwert_auswertung,
        abteilung_filter=abteilung_filter,
        lieferant_filter=lieferant_filter,
        datum_von=datum_von.strftime('%Y-%m-%d'),
        datum_bis=datum_bis.strftime('%Y-%m-%d'),
        lieferanten=lieferanten,
        abteilungen=abteilungen
    )
