"""
File Handling Utilities für Ersatzteile-Modul
"""

import os
from flask import current_app


def allowed_file(filename):
    """Prüft ob Dateityp erlaubt ist"""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.doc', '.docx'})
    return '.' in filename and os.path.splitext(filename)[1].lower() in allowed_extensions

import os
from datetime import datetime
from flask import current_app


def get_datei_anzahl(ersatzteil_id, typ='bild'):
    """Ermittelt die Anzahl der Dateien für ein Ersatzteil"""
    ersatzteil_folder = os.path.join(current_app.config['ERSATZTEIL_UPLOAD_FOLDER'], str(ersatzteil_id), typ)
    if not os.path.exists(ersatzteil_folder):
        return 0
    try:
        files = os.listdir(ersatzteil_folder)
        return len([f for f in files if os.path.isfile(os.path.join(ersatzteil_folder, f))])
    except:
        return 0


def get_bestellung_dateien(bestellung_id):
    """Hilfsfunktion: Scannt Ordner nach PDF-Dateien für eine Bestellung"""
    bestellung_folder = os.path.join(current_app.config['ANGEBOTE_UPLOAD_FOLDER'], 'Bestellungen', str(bestellung_id))
    dateien = []
    
    if os.path.exists(bestellung_folder):
        try:
            for filename in os.listdir(bestellung_folder):
                if filename.lower().endswith('.pdf'):
                    filepath = os.path.join(bestellung_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellungen/{bestellung_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Bestellung-Ordners: {e}")
    
    return dateien


def get_angebotsanfrage_dateien(angebotsanfrage_id):
    """Hilfsfunktion: Scannt Ordner nach PDF-Dateien für eine Angebotsanfrage"""
    angebote_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Angebote', str(angebotsanfrage_id))
    dateien = []
    
    if os.path.exists(angebote_folder):
        try:
            for filename in os.listdir(angebote_folder):
                if filename.lower().endswith('.pdf'):
                    filepath = os.path.join(angebote_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellwesen/Angebote/{angebotsanfrage_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Angebotsanfrage-Ordners: {e}")
    
    return dateien


def get_auftragsbestätigung_dateien(bestellung_id):
    """Hilfsfunktion: Scannt Ordner nach Auftragsbestätigungs-Dateien (PDF, JPEG, JPG, PNG) für eine Bestellung"""
    auftragsbestätigung_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Auftragsbestätigungen', str(bestellung_id))
    dateien = []
    
    if os.path.exists(auftragsbestätigung_folder):
        try:
            for filename in os.listdir(auftragsbestätigung_folder):
                file_ext = filename.lower()
                if file_ext.endswith(('.pdf', '.jpeg', '.jpg', '.png')):
                    filepath = os.path.join(auftragsbestätigung_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellwesen/Auftragsbestätigungen/{bestellung_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Auftragsbestätigung-Ordners: {e}")
    
    return dateien


def get_lieferschein_dateien(bestellung_id):
    """Hilfsfunktion: Scannt Ordner nach Lieferschein-Dateien (PDF, JPEG, JPG, PNG) für eine Bestellung"""
    lieferschein_folder = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], 'Bestellwesen', 'Lieferscheine', str(bestellung_id))
    dateien = []
    
    if os.path.exists(lieferschein_folder):
        try:
            for filename in os.listdir(lieferschein_folder):
                file_ext = filename.lower()
                if file_ext.endswith(('.pdf', '.jpeg', '.jpg', '.png')):
                    filepath = os.path.join(lieferschein_folder, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        # Pfad immer mit Forward-Slash für URL-Kompatibilität
                        path_for_url = f'Bestellwesen/Lieferscheine/{bestellung_id}/{filename}'
                        dateien.append({
                            'name': filename,
                            'path': path_for_url,
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime)
                        })
            # Sortiere nach Änderungsdatum (neueste zuerst)
            dateien.sort(key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            print(f"Fehler beim Scannen des Lieferschein-Ordners: {e}")
    
    return dateien

