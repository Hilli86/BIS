"""
Search Routes
Routes für globale Suche
"""

from flask import render_template, request, jsonify, session, url_for
from . import search_bp
from utils import get_db_connection, login_required
from . import services


@search_bp.route('', methods=['GET'])
@login_required
def search():
    """
    Globale Suche - unterstützt JSON (AJAX) und HTML
    
    Query-Parameter:
    - q: Suchbegriff (z.B. "123", "t123", "t@123", "e@ABC-123")
    - format: 'json' für JSON-Response, sonst HTML
    """
    mitarbeiter_id = session.get('user_id')
    is_admin = 'admin' in session.get('user_berechtigungen', [])
    query_string = request.args.get('q', '').strip()
    response_format = request.args.get('format', 'html')
    
    if not query_string:
        if response_format == 'json':
            return jsonify({
                'success': True,
                'results': {
                    'themen': [],
                    'ersatzteile': [],
                    'bestellungen': [],
                    'angebotsanfragen': []
                }
            })
        return render_template('search/search_results.html', 
                             query='',
                             results={
                                 'themen': [],
                                 'ersatzteile': [],
                                 'bestellungen': [],
                                 'angebotsanfragen': []
                             })
    
    # Query parsen
    parsed_query = services.parse_search_query(query_string)
    
    try:
        with get_db_connection() as conn:
            # Suche durchführen
            results = services.search_all(parsed_query, mitarbeiter_id, conn, is_admin, limit_per_type=10)
            
            # URLs für jeden Treffer hinzufügen
            for thema in results['themen']:
                thema['url'] = url_for('schichtbuch.thema_detail', thema_id=thema['ID'])
            
            for ersatzteil in results['ersatzteile']:
                ersatzteil['url'] = url_for('ersatzteile.ersatzteil_detail', ersatzteil_id=ersatzteil['ID'])
            
            for bestellung in results['bestellungen']:
                bestellung['url'] = url_for('ersatzteile.bestellung_detail', bestellung_id=bestellung['ID'])
            
            for anfrage in results['angebotsanfragen']:
                anfrage['url'] = url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=anfrage['ID'])
            
            # JSON-Response für AJAX
            if response_format == 'json':
                return jsonify({
                    'success': True,
                    'query': query_string,
                    'results': results
                })
            
            # HTML-Response
            return render_template('search/search_results.html',
                                 query=query_string,
                                 results=results)
    
    except Exception as e:
        error_msg = f'Fehler bei der Suche: {str(e)}'
        if response_format == 'json':
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
        
        return render_template('search/search_results.html',
                             query=query_string,
                             results={
                                 'themen': [],
                                 'ersatzteile': [],
                                 'bestellungen': [],
                                 'angebotsanfragen': []
                             },
                             error=error_msg)
