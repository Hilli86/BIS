"""
Folder Setup Utilities
Hilfsfunktionen für die Erstellung von Upload-Ordnern beim Start
"""

import os
from flask import current_app


def create_all_upload_folders(app):
    """
    Erstellt alle benötigten Upload-Ordner falls sie nicht existieren
    
    Args:
        app: Flask-App-Instanz
    """
    folders = [
        app.config.get('SCHICHTBUCH_UPLOAD_FOLDER'),
        app.config.get('ERSATZTEIL_UPLOAD_FOLDER'),
        app.config.get('ANGEBOTE_UPLOAD_FOLDER'),
        app.config.get('IMPORT_FOLDER'),
        app.config.get('UPLOAD_BASE_FOLDER'),
    ]
    
    for folder in folders:
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                print(f"Warnung: Konnte Upload-Ordner {folder} nicht erstellen: {e}")

