"""
Decorator Utilities
Dekoratoren für Routen (z.B. login_required)
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify
from urllib.parse import urlparse, urljoin


def is_safe_url(target):
    """Prüft, ob eine URL sicher ist (verhindert Open Redirects)"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def login_required(view_func):
    """Decorator: Überprüft, ob User eingeloggt ist. Blockiert Gast-Benutzer standardmäßig, außer wenn Route @guest_allowed hat."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # Prüfe auf normale Anmeldung (user_id) oder Gast-Login (is_guest)
        if 'user_id' not in session and not session.get('is_guest'):
            flash('Bitte zuerst anmelden.', 'warning')
            # Speichere die ursprüngliche URL als next-Parameter
            # Und Personalnummer falls vorhanden
            personalnummer = request.args.get('personalnummer')
            login_url = url_for('auth.login', next=request.url)
            if personalnummer:
                login_url = url_for('auth.login', next=request.url, personalnummer=personalnummer)
            return redirect(login_url)
        
        # Wenn Gast-Benutzer: Prüfe ob Route Gast erlaubt
        if session.get('is_guest'):
            # Whitelist von erlaubten Endpoints für Gast-Benutzer
            ALLOWED_GUEST_ENDPOINTS = ['produktion.etikettierung']
            
            # Prüfe ob aktueller Endpoint erlaubt ist
            current_endpoint = request.endpoint
            if current_endpoint not in ALLOWED_GUEST_ENDPOINTS:
                # Gast-Benutzer nicht erlaubt - zur Etikettierung umleiten
                flash('Zugriff verweigert. Diese Funktion ist nur für angemeldete Benutzer verfügbar.', 'warning')
                return redirect(url_for('produktion.etikettierung'))
        
        return view_func(*args, **kwargs)
    
    # Übertrage das _guest_allowed Attribut vom view_func auf den Wrapper
    if hasattr(view_func, '_guest_allowed'):
        wrapper._guest_allowed = view_func._guest_allowed
    
    return wrapper


def admin_required(view_func):
    """Decorator: Überprüft, ob User eingeloggt ist und Admin-Berechtigung hat"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # Prüfe, ob AJAX-Request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Gast-Benutzer haben keine Admin-Rechte
        if session.get('is_guest'):
            if is_ajax:
                return jsonify({'success': False, 'message': 'Zugriff verweigert. Gast-Benutzer haben keine Admin-Rechte.'}), 403
            flash('Zugriff verweigert. Gast-Benutzer haben keine Admin-Rechte.', 'danger')
            return redirect(url_for('produktion.etikettierung'))
        
        if 'user_id' not in session:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Bitte zuerst anmelden.'}), 401
            flash('Bitte zuerst anmelden.', 'warning')
            # Speichere die ursprüngliche URL als next-Parameter
            # Und Personalnummer falls vorhanden
            personalnummer = request.args.get('personalnummer')
            login_url = url_for('auth.login', next=request.url)
            if personalnummer:
                login_url = url_for('auth.login', next=request.url, personalnummer=personalnummer)
            return redirect(login_url)
        
        # Prüfe, ob Benutzer Admin-Berechtigung hat
        user_berechtigungen = session.get('user_berechtigungen', [])
        if 'admin' not in user_berechtigungen:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Zugriff verweigert. Sie benötigen Admin-Rechte.'}), 403
            flash('Zugriff verweigert. Sie benötigen Admin-Rechte.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        
        return view_func(*args, **kwargs)
    return wrapper


def permission_required(berechtigung_schluessel):
    """
    Decorator: Überprüft, ob User eine bestimmte Berechtigung hat
    
    Args:
        berechtigung_schluessel: Schlüssel der benötigten Berechtigung (z.B. 'artikel_buchen')
    
    Usage:
        @permission_required('artikel_buchen')
        def meine_route():
            pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            # Prüfe, ob AJAX-Request
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            
            # Login-Prüfung (normale Benutzer oder Gast)
            if 'user_id' not in session and not session.get('is_guest'):
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Bitte zuerst anmelden.'}), 401
                flash('Bitte zuerst anmelden.', 'warning')
                personalnummer = request.args.get('personalnummer')
                login_url = url_for('auth.login', next=request.url)
                if personalnummer:
                    login_url = url_for('auth.login', next=request.url, personalnummer=personalnummer)
                return redirect(login_url)
            
            # Gast-Benutzer haben keine spezifischen Berechtigungen
            if session.get('is_guest'):
                if is_ajax:
                    return jsonify({
                        'success': False, 
                        'message': 'Zugriff verweigert. Gast-Benutzer haben keine Berechtigungen.'
                    }), 403
                flash('Zugriff verweigert. Gast-Benutzer haben keine Berechtigungen.', 'danger')
                return redirect(url_for('produktion.etikettierung'))
            
            # Berechtigungs-Prüfung
            user_berechtigungen = session.get('user_berechtigungen', [])
            
            # Admin hat alle Berechtigungen
            if 'admin' in user_berechtigungen:
                return view_func(*args, **kwargs)
            
            # Prüfe spezifische Berechtigung
            if berechtigung_schluessel not in user_berechtigungen:
                if is_ajax:
                    return jsonify({
                        'success': False, 
                        'message': f'Zugriff verweigert. Sie benötigen die Berechtigung: {berechtigung_schluessel}'
                    }), 403
                flash(f'Zugriff verweigert. Sie benötigen die erforderliche Berechtigung.', 'danger')
                return redirect(url_for('dashboard.dashboard'))
            
            return view_func(*args, **kwargs)
        return wrapper
    return decorator


def guest_allowed(view_func):
    """
    Decorator: Markiert eine Route als für Gast-Benutzer zugänglich
    Setzt das Attribut _guest_allowed auf der Funktion, das von login_required geprüft wird.
    
    Wichtig: @guest_allowed muss VOR @login_required stehen!
    
    Usage:
        @guest_allowed  # Muss ZUERST stehen
        @login_required
        def meine_route():
            pass
    """
    # Setze Attribut auf der ursprünglichen Funktion
    view_func._guest_allowed = True
    
    # Erstelle einen Wrapper, der das Attribut auch hat
    # Damit login_required es finden kann, auch wenn es auf dem Wrapper prüft
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        return view_func(*args, **kwargs)
    
    # Setze Attribut auf dem Wrapper
    wrapper._guest_allowed = True
    # Auch auf der ursprünglichen Funktion behalten (für rekursive Suche)
    wrapper.__wrapped__ = view_func
    
    return wrapper