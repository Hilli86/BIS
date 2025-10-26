import os
from datetime import timedelta

class Config:
    """Basis-Konfiguration für die Flask-Anwendung"""
    
    # Sicherheit
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production-12345'
    
    # Datenbank
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'database_main.db'
    
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
