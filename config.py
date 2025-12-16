import os
from datetime import timedelta

class Config:
    """Basis-Konfiguration für die Flask-Anwendung"""
    
    # Sicherheit
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production-12345'
    
    # Datenbank
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'database_main.db'
    
    # Upload-Konfiguration
    UPLOAD_BASE_FOLDER = os.environ.get('UPLOAD_BASE_FOLDER') or os.path.join(os.getcwd(), 'Daten')
    SCHICHTBUCH_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Schichtbuch', 'Themen')
    ERSATZTEIL_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Ersatzteile')
    ANGEBOTE_UPLOAD_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Angebote')
    IMPORT_FOLDER = os.path.join(UPLOAD_BASE_FOLDER, 'Import')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    
    # Session-Konfiguration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Debug-Modus (nur für Entwicklung)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # SQL-Tracing (nur für Entwicklung)
    SQL_TRACING = os.environ.get('SQL_TRACING', 'False').lower() == 'true'
    
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
    
    # Push-Benachrichtigungen (VAPID)
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', None)
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', None)
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

class DevelopmentConfig(Config):
    """Entwicklungskonfiguration"""
    DEBUG = True
    SQL_TRACING = True

class ProductionConfig(Config):
    """Produktionskonfiguration"""
    DEBUG = False
    SQL_TRACING = False

    # Für das Intranet-System unter https://10.40.140.243
    WEBAUTHN_RP_ID = '10.40.140.243'
    WEBAUTHN_RP_NAME = 'BIS – Betriebsinformationssystem'
    WEBAUTHN_ORIGIN = 'https://10.40.140.243'

# Konfiguration basierend auf Umgebungsvariable auswählen
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
