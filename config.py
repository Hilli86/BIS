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
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    
    # Session-Konfiguration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Debug-Modus (nur für Entwicklung)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # SQL-Tracing (nur für Entwicklung)
    SQL_TRACING = os.environ.get('SQL_TRACING', 'False').lower() == 'true'

class DevelopmentConfig(Config):
    """Entwicklungskonfiguration"""
    DEBUG = True
    SQL_TRACING = True

class ProductionConfig(Config):
    """Produktionskonfiguration"""
    DEBUG = False
    SQL_TRACING = False

# Konfiguration basierend auf Umgebungsvariable auswählen
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
