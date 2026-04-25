import os
from datetime import timedelta

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Nur für lokale Entwicklung; in Produktion muss SECRET_KEY per Umgebungsvariable gesetzt sein.
DEV_SECRET_KEY_FALLBACK = 'dev-key-change-in-production-12345'


def _env_str_strip_optional(value):
    """Whitespace und umschließende Anführungszeichen (Windows-Umgebung) entfernen."""
    if value is None:
        return None
    s = str(value).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
        s = s[1:-1].strip()
    return s or None


class Config:
    """Basis-Konfiguration für die Flask-Anwendung"""
    
    # Sicherheit
    SECRET_KEY = os.environ.get('SECRET_KEY') or DEV_SECRET_KEY_FALLBACK
    
    # Datenbank
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'database_main.db'
    
    # Upload-Konfiguration
    UPLOAD_BASE_FOLDER = os.environ.get('UPLOAD_BASE_FOLDER') or os.path.join(os.getcwd(), 'Daten')
    SCHICHTBUCH_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Schichtbuch', 'Themen')
    ERSATZTEIL_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Ersatzteile')
    WARTUNG_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Wartungen')
    ANGEBOTE_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Angebote')
    IMPORT_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Import')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    
    # Session-Konfiguration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    # SESSION_COOKIE_SECURE wird pro Umgebung gesetzt (Development=False, Production=True).
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Lax')
    REMEMBER_COOKIE_SECURE = os.environ.get('REMEMBER_COOKIE_SECURE', 'False').lower() == 'true'

    # Vertrauenswuerdige Reverse-Proxies (komma-separierte IPs/CIDRs).
    # Nur fuer diese Gegenstellen werden X-Forwarded-For / X-Real-IP ausgewertet.
    # Beispiel (nginx vor der App): TRUSTED_PROXIES="127.0.0.1,10.0.0.0/8"
    TRUSTED_PROXIES = tuple(
        p.strip() for p in os.environ.get('TRUSTED_PROXIES', '').split(',') if p.strip()
    )
    
    # Debug-Modus (nur für Entwicklung)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # SQL-Tracing (nur für Entwicklung)
    SQL_TRACING = os.environ.get('SQL_TRACING', 'False').lower() == 'true'

    # Rate-Limiter Storage: im Single-Process-Betrieb (Dev) reicht memory://.
    # Bei Gunicorn-Multi-Worker muss ein geteilter Store genutzt werden,
    # z. B. redis://Redis-Service:6379/0 (Docker-Compose-Dienstname).
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    
    # E-Mail-Konfiguration für Benachrichtigungen
    MAIL_ENABLED = os.environ.get('MAIL_ENABLED', 'False').lower() == 'true'
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', None)
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', None)
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')
    MAIL_DEFAULT_SENDER_NAME = os.environ.get('MAIL_DEFAULT_SENDER_NAME', 'BIS System')
    
    # Push-Benachrichtigungen (VAPID) – Schlüssel z. B. mit: flask --app app vapid-generate
    # VAPID_PRIVATE_KEY: Pfad zur PEM-Datei oder PEM-Inhalt; VAPID_PUBLIC_KEY: eine Zeile Base64-URL
    VAPID_PRIVATE_KEY = _env_str_strip_optional(os.environ.get('VAPID_PRIVATE_KEY'))
    VAPID_PUBLIC_KEY = _env_str_strip_optional(os.environ.get('VAPID_PUBLIC_KEY'))
    VAPID_EMAIL = os.environ.get('VAPID_EMAIL', 'noreply@example.com')

    # WebAuthn / Passkeys (für biometrische Anmeldung, z.B. Windows Hello / FaceID)
    # Standardwerte können per Umgebungsvariablen überschrieben werden.
    # Intranet-Produktivsystem: https://10.40.140.243
    WEBAUTHN_RP_ID = os.environ.get('WEBAUTHN_RP_ID', 'localhost')
    WEBAUTHN_RP_NAME = os.environ.get('WEBAUTHN_RP_NAME', 'BIS – Betriebsinformationssystem')
    WEBAUTHN_ORIGIN = os.environ.get('WEBAUTHN_ORIGIN', 'http://localhost:5000')
    
    # Benachrichtigungen-Cleanup
    BENACHRICHTIGUNGEN_CLEANUP_AKTIV = os.environ.get('BENACHRICHTIGUNGEN_CLEANUP_AKTIV', 'True').lower() == 'true'
    BENACHRICHTIGUNGEN_CLEANUP_TAGE = int(os.environ.get('BENACHRICHTIGUNGEN_CLEANUP_TAGE', 30))
    BENACHRICHTIGUNGEN_CLEANUP_NUR_GELESENE = os.environ.get('BENACHRICHTIGUNGEN_CLEANUP_NUR_GELESENE', 'True').lower() == 'true'
    BENACHRICHTIGUNGEN_CLEANUP_LIMIT_PRO_MITARBEITER = int(os.environ.get('BENACHRICHTIGUNGEN_CLEANUP_LIMIT_PRO_MITARBEITER', 0)) or None

    # Passwort-Policy (Laenge, Zeichenklassen): True = volle Regeln aus utils.security.
    # Ueber BIS_PASSWORT_POLICY_STRENG=true|false steuerbar; wird in Development/Production unterschiedlich vorbelegt.
    PASSWORT_POLICY_STRENG = os.environ.get('BIS_PASSWORT_POLICY_STRENG', 'true').lower() in ('1', 'true', 'yes')


class DevelopmentConfig(Config):
    """Entwicklungskonfiguration"""
    DEBUG = True
    # Lokaler/kleiner Pilot: verschärfte Passwortregeln standardmaessig aus (nur nicht leer).
    PASSWORT_POLICY_STRENG = os.environ.get('BIS_PASSWORT_POLICY_STRENG', 'false').lower() in ('1', 'true', 'yes')
    # Einstweilen aus: sonst erscheint jede SQL-Abfrage in der Konsole (sqlite3 Trace).
    # Wieder aktivieren oder per Umgebungsvariable: SQL_TRACING=true
    # SQL_TRACING = True

class ProductionConfig(Config):
    """Produktionskonfiguration"""
    DEBUG = False
    SQL_TRACING = False
    # Produktiv: strenge Passwort-Policy; abschaltbar nur bewusst per BIS_PASSWORT_POLICY_STRENG=false
    PASSWORT_POLICY_STRENG = os.environ.get('BIS_PASSWORT_POLICY_STRENG', 'true').lower() in ('1', 'true', 'yes')

    # WebAuthn-Parameter muessen im Produktivbetrieb zwingend ueber
    # Umgebungsvariablen gesetzt werden – kein stilles Fallback auf Hostnamen,
    # da ein falscher Origin FIDO2-Authentifizierung scheitern laesst.
    WEBAUTHN_RP_ID = os.environ.get('WEBAUTHN_RP_ID')
    WEBAUTHN_RP_NAME = os.environ.get('WEBAUTHN_RP_NAME', 'BIS – Betriebsinformationssystem')
    WEBAUTHN_ORIGIN = os.environ.get('WEBAUTHN_ORIGIN')

    # Produktiv muss der Auth-Cookie ausschliesslich ueber HTTPS uebertragen werden.
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

# Konfiguration basierend auf Umgebungsvariable auswählen
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
