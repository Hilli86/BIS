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


_SAFE_CONTENT_TYPES = {
    'pdf': {'application/pdf'},
    'png': {'image/png'},
    'jpg': {'image/jpeg'},
    'jpeg': {'image/jpeg'},
    'gif': {'image/gif'},
    'webp': {'image/webp'},
    'txt': {'text/plain', 'application/octet-stream'},
    'doc': {'application/msword', 'application/octet-stream'},
    'docx': {
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/octet-stream',
    },
    'xls': {'application/vnd.ms-excel', 'application/octet-stream'},
    'xlsx': {
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/octet-stream',
    },
}


def _content_type_erlaubt(filename, content_type):
    if not content_type:
        return True
    ext = os.path.splitext(filename)[1].lstrip('.').lower()
    erlaubte = _SAFE_CONTENT_TYPES.get(ext)
    if not erlaubte:
        return True
    return str(content_type).lower().split(';', 1)[0].strip() in erlaubte


def save_uploaded_file(file, target_folder, allowed_extensions=None, create_unique_name=True, override_filename=None):
    """
    Speichert eine hochgeladene Datei.

    Args:
        file: Werkzeug FileStorage-Objekt.
        target_folder: Zielordner fuer die Datei.
        allowed_extensions: Erlaubte Dateiendungen. MUSS angegeben werden;
            `None` faellt auf `ALLOWED_EXTENSIONS` aus der Config zurueck.
        create_unique_name: Bei Existenz einen eindeutigen Namen erzeugen.
        override_filename: Optionaler Dateiname (z. B. aus Formularfeld),
            sonst `file.filename`.

    Returns:
        Tuple (success, filename_or_None, error_message_or_None)
    """
    if not file:
        return False, None, "Keine Datei ausgewählt"

    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', set())
    if not allowed_extensions:
        return False, None, "Keine erlaubten Dateitypen konfiguriert"

    name_for_validation = None
    if override_filename is not None and str(override_filename).strip():
        name_for_validation = str(override_filename).strip()
    elif file.filename:
        name_for_validation = file.filename

    if not name_for_validation:
        return False, None, "Keine Datei ausgewählt"

    if not validate_file_extension(name_for_validation, allowed_extensions):
        return False, None, (
            'Dateityp nicht erlaubt. Erlaubt: ' + ', '.join(sorted(allowed_extensions))
        )

    content_type = getattr(file, 'mimetype', None) or getattr(file, 'content_type', None)
    if not _content_type_erlaubt(name_for_validation, content_type):
        return False, None, (
            f'Dateiinhalt ({content_type}) passt nicht zur Dateiendung.'
        )
    
    # Ordner erstellen
    if not create_upload_folder(target_folder):
        return False, None, "Fehler beim Erstellen des Zielordners"
    
    # Sicheren Dateinamen erstellen
    safe_filename = secure_filename(name_for_validation)
    if not safe_filename or safe_filename in ('.', '..'):
        safe_filename = secure_filename(file.filename) if file.filename else 'upload.jpg'
    if not safe_filename:
        safe_filename = 'upload.jpg'
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


def speichere_in_import_ordner(file_storage, allowed_extensions=None, create_unique_name=True, dateiname_vorgabe=None):
    """
    Speichert eine hochgeladene Datei im konfigurierten Import-Ordner (IMPORT_FOLDER).
    Wiederverwendbar für Scan-Upload und andere Upload-Blöcke.

    dateiname_vorgabe: optionaler Dateiname (z. B. multipart-Feld „filename“), zuverlässiger als nur Blob-Name.
    """
    import_folder = current_app.config.get('IMPORT_FOLDER')
    if not import_folder:
        return False, None, "Import-Ordner nicht konfiguriert"
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', set())
    override = None
    if dateiname_vorgabe is not None and str(dateiname_vorgabe).strip():
        override = str(dateiname_vorgabe).strip()
    return save_uploaded_file(
        file_storage,
        import_folder,
        allowed_extensions=allowed_extensions,
        create_unique_name=create_unique_name,
        override_filename=override,
    )


def move_file_safe(source_path, target_path, create_unique_name=True, allowed_base=None):
    """
    Verschiebt eine Datei sicher (mit Pfad-Validierung)

    Args:
        source_path: Quellpfad
        target_path: Zielpfad
        create_unique_name: Ob bei Existenz ein eindeutiger Name erstellt werden soll
        allowed_base: Optionaler Basispfad. Wenn gesetzt, muss sowohl die
            Quell- als auch die Zielpfade innerhalb liegen (Path-Traversal-
            Schutz).

    Returns:
        Tuple (success: bool, final_filename: str oder None, error_message: str oder None)
    """
    import shutil

    if not os.path.exists(source_path):
        return False, None, f"Quelldatei nicht gefunden: {source_path}"

    if allowed_base:
        base_real = os.path.realpath(allowed_base)
        src_real = os.path.realpath(source_path)
        tgt_real = os.path.realpath(target_path)
        try:
            if os.path.normcase(os.path.commonpath([base_real, src_real])) != os.path.normcase(base_real):
                return False, None, 'Quelle außerhalb des erlaubten Basisordners.'
            if os.path.normcase(os.path.commonpath([base_real, tgt_real])) != os.path.normcase(base_real):
                return False, None, 'Ziel außerhalb des erlaubten Basisordners.'
        except ValueError:
            return False, None, 'Pfadvergleich nicht möglich.'

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


def originale_loeschen_aus_formular():
    """
    Früher: Checkbox „Originale löschen“ im Formular (entfernt, funktionierte nicht zuverlässig).
    Import-Kopien werden nach Upload nicht mehr automatisch gelöscht.
    """
    return False


def loesche_import_kopie_nach_upload(original_filename, import_folder, aktiviert=True):
    """
    Entfernt nach erfolgreichem Upload eine gleichnamige Datei im Import-Ordner (falls vorhanden).
    """
    if not aktiviert or not original_filename or not import_folder:
        return
    base = os.path.basename(original_filename)
    if not base or base in ('.', '..'):
        return
    full = os.path.join(import_folder, base)
    import_abs = os.path.abspath(import_folder)
    full_abs = os.path.abspath(full)
    if not full_abs.startswith(import_abs + os.sep):
        return
    if os.path.isfile(full_abs):
        try:
            os.remove(full_abs)
        except OSError:
            pass

