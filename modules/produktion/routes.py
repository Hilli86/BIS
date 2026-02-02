"""
Produktion Routes
Routes für Produktionsfunktionen
"""

import os
import re
from flask import render_template, send_from_directory, current_app, abort
from . import produktion_bp
from utils.decorators import login_required, guest_allowed


def get_artikeleinstellungen_struktur():
    """
    Scannt die Ordnerstruktur für Artikeleinstellungen und erstellt eine hierarchische Datenstruktur.
    
    Returns:
        dict: {linie: {artikel: [fotos]}} mit sortierten Einträgen
    """
    base_folder = current_app.config.get('UPLOAD_BASE_FOLDER')
    etikettierung_folder = os.path.join(base_folder, 'Produktion', 'Etikettierung', 'Artikeleinstellungen')
    
    struktur = {}
    
    # Prüfen ob Ordner existiert
    if not os.path.exists(etikettierung_folder):
        return struktur
    
    # Erlaubte Bildformate
    bild_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    
    # Durch Linien-Ordner iterieren
    try:
        linien_ordner = [d for d in os.listdir(etikettierung_folder) 
                        if os.path.isdir(os.path.join(etikettierung_folder, d))]
        linien_ordner.sort()  # Alphabetisch sortieren
        
        for linie in linien_ordner:
            linie_path = os.path.join(etikettierung_folder, linie)
            struktur[linie] = {}
            
            # Durch Artikel-Ordner iterieren
            artikel_ordner = [d for d in os.listdir(linie_path)
                             if os.path.isdir(os.path.join(linie_path, d))]
            
            # Artikel nach Sortiernummer sortieren (numerisch, nicht lexikalisch)
            def get_sortiernummer(artikel_name):
                """Extrahiert die Sortiernummer aus dem Artikelnamen (z.B. '01-Artikel' -> 1)"""
                match = re.match(r'^(\d+)-', artikel_name)
                if match:
                    return int(match.group(1))
                return 9999  # Artikel ohne Sortiernummer ans Ende
            
            artikel_ordner.sort(key=get_sortiernummer)
            
            for artikel in artikel_ordner:
                artikel_path = os.path.join(linie_path, artikel)
                fotos = []
                
                # Alle Dateien im Artikel-Ordner durchgehen
                try:
                    dateien = [f for f in os.listdir(artikel_path)
                              if os.path.isfile(os.path.join(artikel_path, f))]
                    
                    # Nur Bilddateien filtern
                    bild_dateien = [f for f in dateien 
                                   if os.path.splitext(f.lower())[1] in bild_extensions]
                    
                    # Fotos sortieren: bizerba.* zuerst, dann alphabetisch
                    def foto_sort_key(filename):
                        filename_lower = filename.lower()
                        if filename_lower.startswith('bizerba'):
                            return (0, filename_lower)  # bizerba zuerst
                        return (1, filename_lower)  # andere alphabetisch
                    
                    bild_dateien.sort(key=foto_sort_key)
                    struktur[linie][artikel] = bild_dateien
                    
                except (OSError, PermissionError) as e:
                    # Fehler beim Lesen eines Artikel-Ordners ignorieren
                    print(f"Warnung: Konnte Artikel-Ordner {artikel_path} nicht lesen: {e}")
                    struktur[linie][artikel] = []
                    
    except (OSError, PermissionError) as e:
        print(f"Warnung: Konnte Etikettierungs-Ordner nicht lesen: {e}")
        return {}
    
    return struktur


@produktion_bp.route('/etikettierung')
@guest_allowed  # Muss ZUERST stehen, damit Attribut gesetzt wird
@login_required  # Prüft dann das Attribut
def etikettierung():
    """Etikettierung-Seite mit Artikeleinstellungen"""
    struktur = get_artikeleinstellungen_struktur()
    return render_template('produktion/etikettierung.html', struktur=struktur)


@produktion_bp.route('/etikettierung/bild/<path:filepath>')
@guest_allowed
@login_required
def etikettierung_bild(filepath):
    """Serviert Bilder aus dem Artikeleinstellungen-Ordner"""
    # Normalisiere den Pfad: Backslashes zu Forward-Slashes
    filepath = filepath.replace('\\', '/')
    
    # Sicherheitsprüfung: Pfad muss mit Produktion/Etikettierung/Artikeleinstellungen/ beginnen
    if not filepath.startswith('Produktion/Etikettierung/Artikeleinstellungen/'):
        abort(403)
    
    try:
        base_folder = current_app.config.get('UPLOAD_BASE_FOLDER')
        full_path = os.path.join(base_folder, filepath)
        
        # Sicherheitsprüfung: Datei muss im erlaubten Ordner sein
        abs_base = os.path.abspath(base_folder)
        abs_file = os.path.abspath(full_path)
        if not abs_file.startswith(abs_base):
            abort(403)
        
        # Prüfen ob Datei existiert
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            abort(404)
        
        # Verzeichnis und Dateiname extrahieren
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        return send_from_directory(directory, filename)
        
    except Exception as e:
        print(f"Fehler beim Servieren des Bildes {filepath}: {e}")
        abort(500)
