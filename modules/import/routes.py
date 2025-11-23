"""
Import Routes
Routes für Datei-Import-Funktionalität
"""

from flask import request, session, jsonify, current_app
import os
import shutil
from werkzeug.utils import secure_filename
from . import import_bp
from utils.file_handling import get_file_list, move_file_safe


@import_bp.route('/dateien', methods=['GET'])
def import_dateien_liste():
    """Liste alle Dateien im Import-Ordner auf"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    
    import_folder = current_app.config['IMPORT_FOLDER']
    
    if not os.path.exists(import_folder):
        return jsonify({'success': True, 'dateien': []})
    
    try:
        dateien = get_file_list(import_folder, include_size=True)
        return jsonify({'success': True, 'dateien': dateien})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Lesen des Import-Ordners: {str(e)}'}), 500


@import_bp.route('/verschieben', methods=['POST'])
def import_datei_verschieben():
    """Verschiebe eine Datei aus dem Import-Ordner zu einem Zielordner"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    
    data = request.get_json()
    original_filename = data.get('filename')
    ziel_ordner = data.get('ziel_ordner')  # Relativer Pfad zum Zielordner
    
    if not original_filename or not ziel_ordner:
        return jsonify({'success': False, 'message': 'Fehlende Parameter'}), 400
    
    # Sicherheitsprüfung: Dateiname darf keine Pfad-Traversal enthalten
    if '..' in original_filename or '/' in original_filename or '\\' in original_filename:
        return jsonify({'success': False, 'message': 'Ungültiger Dateiname'}), 400
    
    import_folder = current_app.config['IMPORT_FOLDER']
    quelle = os.path.join(import_folder, original_filename)
    
    # Sicherheitsprüfung: Quelle muss im Import-Ordner sein (mit normalisiertem Pfad)
    quelle_abs = os.path.abspath(quelle)
    import_folder_abs = os.path.abspath(import_folder)
    if not quelle_abs.startswith(import_folder_abs):
        return jsonify({'success': False, 'message': 'Ungültiger Dateipfad'}), 403
    
    # Prüfen ob Datei existiert
    if not os.path.exists(quelle):
        return jsonify({'success': False, 'message': f'Datei nicht gefunden: {original_filename}'}), 404
    
    # Sicheren Dateinamen für Ziel erstellen
    safe_filename = secure_filename(original_filename)
    ziel = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], ziel_ordner, safe_filename)
    
    # Datei verschieben
    success, final_filename, error_message = move_file_safe(quelle, ziel, create_unique_name=True)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'Datei "{final_filename}" erfolgreich verschoben',
            'filename': final_filename
        })
    else:
        return jsonify({'success': False, 'message': error_message}), 500

