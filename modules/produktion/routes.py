"""
Produktion Routes
Routes für Produktionsfunktionen
"""

import os
import re
from datetime import datetime, timedelta

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from . import produktion_bp
from utils.database import get_db_connection
from utils.decorators import guest_allowed, login_required, permission_required
from utils.etikett_druck import (
    FUNKTION_PRODUKTION_ETIKETT,
    build_print_resolution,
    zpl_produktion_etikett,
)
from utils.file_handling import (
    create_upload_folder,
    loesche_import_kopie_nach_upload,
    originale_loeschen_aus_formular,
    save_uploaded_file,
)
from utils.zebra_client import send_zpl_to_printer


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


@produktion_bp.route('/etiketten-drucken')
@login_required
def etiketten_drucken():
    """Freitext-Produktion-Etikett (optional Artikelnummer, Produkt, Datum, zu verwenden am, Stück)."""
    heute = datetime.now().date()
    morgen = heute + timedelta(days=1)
    datum_tag_iso = heute.strftime('%Y-%m-%d')
    zu_verwenden_tag_iso = morgen.strftime('%Y-%m-%d')
    return render_template(
        'etiketten_drucken.html',
        datum_tag_iso=datum_tag_iso,
        zu_verwenden_tag_iso=zu_verwenden_tag_iso,
    )


@produktion_bp.route('/etiketten-drucken/druck', methods=['POST'])
@login_required
def etiketten_drucken_druck():
    """Druckt Produktion-Etikett gemäß Admin-Konfiguration ``produktion_etikett``."""
    mitarbeiter_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    produkt = (data.get('produkt') or '').strip()
    artikelnummer = (data.get('artikelnummer') or '').strip()
    datum_text = (data.get('datum') or '').strip()
    if not datum_text:
        datum_text = datetime.now().strftime('%d.%m.%Y')
    zu_verwenden_text = (data.get('zu_verwenden_am') or '').strip()
    if not zu_verwenden_text:
        zu_verwenden_text = (datetime.now().date() + timedelta(days=1)).strftime('%d.%m.%Y')

    raw_stueck = data.get('stueck')
    try:
        anzahl = int(raw_stueck)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Stück muss eine ganze Zahl sein.'}), 400
    if anzahl < 1 or anzahl > 9999:
        return jsonify({'success': False, 'message': 'Stück muss zwischen 1 und 9999 liegen.'}), 400

    if not produkt:
        return jsonify({'success': False, 'message': 'Produkt ist erforderlich.'}), 400

    raw_pid = data.get('printer_id')
    printer_id = None
    if raw_pid is not None:
        try:
            printer_id = int(raw_pid)
        except (TypeError, ValueError):
            printer_id = None

    stueck_text = str(anzahl)

    try:
        with get_db_connection() as conn:
            res = build_print_resolution(
                conn, FUNKTION_PRODUKTION_ETIKETT, mitarbeiter_id, printer_id
            )
            if not res['ok']:
                return jsonify({'success': False, 'message': res['error_message']}), 400
            if res['needs_printer_choice']:
                return jsonify({
                    'success': True,
                    'needs_printer_choice': True,
                    'printers': res['printers'],
                    'message': 'Drucker wählen.',
                })

            etikett = res['etikett']
            zpl = zpl_produktion_etikett(
                etikett,
                produkt,
                datum_text,
                stueck_text,
                anzahl,
                artikelnummer=artikelnummer,
                zu_verwenden_am_text=zu_verwenden_text,
            )
            try:
                send_zpl_to_printer(res['printer_ip'], zpl)
            except Exception as e:
                return jsonify({'success': False, 'message': f'Fehler beim Senden an Drucker: {e}'}), 500

        return jsonify({
            'success': True,
            'message': f'{anzahl} Produktion-Etikett(en) gedruckt.',
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Drucken: {e}'}), 500


@produktion_bp.route('/etikettierung')
@guest_allowed  # Muss ZUERST stehen, damit Attribut gesetzt wird
@login_required  # Prüft dann das Attribut
def etikettierung():
    """Etikettierung-Seite mit Artikeleinstellungen"""
    struktur = get_artikeleinstellungen_struktur()
    user_berechtigungen = session.get('user_berechtigungen', [])
    kann_foto_aendern = 'foto_artikeleinstellungen_aendern' in user_berechtigungen or 'admin' in user_berechtigungen
    return render_template('etikettierung.html', struktur=struktur, kann_foto_aendern=kann_foto_aendern)


@produktion_bp.route('/etikettierung/foto/upload', methods=['POST'])
@login_required
@permission_required('foto_artikeleinstellungen_aendern')
def etikettierung_foto_upload():
    """bizerba.jpg für einen Artikel in den Artikeleinstellungen ersetzen"""
    linie = (request.form.get('linie') or '').strip()
    artikel = (request.form.get('artikel') or '').strip()

    # Pfadvalidierung: Kein Path-Traversal
    if not linie or not artikel:
        flash('Linie und Artikel sind erforderlich.', 'danger')
        return redirect(url_for('produktion.etikettierung'))
    if '..' in linie or '..' in artikel or '/' in linie or '/' in artikel or '\\' in linie or '\\' in artikel:
        flash('Ungültige Zeichen in Linie oder Artikel.', 'danger')
        return redirect(url_for('produktion.etikettierung'))

    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('produktion.etikettierung'))

    file = request.files['file']
    if not file or file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('produktion.etikettierung'))

    original_filename = file.filename
    allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file_ext = os.path.splitext(file.filename)[1].lower().lstrip('.')
    if file_ext not in allowed_image_extensions:
        flash(f'Dateityp nicht erlaubt. Erlaubt sind: {", ".join(allowed_image_extensions)}', 'danger')
        return redirect(url_for('produktion.etikettierung'))

    base_folder = current_app.config.get('UPLOAD_BASE_FOLDER')
    target_folder = os.path.join(base_folder, 'Produktion', 'Etikettierung', 'Artikeleinstellungen', linie, artikel)

    # Sicherheitsprüfung: Ziel muss im erlaubten Ordner liegen
    abs_base = os.path.abspath(base_folder)
    abs_target = os.path.abspath(target_folder)
    if not abs_target.startswith(abs_base):
        flash('Ungültiger Zielpfad.', 'danger')
        return redirect(url_for('produktion.etikettierung'))

    if not create_upload_folder(target_folder):
        flash('Fehler beim Erstellen des Zielordners.', 'danger')
        return redirect(url_for('produktion.etikettierung'))

    # Immer als bizerba.jpg speichern (Überschreiben erlauben)
    file.filename = 'bizerba.jpg'
    success, saved_filename, error_message = save_uploaded_file(
        file,
        target_folder,
        allowed_extensions=allowed_image_extensions,
        create_unique_name=False
    )

    if not success or error_message:
        flash(f'Fehler beim Hochladen: {error_message}', 'danger')
    else:
        loesche_import_kopie_nach_upload(
            original_filename,
            current_app.config['IMPORT_FOLDER'],
            originale_loeschen_aus_formular(),
        )
        flash('bizerba.jpg erfolgreich aktualisiert.', 'success')

    return redirect(url_for('produktion.etikettierung'))


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
