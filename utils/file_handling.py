"""
File Handling Utilities
Hilfsfunktionen für Datei-Uploads, Validierung und Dateiverwaltung
"""

import os
from werkzeug.utils import secure_filename
from flask import current_app


def validate_file_extension(filename, allowed_extensions=None):
    """
    Validiert die Dateiendung
    
    Args:
        filename: Dateiname
        allowed_extensions: Set oder Liste erlaubter Endungen (ohne Punkt)
                          Falls None, werden die Standard-Erweiterungen aus der Config verwendet
        
    Returns:
        True wenn erlaubt, False sonst
    """
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', set())
    
    if not filename:
        return False
    
    # Normalisiere zu Set
    if isinstance(allowed_extensions, list):
        allowed_extensions = set(allowed_extensions)
    
    # Dateiendung extrahieren (ohne Punkt, lowercase)
    file_ext = os.path.splitext(filename)[1].lstrip('.').lower()
    
    return file_ext in allowed_extensions


def create_upload_folder(folder_path):
    """
    Erstellt einen Upload-Ordner falls er nicht existiert
    
    Args:
        folder_path: Pfad zum Ordner
        
    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    try:
        os.makedirs(folder_path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Fehler beim Erstellen des Ordners {folder_path}: {e}")
        return False


def get_file_list(folder_path, include_size=True):
    """
    Liest eine Liste von Dateien aus einem Ordner
    
    Args:
        folder_path: Pfad zum Ordner
        include_size: Ob Dateigröße mit aufgenommen werden soll
        
    Returns:
        Liste von Dictionaries mit Dateiinformationen
    """
    if not os.path.exists(folder_path):
        return []
    
    dateien = []
    try:
        for filename in os.listdir(folder_path):
            filepath = os.path.join(folder_path, filename)
            if os.path.isfile(filepath):
                file_info = {
                    'name': filename,
                }
                
                if include_size:
                    from utils.helpers import format_file_size
                    file_size = os.path.getsize(filepath)
                    file_info['size'] = format_file_size(file_size)
                    file_info['size_bytes'] = file_size
                
                dateien.append(file_info)
    except Exception as e:
        print(f"Fehler beim Lesen des Ordners {folder_path}: {e}")
        return []
    
    return dateien


def save_uploaded_file(file, target_folder, allowed_extensions=None, create_unique_name=True):
    """
    Speichert eine hochgeladene Datei
    
    Args:
        file: Werkzeug FileStorage-Objekt
        target_folder: Zielordner für die Datei
        allowed_extensions: Erlaubte Dateiendungen (optional)
        create_unique_name: Ob bei Existenz ein eindeutiger Name erstellt werden soll
        
    Returns:
        Tuple (success: bool, filename: str oder None, error_message: str oder None)
    """
    if not file or not file.filename:
        return False, None, "Keine Datei ausgewählt"
    
    # Validierung
    if allowed_extensions and not validate_file_extension(file.filename, allowed_extensions):
        return False, None, f"Dateityp nicht erlaubt. Erlaubt: {', '.join(allowed_extensions)}"
    
    # Ordner erstellen
    if not create_upload_folder(target_folder):
        return False, None, "Fehler beim Erstellen des Zielordners"
    
    # Sicheren Dateinamen erstellen
    safe_filename = secure_filename(file.filename)
    filepath = os.path.join(target_folder, safe_filename)
    
    # Eindeutigen Namen erstellen falls Datei bereits existiert
    if create_unique_name and os.path.exists(filepath):
        name, ext = os.path.splitext(safe_filename)
        counter = 1
        while os.path.exists(filepath):
            safe_filename = f"{name}_{counter}{ext}"
            filepath = os.path.join(target_folder, safe_filename)
            counter += 1
    
    try:
        file.save(filepath)
        return True, safe_filename, None
    except Exception as e:
        return False, None, f"Fehler beim Speichern: {str(e)}"


def move_file_safe(source_path, target_path, create_unique_name=True):
    """
    Verschiebt eine Datei sicher (mit Pfad-Validierung)
    
    Args:
        source_path: Quellpfad
        target_path: Zielpfad
        create_unique_name: Ob bei Existenz ein eindeutiger Name erstellt werden soll
        
    Returns:
        Tuple (success: bool, final_filename: str oder None, error_message: str oder None)
    """
    import shutil
    
    # Sicherheitsprüfung: Quelle muss existieren
    if not os.path.exists(source_path):
        return False, None, f"Quelldatei nicht gefunden: {source_path}"
    
    # Sicherheitsprüfung: Pfad-Traversal verhindern
    source_abs = os.path.abspath(source_path)
    target_abs = os.path.abspath(target_path)
    
    # Zielordner erstellen
    target_dir = os.path.dirname(target_path)
    if not create_upload_folder(target_dir):
        return False, None, "Fehler beim Erstellen des Zielordners"
    
    # Eindeutigen Namen erstellen falls Datei bereits existiert
    final_filename = os.path.basename(target_path)
    if create_unique_name and os.path.exists(target_path):
        name, ext = os.path.splitext(final_filename)
        counter = 1
        while os.path.exists(target_path):
            final_filename = f"{name}_{counter}{ext}"
            target_path = os.path.join(target_dir, final_filename)
            counter += 1
    
    try:
        shutil.move(source_path, target_path)
        return True, final_filename, None
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Fehler beim Verschieben: {error_details}")
        return False, None, f"Fehler beim Verschieben: {str(e)}"

