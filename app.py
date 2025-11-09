"""
BIS - Betriebsinformationssystem
Modulare Flask-Anwendung mit Blueprints

Hauptdatei - nur Initialisierung und Blueprint-Registrierung
"""

from flask import Flask, render_template, session, redirect, url_for, request
import os
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
    """Dashboard - Übersicht"""
    if 'user_id' not in session:
        # URL-Parameter (z.B. personalnummer) an Login-Route weitergeben
        personalnummer = request.args.get('personalnummer')
        if personalnummer:
            return redirect(url_for('auth.login', personalnummer=personalnummer, next=url_for('dashboard')))
        return redirect(url_for('auth.login'))
    
    from utils import get_db_connection, get_sichtbare_abteilungen_fuer_mitarbeiter
    
    mitarbeiter_id = session.get('user_id')
    
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
        
        gesamt = conn.execute(gesamt_query, gesamt_params).fetchone()['Gesamt']
        
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
        is_admin = 'BIS-Admin' in (session.get('user_abteilungen') or [])
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
        ersatzteil_gesamt = conn.execute(ersatzteil_gesamt_query, ersatzteil_params).fetchone()['Gesamt']
        
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
            AND e.AktuellerBestand <= e.Mindestbestand 
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
            'kategorien': kategorie_stats
        }

    return render_template('dashboard/dashboard.html', 
                         status_daten=status_daten,
                         gesamt=gesamt,
                         aktuelle_themen=aktuelle_themen,
                         meine_themen=meine_themen,
                         aktivitaeten=aktivitaeten,
                         ersatzteil_stats=ersatzteil_stats,
                         ersatzteil_warnungen=ersatzteil_warnungen)


# ========== App starten ==========

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

