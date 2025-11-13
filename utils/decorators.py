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
    """Decorator: Überprüft, ob User eingeloggt ist"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte zuerst anmelden.', 'warning')
            # Speichere die ursprüngliche URL als next-Parameter
            # Und Personalnummer falls vorhanden
            personalnummer = request.args.get('personalnummer')
            login_url = url_for('auth.login', next=request.url)
            if personalnummer:
                login_url = url_for('auth.login', next=request.url, personalnummer=personalnummer)
            return redirect(login_url)
        return view_func(*args, **kwargs)
    return wrapper


def admin_required(view_func):
    """Decorator: Überprüft, ob User eingeloggt ist und Admin-Berechtigung hat"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # Prüfe, ob AJAX-Request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
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
            return redirect(url_for('dashboard'))
        
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
            
            # Login-Prüfung
            if 'user_id' not in session:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Bitte zuerst anmelden.'}), 401
                flash('Bitte zuerst anmelden.', 'warning')
                personalnummer = request.args.get('personalnummer')
                login_url = url_for('auth.login', next=request.url)
                if personalnummer:
                    login_url = url_for('auth.login', next=request.url, personalnummer=personalnummer)
                return redirect(login_url)
            
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
                return redirect(url_for('dashboard'))
            
            return view_func(*args, **kwargs)
        return wrapper
    return decorator