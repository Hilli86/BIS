"""
BIS - Betriebsinformationssystem
Modulare Flask-Anwendung mit Blueprints

Hauptdatei - nur Initialisierung und Blueprint-Registrierung
"""

from flask import Flask, render_template, session, redirect, url_for, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
import click
import os
from config import config, DEV_SECRET_KEY_FALLBACK

# Flask App initialisieren
app = Flask(__name__)

# ProxyFix: Hinter nginx/reverse-proxy korrekte URLs (https statt http) für request.url etc.
# X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-For werden von nginx gesetzt
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Konfiguration laden
config_name = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[config_name])

# Produktion: Session-Sicherheit – kein Default-Schlüssel
if config_name == 'production':
    sk = app.config.get('SECRET_KEY')
    if not sk or sk == DEV_SECRET_KEY_FALLBACK:
        raise RuntimeError(
            'Produktion (FLASK_ENV=production): SECRET_KEY muss per Umgebungsvariable gesetzt sein '
            'und darf nicht dem Entwicklungs-Default entsprechen.'
        )

# Datenbank-Prüfung beim Start
with app.app_context():
    from utils.database_check import initialize_database_on_startup
    initialize_database_on_startup(app)
    
    # Automatische Bereinigung alter Benachrichtigungen
    try:
        from utils.benachrichtigungen_cleanup import bereinige_benachrichtigungen_automatisch
        bereinige_benachrichtigungen_automatisch(app)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Fehler beim automatischen Cleanup von Benachrichtigungen: {str(e)}")

    # Ausstehende E-Mail/Push-Versände (ältere pending-Einträge) einmal abarbeiten
    try:
        from utils.benachrichtigungen import versende_alle_benachrichtigungen
        versende_alle_benachrichtigungen()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Fehler beim Nachversand ausstehender Benachrichtigungen: {str(e)}")

# Upload-Ordner erstellen falls nicht vorhanden
from utils.folder_setup import create_all_upload_folders
create_all_upload_folders(app)

# Benutzerdefinierte Jinja2-Filter und Globals
@app.template_filter('file_extension')
def file_extension(filename):
    """Extrahiert die Dateierweiterung aus einem Dateinamen"""
    if not filename:
        return ''
    parts = filename.rsplit('.', 1)
    return parts[1].lower() if len(parts) > 1 else ''


@app.template_filter('schichtbuch_datum')
def schichtbuch_datum_filter(value):
    """Schichtbuch-Datum: bei 00:00:00 nur Tag, sonst Tag + Uhrzeit."""
    from utils.helpers import format_schichtbuch_datum
    return format_schichtbuch_datum(value)


@app.before_request
def _ensure_menue_sichtbarkeit():
    """Lädt user_menue_sichtbarkeit für eingeloggte Benutzer (auch nach Admin-Änderungen)."""
    if session.get('user_id') and not session.get('is_guest'):
        from utils.menue_definitions import get_menue_sichtbarkeit_fuer_mitarbeiter
        session['user_menue_sichtbarkeit'] = get_menue_sichtbarkeit_fuer_mitarbeiter(session['user_id'])


@app.template_global('menue_sichtbar')
def menue_sichtbar(schluessel):
    """
    Prüft ob ein Menüpunkt für den aktuellen Benutzer sichtbar ist.
    Nutzt session['user_menue_sichtbarkeit'].
    """
    sichtbarkeit = session.get('user_menue_sichtbarkeit', {})
    return sichtbarkeit.get(schluessel, True)


# Blueprints registrieren
from modules import auth_bp, schichtbuch_bp, admin_bp, ersatzteile_bp, dashboard_bp, import_bp, errors_bp, diverses_bp, search_bp, produktion_bp, wartungen_bp

