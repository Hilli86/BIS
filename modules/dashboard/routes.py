"""
Dashboard Routes
Routes für Dashboard-Übersicht und API-Endpunkte
"""

from flask import render_template, request, redirect, url_for, session, jsonify, current_app
from . import dashboard_bp
from utils import get_db_connection, get_sichtbare_abteilungen_fuer_mitarbeiter, login_required
from utils.helpers import row_to_dict
from . import services


@dashboard_bp.route('/')
@login_required
def dashboard():
    """Dashboard - Übersicht (schnelles Rendern, Daten werden per AJAX nachgeladen)"""
    # URL-Parameter (z.B. personalnummer) an Login-Route weitergeben
    personalnummer = request.args.get('personalnummer')
    if personalnummer:
        return redirect(url_for('auth.login', personalnummer=personalnummer, next=url_for('dashboard.dashboard')))
    
    # Schnelles Rendern ohne Datenbankabfragen
    return render_template('dashboard/dashboard.html')


@dashboard_bp.route('/api')
@dashboard_bp.route('/api/dashboard')
def api_dashboard():
    """API-Endpunkt für Dashboard-Daten"""
    if 'user_id' not in session:
        return jsonify({'error': 'Nicht angemeldet'}), 401
    
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Sichtbare Abteilungen für den Mitarbeiter ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            
            # Status-Statistiken
            status_daten = services.get_status_statistiken(sichtbare_abteilungen, conn)
            
            # Gesamtanzahl aller Themen
            gesamt = services.get_gesamtanzahl_themen(sichtbare_abteilungen, conn)
            
            # Aktuelle Themen
            aktuelle_themen = services.get_aktuelle_themen(sichtbare_abteilungen, conn)
            
            # Meine offenen Themen
            meine_themen = services.get_meine_themen(mitarbeiter_id, sichtbare_abteilungen, conn)
            
            # Aktivitätsübersicht
            aktivitaeten = services.get_aktivitaeten(sichtbare_abteilungen, conn)
            
            # Ersatzteile-Statistiken
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            ersatzteil_stats_data = services.get_ersatzteil_statistiken(mitarbeiter_id, sichtbare_abteilungen, is_admin, conn)
            
            # Daten als JSON zurückgeben
            return jsonify({
                'success': True,
                'status_daten': [row_to_dict(row) for row in status_daten],
                'gesamt': gesamt,
                'aktuelle_themen': [row_to_dict(row) for row in aktuelle_themen],
                'meine_themen': [row_to_dict(row) for row in meine_themen],
                'aktivitaeten': [row_to_dict(row) for row in aktivitaeten],
                'ersatzteil_stats': {
                    'gesamt': ersatzteil_stats_data['gesamt'],
                    'warnungen': ersatzteil_stats_data['warnungen'],
                    'kategorien': ersatzteil_stats_data['kategorien']
                },
                'ersatzteil_warnungen': ersatzteil_stats_data['warnungen_liste']
            })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Dashboard API Fehler: {error_details}")
        return jsonify({'success': False, 'error': str(e), 'details': error_details}), 500


@dashboard_bp.route('/api/benachrichtigungen')
def api_benachrichtigungen():
    """API-Endpoint für Benachrichtigungen"""
    if 'user_id' not in session:
        return jsonify({'error': 'Nicht angemeldet'}), 401
    
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Ungelesene Benachrichtigungen
        benachrichtigungen = conn.execute('''
            SELECT ID, Titel, Nachricht, Gelesen, ErstelltAm, Modul, Aktion
            FROM Benachrichtigung
            WHERE MitarbeiterID = ?
            ORDER BY ErstelltAm DESC
            LIMIT 20
        ''', (user_id,)).fetchall()
        
        ungelesen_count = conn.execute('''
            SELECT COUNT(*) as count
            FROM Benachrichtigung
            WHERE MitarbeiterID = ? AND Gelesen = 0
        ''', (user_id,)).fetchone()['count']
    
    return jsonify({
        'benachrichtigungen': [row_to_dict(b) for b in benachrichtigungen],
        'ungelesen_count': ungelesen_count
    })

