"""
BIS - Betriebsinformationssystem
Modulare Flask-Anwendung mit Blueprints

Hauptdatei - nur Initialisierung und Blueprint-Registrierung
"""

from flask import Flask, render_template, session, redirect, url_for, request, jsonify, current_app
import os
import shutil
from werkzeug.utils import secure_filename
from config import config

# Flask App initialisieren
app = Flask(__name__)

# Konfiguration laden
config_name = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[config_name])

# Datenbank-Prüfung beim Start
with app.app_context():
    from utils.database_check import initialize_database_on_startup
    initialize_database_on_startup(app)

# Upload-Ordner erstellen falls nicht vorhanden
os.makedirs(app.config['SCHICHTBUCH_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ERSATZTEIL_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ANGEBOTE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['IMPORT_FOLDER'], exist_ok=True)

# Blueprints registrieren
from modules import auth_bp, schichtbuch_bp, admin_bp, ersatzteile_bp

app.register_blueprint(auth_bp)
app.register_blueprint(schichtbuch_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(ersatzteile_bp)


# ========== Error Handler ==========

@app.errorhandler(404)
def not_found_error(error):
    """404 Fehlerseite"""
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 Fehlerseite"""
    return render_template('errors/500.html'), 500


# ========== Import-Funktionalität ==========

@app.route('/api/import/dateien', methods=['GET'])
def import_dateien_liste():
    """Liste alle Dateien im Import-Ordner auf"""
    from utils.decorators import login_required
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    
    import_folder = current_app.config['IMPORT_FOLDER']
    
    if not os.path.exists(import_folder):
        return jsonify({'success': True, 'dateien': []})
    
    dateien = []
    try:
        for filename in os.listdir(import_folder):
            filepath = os.path.join(import_folder, filename)
            if os.path.isfile(filepath):
                file_size = os.path.getsize(filepath)
                file_size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
                
                dateien.append({
                    'name': filename,
                    'size': file_size_str,
                    'size_bytes': file_size
                })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Lesen des Import-Ordners: {str(e)}'}), 500
    
    return jsonify({'success': True, 'dateien': dateien})


@app.route('/api/import/verschieben', methods=['POST'])
def import_datei_verschieben():
    """Verschiebe eine Datei aus dem Import-Ordner zu einem Zielordner"""
    from utils.decorators import login_required
    
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Nicht angemeldet'}), 401
    
    data = request.get_json()
    original_filename = data.get('filename')
    ziel_ordner = data.get('ziel_ordner')  # Relativer Pfad zum Zielordner
    
    if not original_filename or not ziel_ordner:
        return jsonify({'success': False, 'message': 'Fehlende Parameter'}), 400
    
    # Sicherheitsprüfung: Dateiname darf keine Pfad-Traversal enthalten
    # Prüfe auf gefährliche Zeichen, aber behalte den Originalnamen für die Suche
    if '..' in original_filename or '/' in original_filename or '\\' in original_filename:
        return jsonify({'success': False, 'message': 'Ungültiger Dateiname'}), 400
    
    import_folder = current_app.config['IMPORT_FOLDER']
    quelle = os.path.join(import_folder, original_filename)
    
    # Sicherheitsprüfung: Quelle muss im Import-Ordner sein (mit normalisiertem Pfad)
    quelle_abs = os.path.abspath(quelle)
    import_folder_abs = os.path.abspath(import_folder)
    if not quelle_abs.startswith(import_folder_abs):
        return jsonify({'success': False, 'message': 'Ungültiger Dateipfad'}), 403
    
    # Prüfen ob Datei existiert (mit Originalnamen)
    if not os.path.exists(quelle):
        return jsonify({'success': False, 'message': f'Datei nicht gefunden: {original_filename}'}), 404
    
    # Sicheren Dateinamen für Ziel erstellen (secure_filename entfernt Leerzeichen)
    safe_filename = secure_filename(original_filename)
    ziel = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], ziel_ordner, safe_filename)
    
    # Zielordner erstellen falls nicht vorhanden
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    
    # Prüfen ob Datei bereits existiert
    final_filename = safe_filename
    if os.path.exists(ziel):
        name, ext = os.path.splitext(safe_filename)
        counter = 1
        while os.path.exists(ziel):
            final_filename = f"{name}_{counter}{ext}"
            ziel = os.path.join(current_app.config['UPLOAD_BASE_FOLDER'], ziel_ordner, final_filename)
            counter += 1
    
    try:
        # Datei verschieben (nicht kopieren)
        shutil.move(quelle, ziel)
        return jsonify({
            'success': True,
            'message': f'Datei "{final_filename}" erfolgreich verschoben',
            'filename': final_filename
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Fehler beim Verschieben: {error_details}")
        return jsonify({'success': False, 'message': f'Fehler beim Verschieben: {str(e)}'}), 500


# ========== Main Routes ==========

@app.route('/')
def index():
    """Startseite - Redirect zu Dashboard oder Login"""
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    # URL-Parameter (z.B. personalnummer) an Login-Route weitergeben
    personalnummer = request.args.get('personalnummer')
    if personalnummer:
        return redirect(url_for('auth.login', personalnummer=personalnummer))
    return redirect(url_for('auth.login'))


@app.route('/dashboard')
def dashboard():
    """Dashboard - Übersicht (schnelles Rendern, Daten werden per AJAX nachgeladen)"""
    if 'user_id' not in session:
        # URL-Parameter (z.B. personalnummer) an Login-Route weitergeben
        personalnummer = request.args.get('personalnummer')
        if personalnummer:
            return redirect(url_for('auth.login', personalnummer=personalnummer, next=url_for('dashboard')))
        return redirect(url_for('auth.login'))
    
    # Schnelles Rendern ohne Datenbankabfragen
    return render_template('dashboard/dashboard.html')


@app.route('/api/dashboard')
def api_dashboard():
    """API-Endpunkt für Dashboard-Daten"""
    if 'user_id' not in session:
        return jsonify({'error': 'Nicht angemeldet'}), 401
    
    from utils import get_db_connection, get_sichtbare_abteilungen_fuer_mitarbeiter
    
    # Hilfsfunktion zur Konvertierung von Row zu Dict
    def row_to_dict(row):
        """Konvertiert eine SQLite Row zu einem Dictionary"""
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}
    
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Sichtbare Abteilungen für den Mitarbeiter ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            
            # Status-Statistiken (nur für sichtbare Themen)
            status_query = '''
                SELECT S.Bezeichnung AS Status, S.Farbe, COUNT(T.ID) AS Anzahl
                FROM SchichtbuchThema T
                JOIN Status S ON S.ID = T.StatusID
                WHERE T.Gelöscht = 0
            '''
            status_params = []
            
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                status_query += f''' AND EXISTS (
                    SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                    WHERE sv.ThemaID = T.ID 
                    AND sv.AbteilungID IN ({placeholders})
                )'''
                status_params.extend(sichtbare_abteilungen)
            
            status_query += ' GROUP BY S.Bezeichnung, S.Farbe ORDER BY S.Sortierung ASC'
            status_daten = conn.execute(status_query, status_params).fetchall()
            
            # Gesamtanzahl aller Themen
            gesamt_query = '''
                SELECT COUNT(DISTINCT T.ID) AS Gesamt
                FROM SchichtbuchThema T
                WHERE T.Gelöscht = 0
            '''
            gesamt_params = []
            
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                gesamt_query += f''' AND EXISTS (
                    SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                    WHERE sv.ThemaID = T.ID 
                    AND sv.AbteilungID IN ({placeholders})
                )'''
                gesamt_params.extend(sichtbare_abteilungen)
            
            gesamt_result = conn.execute(gesamt_query, gesamt_params).fetchone()
            gesamt = gesamt_result['Gesamt'] if gesamt_result else 0
            
            # Aktuelle Themen (letzte 10, nach letzter Bemerkung)
            aktuelle_query = '''
                SELECT 
                    T.ID,
                    B.Bezeichnung AS Bereich,
                    G.Bezeichnung AS Gewerk,
                    S.Bezeichnung AS Status,
                    S.Farbe AS StatusFarbe,
                    ABT.Bezeichnung AS Abteilung,
                    COALESCE(MAX(BM.Datum), T.ErstelltAm) AS LetzteAktivitaet,
                    COALESCE(MAX(M.Vorname || ' ' || M.Nachname), '') AS LetzterMitarbeiter
                FROM SchichtbuchThema T
                JOIN Gewerke G ON T.GewerkID = G.ID
                JOIN Bereich B ON G.BereichID = B.ID
                JOIN Status S ON T.StatusID = S.ID
                LEFT JOIN Abteilung ABT ON T.ErstellerAbteilungID = ABT.ID
                LEFT JOIN SchichtbuchBemerkungen BM ON BM.ThemaID = T.ID AND BM.Gelöscht = 0
                LEFT JOIN Mitarbeiter M ON BM.MitarbeiterID = M.ID
                WHERE T.Gelöscht = 0
            '''
            aktuelle_params = []
            
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                aktuelle_query += f''' AND EXISTS (
                    SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                    WHERE sv.ThemaID = T.ID 
                    AND sv.AbteilungID IN ({placeholders})
                )'''
                aktuelle_params.extend(sichtbare_abteilungen)
            
            aktuelle_query += ''' GROUP BY T.ID
                ORDER BY LetzteAktivitaet DESC
                LIMIT 10'''
            aktuelle_themen = conn.execute(aktuelle_query, aktuelle_params).fetchall()
            
            # Meine offenen Themen (Themen mit eigenen Bemerkungen, Status != Abgeschlossen)
            meine_query = '''
                SELECT DISTINCT
                    T.ID,
                    B.Bezeichnung AS Bereich,
                    G.Bezeichnung AS Gewerk,
                    S.Bezeichnung AS Status,
                    S.Farbe AS StatusFarbe,
                    ABT.Bezeichnung AS Abteilung,
                    MAX(BM.Datum) AS LetzteBemerkung
                FROM SchichtbuchThema T
                JOIN Gewerke G ON T.GewerkID = G.ID
                JOIN Bereich B ON G.BereichID = B.ID
                JOIN Status S ON T.StatusID = S.ID
                LEFT JOIN Abteilung ABT ON T.ErstellerAbteilungID = ABT.ID
                JOIN SchichtbuchBemerkungen BM ON BM.ThemaID = T.ID AND BM.Gelöscht = 0
                WHERE T.Gelöscht = 0 AND BM.MitarbeiterID = ?
            '''
            meine_params = [mitarbeiter_id]
            
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                meine_query += f''' AND EXISTS (
                    SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                    WHERE sv.ThemaID = T.ID 
                    AND sv.AbteilungID IN ({placeholders})
                )'''
                meine_params.extend(sichtbare_abteilungen)
            
            meine_query += ''' GROUP BY T.ID
                ORDER BY LetzteBemerkung DESC
                LIMIT 10'''
            meine_themen = conn.execute(meine_query, meine_params).fetchall()
            
            # Aktivitätsübersicht (letzte Bemerkungen)
            aktivitaet_query = '''
                SELECT 
                    BM.ID AS BemerkungID,
                    BM.Datum,
                    BM.Bemerkung,
                    M.Vorname || ' ' || M.Nachname AS Mitarbeiter,
                    T.ID AS ThemaID,
                    B.Bezeichnung AS Bereich,
                    G.Bezeichnung AS Gewerk,
                    TA.Bezeichnung AS Taetigkeit
                FROM SchichtbuchBemerkungen BM
                JOIN Mitarbeiter M ON BM.MitarbeiterID = M.ID
                JOIN SchichtbuchThema T ON BM.ThemaID = T.ID
                JOIN Gewerke G ON T.GewerkID = G.ID
                JOIN Bereich B ON G.BereichID = B.ID
                LEFT JOIN Taetigkeit TA ON BM.TaetigkeitID = TA.ID
                WHERE BM.Gelöscht = 0 AND T.Gelöscht = 0
            '''
            aktivitaet_params = []
            
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                aktivitaet_query += f''' AND EXISTS (
                    SELECT 1 FROM SchichtbuchThemaSichtbarkeit sv
                    WHERE sv.ThemaID = T.ID 
                    AND sv.AbteilungID IN ({placeholders})
                )'''
                aktivitaet_params.extend(sichtbare_abteilungen)
            
            aktivitaet_query += ''' ORDER BY BM.Datum DESC
                LIMIT 15'''
            aktivitaeten = conn.execute(aktivitaet_query, aktivitaet_params).fetchall()
            
            # Ersatzteile-Statistiken
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            ersatzteil_stats = {}
            ersatzteil_warnungen = []
            
            # Basis-WHERE-Klausel für Ersatzteile
            ersatzteil_where = 'WHERE e.Gelöscht = 0 AND e.Aktiv = 1'
            ersatzteil_params = []
            
            # Berechtigungsfilter für Ersatzteile
            if not is_admin and sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                ersatzteil_where += f'''
                    AND e.ID IN (
                        SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                        WHERE AbteilungID IN ({placeholders})
                    )
                '''
                ersatzteil_params.extend(sichtbare_abteilungen)
            elif not is_admin:
                # Keine Berechtigung für Ersatzteile
                ersatzteil_where += ' AND 1=0'
            
            # Gesamtanzahl Ersatzteile
            ersatzteil_gesamt_query = f'''
                SELECT COUNT(*) AS Gesamt
                FROM Ersatzteil e
                {ersatzteil_where}
            '''
            ersatzteil_gesamt_result = conn.execute(ersatzteil_gesamt_query, ersatzteil_params).fetchone()
            ersatzteil_gesamt = ersatzteil_gesamt_result['Gesamt'] if ersatzteil_gesamt_result else 0
            
            # Ersatzteile mit Bestandswarnung
            warnung_query = f'''
                SELECT 
                    e.ID,
                    e.Bestellnummer,
                    e.Bezeichnung,
                    e.AktuellerBestand,
                    e.Mindestbestand,
                    e.Einheit,
                    k.Bezeichnung AS Kategorie
                FROM Ersatzteil e
                LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
                {ersatzteil_where}
                AND e.AktuellerBestand < e.Mindestbestand 
                AND e.Mindestbestand > 0 
                AND e.EndOfLife = 0
                ORDER BY e.AktuellerBestand ASC, e.Bezeichnung ASC
                LIMIT 10
            '''
            ersatzteil_warnungen = conn.execute(warnung_query, ersatzteil_params).fetchall()
            
            # Kategorie-Statistiken
            kategorie_query = f'''
                SELECT 
                    k.Bezeichnung AS Kategorie,
                    COUNT(e.ID) AS Anzahl
                FROM Ersatzteil e
                LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
                {ersatzteil_where}
                GROUP BY k.Bezeichnung
                ORDER BY Anzahl DESC
                LIMIT 5
            '''
            kategorie_stats = conn.execute(kategorie_query, ersatzteil_params).fetchall()
            
            ersatzteil_stats = {
                'gesamt': ersatzteil_gesamt,
                'warnungen': len(ersatzteil_warnungen),
                'kategorien': [row_to_dict(row) for row in kategorie_stats]
            }
            
            # Daten als JSON zurückgeben
            return jsonify({
                'success': True,
                'status_daten': [row_to_dict(row) for row in status_daten],
                'gesamt': gesamt,
                'aktuelle_themen': [row_to_dict(row) for row in aktuelle_themen],
                'meine_themen': [row_to_dict(row) for row in meine_themen],
                'aktivitaeten': [row_to_dict(row) for row in aktivitaeten],
                'ersatzteil_stats': ersatzteil_stats,
                'ersatzteil_warnungen': [row_to_dict(row) for row in ersatzteil_warnungen]
            })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Dashboard API Fehler: {error_details}")
        return jsonify({'success': False, 'error': str(e), 'details': error_details}), 500


# ========== App starten ==========

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

