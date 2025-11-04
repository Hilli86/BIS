"""
Decorator Utilities
Dekoratoren für Routen (z.B. login_required)
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(view_func):
    """Decorator: Überprüft, ob User eingeloggt ist"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte zuerst anmelden.', 'warning')
            return redirect(url_for('auth.login'))
        return view_func(*args, **kwargs)
    return wrapper


def admin_required(view_func):
    """Decorator: Überprüft, ob User eingeloggt ist und zur BIS-Admin Abteilung gehört"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte zuerst anmelden.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Prüfe, ob Benutzer in BIS-Admin Abteilung ist
        user_abteilungen = session.get('user_abteilungen', [])
        if 'BIS-Admin' not in user_abteilungen:
            flash('Zugriff verweigert. Sie benötigen Admin-Rechte (BIS-Admin Abteilung).', 'danger')
            return redirect(url_for('dashboard'))
        
        return view_func(*args, **kwargs)
    return wrapper
