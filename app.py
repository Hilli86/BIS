"""
BIS - Betriebsinformationssystem
Modulare Flask-Anwendung mit Blueprints

Hauptdatei - nur Initialisierung und Blueprint-Registrierung
"""

from flask import Flask, render_template, session, redirect, url_for, request
import os
from config import config

# Flask App initialisieren
app = Flask(__name__)

# Konfiguration laden
config_name = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[config_name])

# Datenbank-Prüfung beim Start
with app.app_context():
    from utils.database_check import initialize_database_on_startup
    initialize_database_on_startup(app)

# Upload-Ordner erstellen falls nicht vorhanden
from utils.folder_setup import create_all_upload_folders
create_all_upload_folders(app)

# Benutzerdefinierte Jinja2-Filter
@app.template_filter('file_extension')
def file_extension(filename):
    """Extrahiert die Dateierweiterung aus einem Dateinamen"""
    if not filename:
        return ''
    parts = filename.rsplit('.', 1)
    return parts[1].lower() if len(parts) > 1 else ''

# Blueprints registrieren
from modules import auth_bp, schichtbuch_bp, admin_bp, ersatzteile_bp, dashboard_bp, import_bp, errors_bp

app.register_blueprint(auth_bp)
app.register_blueprint(schichtbuch_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ersatzteile_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(import_bp)
app.register_blueprint(errors_bp)


# ========== Main Routes ==========

@app.route('/')
def index():
    """Startseite - Redirect zu Dashboard oder Login"""
    if session.get('user_id'):
        return redirect(url_for('dashboard.dashboard'))
    # URL-Parameter (z.B. personalnummer) an Login-Route weitergeben
    personalnummer = request.args.get('personalnummer')
    if personalnummer:
        return redirect(url_for('auth.login', personalnummer=personalnummer))
    return redirect(url_for('auth.login'))


# ========== App starten ==========

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