app.register_blueprint(auth_bp)
app.register_blueprint(schichtbuch_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ersatzteile_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(import_bp)
app.register_blueprint(errors_bp)
app.register_blueprint(diverses_bp)
app.register_blueprint(search_bp)
app.register_blueprint(produktion_bp)
app.register_blueprint(wartungen_bp)


@app.route('/service-worker.js')
def service_worker():
    """
    Liefert den Service Worker mit Scope / (Header Service-Worker-Allowed).
    Registrierung nur unter /static/ führt zu Scope /static/ und kann Web-Push
    (push service error) in Browsern verhindern.
    """
    response = send_from_directory(
        app.static_folder,
        'service-worker.js',
        mimetype='application/javascript',
    )
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


# ========== Main Routes ==========

@app.route('/')
def index():
    """Startseite - Redirect zu Dashboard, Etikettierung oder Login"""
    # Gast-Benutzer zur Etikettierung
    if session.get('is_guest'):
        return redirect(url_for('produktion.etikettierung'))
    # Normale Benutzer zum Dashboard
    if session.get('user_id'):
        return redirect(url_for('dashboard.dashboard'))
    # Nicht angemeldet zum Login
    # URL-Parameter (z.B. personalnummer) an Login-Route weitergeben
    personalnummer = request.args.get('personalnummer')
    if personalnummer:
        return redirect(url_for('auth.login', personalnummer=personalnummer))
    return redirect(url_for('auth.login'))


@app.cli.command('push-test')
@click.argument('mitarbeiter_id', type=int)
def cli_push_test(mitarbeiter_id):
    """
    Sendet eine Test-Push an einen Mitarbeiter (Web-Push, wie im Profil).

    Voraussetzungen: VAPID-Keys, pywebpush, gespeicherte Push-Subscription für die ID.

    Beispiel: flask --app app push-test 42
    """
    from utils.benachrichtigungen_push import versende_test_push

    ok, err = versende_test_push(mitarbeiter_id)
    if ok:
        click.echo(f'Test-Push an Mitarbeiter {mitarbeiter_id} gesendet.')
        return
    click.echo(f'Fehler: {err}', err=True)
    raise SystemExit(1)


@app.cli.command('vapid-generate')
@click.option(
    '-o', '--output',
    'pem_path',
    default=None,
    type=click.Path(dir_okay=False, path_type=str),
    help='Pfad für die private PEM-Datei (Standard: <instance>/vapid_private.pem)',
)
def cli_vapid_generate(pem_path):
    """
    Erzeugt VAPID-Schlüssel für Web-Push und speichert den privaten Schlüssel als PEM.

    Anschließend Umgebungsvariablen setzen und App neu starten, z. B. PowerShell:

    \b
        $env:VAPID_PRIVATE_KEY = "C:\\Pfad\\zur\\vapid_private.pem"
        $env:VAPID_PUBLIC_KEY = "<aus der Ausgabe kopieren>"
        $env:VAPID_EMAIL = "admin@example.com"

    VAPID_PRIVATE_KEY kann der volle Pfad zur PEM-Datei sein (von pywebpush unterstützt).
    """
    from pathlib import Path
    from utils.vapid_setup import generate_vapid_files

    target = pem_path or str(Path(app.instance_path) / 'vapid_private.pem')
    public_b64 = generate_vapid_files(target)

    click.echo('')
    click.echo('VAPID-Schlüssel erzeugt.')
    click.echo('')
    click.echo('Private PEM (geheim, nicht ins Repository einchecken):')
    click.echo(f'  {Path(target).resolve()}')
    click.echo('')
    click.echo('Setzen Sie diese Umgebungsvariablen:')
    click.echo('')
    click.echo(f'  VAPID_PRIVATE_KEY = {Path(target).resolve()}')
    click.echo(f'  VAPID_PUBLIC_KEY = {public_b64}')
    click.echo('  VAPID_EMAIL = <Ihre Kontakt-E-Mail für VAPID (mailto: im Token)>')
    click.echo('')
    click.echo('PowerShell (nur diese Sitzung):')
    click.echo(f'  $env:VAPID_PRIVATE_KEY = \'{Path(target).resolve()}\'')
    click.echo(f'  $env:VAPID_PUBLIC_KEY = \'{public_b64}\'')
    click.echo('')


@app.cli.command('vapid-verify')
def cli_vapid_verify():
    """Prüft, ob VAPID_PUBLIC_KEY zum privaten Schlüssel passt (Umgebung / .env)."""
    from utils.vapid_setup import verify_vapid_pair

    priv = app.config.get('VAPID_PRIVATE_KEY')
    pub = app.config.get('VAPID_PUBLIC_KEY')
    ok, msg = verify_vapid_pair(priv, pub)
    if ok:
        click.echo(msg)
        return
    click.echo(msg, err=True)
    raise SystemExit(1)


# ========== App starten ==========

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

