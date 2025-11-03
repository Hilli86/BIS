"""
BIS - Betriebsinformationssystem
Modulare Flask-Anwendung mit Blueprints

Hauptdatei - nur Initialisierung und Blueprint-Registrierung
"""

from flask import Flask, render_template, session, redirect, url_for
import os
from config import config

# Flask App initialisieren
app = Flask(__name__)

# Konfiguration laden
config_name = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[config_name])

# Blueprints registrieren
from modules import auth_bp, schichtbuch_bp, admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(schichtbuch_bp)
app.register_blueprint(admin_bp)


# ========== Error Handler ==========

@app.errorhandler(404)
def not_found_error(error):
    """404 Fehlerseite"""
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 Fehlerseite"""
    return render_template('errors/500.html'), 500


# ========== Main Routes ==========

@app.route('/')
def index():
    """Startseite - Redirect zu Dashboard oder Login"""
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))


@app.route('/dashboard')
def dashboard():
    """Dashboard - Übersicht"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    from utils import get_db_connection
    
    with get_db_connection() as conn:
        # Zähle alle Themen gruppiert nach Status
        daten = conn.execute('''
            SELECT S.Bezeichnung AS Status, COUNT(T.ID) AS Anzahl
            FROM SchichtbuchThema T
            JOIN Status S ON S.ID = T.StatusID
            WHERE Gelöscht = 0
            GROUP BY S.Bezeichnung
            ORDER BY S.Bezeichnung
        ''').fetchall()

    return render_template('dashboard/dashboard.html', daten=daten)


# ========== App starten ==========

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

