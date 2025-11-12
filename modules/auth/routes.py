"""
Auth Routes - Login, Logout
"""

from flask import render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from . import auth_bp
from utils import get_db_connection
from utils.decorators import is_safe_url, login_required


def _log_login_attempt(conn, personalnummer, mitarbeiter_id, erfolgreich, request, fehlermeldung):
    """Hilfsfunktion zum Loggen von Login-Versuchen"""
    try:
        ip_adresse = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', ''))
        if ip_adresse and ',' in ip_adresse:
            # Bei mehreren IPs (Proxy) die erste nehmen
            ip_adresse = ip_adresse.split(',')[0].strip()
        
        user_agent = request.headers.get('User-Agent', '')[:500]  # Begrenzen auf 500 Zeichen
        
        conn.execute('''
            INSERT INTO LoginLog (Personalnummer, MitarbeiterID, Erfolgreich, IPAdresse, UserAgent, Fehlermeldung)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (personalnummer, mitarbeiter_id, 1 if erfolgreich else 0, ip_adresse, user_agent, fehlermeldung))
        conn.commit()
    except Exception as e:
        # Logging-Fehler sollten den Login-Prozess nicht beeinträchtigen
        print(f"Fehler beim Loggen des Login-Versuchs: {e}")
        import traceback
        traceback.print_exc()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite"""
    # Personalnummer aus Cookie oder URL-Parameter oder Formular
    personalnummer_param = request.cookies.get('remembered_personalnummer', '')
    if not personalnummer_param:
        personalnummer_param = request.args.get('personalnummer', '')
    
    # Remember-me Status aus Cookie
    remember_me = request.cookies.get('remembered_personalnummer') is not None
    
    if request.method == 'POST':
        personalnummer = request.form['personalnummer']
        passwort = request.form['passwort']
        remember_me_checkbox = request.form.get('remember_me') == 'on'

        try:
            with get_db_connection() as conn:
                user = conn.execute(
                    'SELECT m.*, a.Bezeichnung as AbteilungName FROM Mitarbeiter m LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID WHERE m.Personalnummer = ? AND m.Aktiv = 1',
                    (personalnummer,)
                ).fetchone()

                if not user:
                    # Fehlgeschlagene Anmeldung loggen
                    _log_login_attempt(conn, personalnummer, None, False, request, 'Benutzer nicht gefunden oder inaktiv')
                    flash('Kein Benutzer mit dieser Personalnummer gefunden oder Benutzer inaktiv.', 'danger')
                    return render_template('login.html', personalnummer=personalnummer, remember_me=remember_me_checkbox)

                if user and check_password_hash(user['Passwort'], passwort):
                    # Erfolgreiche Anmeldung loggen
                    _log_login_attempt(conn, personalnummer, user['ID'], True, request, None)
                    
                    session['user_id'] = user['ID']
                    session['user_name'] = f"{user['Vorname']} {user['Nachname']}"
                    session['user_abteilung'] = user['AbteilungName'] if user['AbteilungName'] else None
                    
                    # Alle Abteilungen des Mitarbeiters laden (primär + zusätzliche)
                    alle_abteilungen = []
                    
                    # Primärabteilung hinzufügen
                    if user['AbteilungName']:
                        alle_abteilungen.append(user['AbteilungName'])
                    
                    # Zusätzliche Abteilungen hinzufügen
                    zusaetzliche = conn.execute('''
                        SELECT a.Bezeichnung
                        FROM MitarbeiterAbteilung ma
                        JOIN Abteilung a ON ma.AbteilungID = a.ID
                        WHERE ma.MitarbeiterID = ? AND a.Aktiv = 1
                    ''', (user['ID'],)).fetchall()
                    
                    for abt in zusaetzliche:
                        if abt['Bezeichnung'] not in alle_abteilungen:
                            alle_abteilungen.append(abt['Bezeichnung'])
                    
                    session['user_abteilungen'] = alle_abteilungen
                    
                    flash('Erfolgreich angemeldet.', 'success')
                    
                    # Weiterleitung zur ursprünglichen URL (next-Parameter) oder zum Dashboard
                    next_page = request.args.get('next')
                    if next_page and is_safe_url(next_page):
                        response = make_response(redirect(next_page))
                    else:
                        response = make_response(redirect(url_for('dashboard')))
                    
                    # Cookie für "Zugangsdaten merken" setzen oder löschen
                    if remember_me_checkbox:
                        # Cookie für 30 Tage setzen
                        expires = datetime.now() + timedelta(days=30)
                        response.set_cookie('remembered_personalnummer', personalnummer, 
                                          expires=expires, httponly=True, samesite='Lax')
                    else:
                        # Cookie löschen falls vorhanden
                        response.set_cookie('remembered_personalnummer', '', expires=0)
                    
                    return response
                else:
                    # Fehlgeschlagene Anmeldung loggen
                    _log_login_attempt(conn, personalnummer, user['ID'] if user else None, False, request, 'Ungültiges Passwort')
                    flash('Ungültige Personalnummer oder Passwort.', 'danger')
        except Exception as e:
            flash('Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.', 'danger')
            print(f"Login error: {e}")

    return render_template('login.html', personalnummer=personalnummer_param, remember_me=remember_me)


@auth_bp.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('Abgemeldet.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/passwort-aendern', methods=['GET', 'POST'])
@login_required
def passwort_aendern():
    """Passwort ändern"""
    if request.method == 'POST':
        altes_passwort = request.form.get('altes_passwort', '')
        neues_passwort = request.form.get('neues_passwort', '')
        neues_passwort_wdh = request.form.get('neues_passwort_wdh', '')
        
        # Validierung
        if not altes_passwort or not neues_passwort or not neues_passwort_wdh:
            flash('Bitte füllen Sie alle Felder aus.', 'danger')
            return render_template('passwort_aendern.html')
        
        if neues_passwort != neues_passwort_wdh:
            flash('Die neuen Passwörter stimmen nicht überein.', 'danger')
            return render_template('passwort_aendern.html')
        
        if len(neues_passwort) < 6:
            flash('Das neue Passwort muss mindestens 6 Zeichen lang sein.', 'danger')
            return render_template('passwort_aendern.html')
        
        try:
            with get_db_connection() as conn:
                # Aktuellen Benutzer und Passwort abrufen
                user = conn.execute(
                    'SELECT Passwort FROM Mitarbeiter WHERE ID = ?',
                    (session['user_id'],)
                ).fetchone()
                
                if not user:
                    flash('Benutzer nicht gefunden.', 'danger')
                    return redirect(url_for('auth.logout'))
                
                # Altes Passwort prüfen
                if not check_password_hash(user['Passwort'], altes_passwort):
                    flash('Das alte Passwort ist nicht korrekt.', 'danger')
                    return render_template('passwort_aendern.html')
                
                # Neues Passwort hashen und speichern
                neues_passwort_hash = generate_password_hash(neues_passwort)
                conn.execute(
                    'UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?',
                    (neues_passwort_hash, session['user_id'])
                )
                conn.commit()
                
                flash('Passwort erfolgreich geändert.', 'success')
                return redirect(url_for('auth.profil'))
                
        except Exception as e:
            flash('Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.', 'danger')
            print(f"Passwort ändern Fehler: {e}")
    
    return render_template('passwort_aendern.html')


@auth_bp.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    """Benutzerprofil anzeigen und bearbeiten"""
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        vorname = request.form.get('vorname', '').strip()
        nachname = request.form.get('nachname', '').strip()
        
        # Validierung
        if not nachname:
            flash('Nachname ist erforderlich.', 'danger')
            return redirect(url_for('auth.profil'))
        
        try:
            with get_db_connection() as conn:
                # Profil aktualisieren
                conn.execute(
                    'UPDATE Mitarbeiter SET Vorname = ?, Nachname = ? WHERE ID = ?',
                    (vorname, nachname, user_id)
                )
                conn.commit()
                
                # Session aktualisieren
                session['user_name'] = f"{vorname} {nachname}"
                
                flash('Profil erfolgreich aktualisiert.', 'success')
                return redirect(url_for('auth.profil'))
                
        except Exception as e:
            flash('Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.', 'danger')
            print(f"Profil aktualisieren Fehler: {e}")
    
    # Profil-Daten laden
    with get_db_connection() as conn:
        user = conn.execute('''
            SELECT 
                m.ID,
                m.Personalnummer,
                m.Vorname,
                m.Nachname,
                m.Aktiv,
                a.Bezeichnung AS PrimaerAbteilung
            FROM Mitarbeiter m
            LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID
            WHERE m.ID = ?
        ''', (user_id,)).fetchone()
        
        # Alle Abteilungen des Benutzers laden
        alle_abteilungen = conn.execute('''
            SELECT a.Bezeichnung, a.ParentAbteilungID
            FROM MitarbeiterAbteilung ma
            JOIN Abteilung a ON ma.AbteilungID = a.ID
            WHERE ma.MitarbeiterID = ? AND a.Aktiv = 1
            ORDER BY a.Sortierung, a.Bezeichnung
        ''', (user_id,)).fetchall()
        
        # Statistiken für den Benutzer
        thema_anzahl = conn.execute('''
            SELECT COUNT(DISTINCT b.ThemaID) as count
            FROM SchichtbuchBemerkungen b
            WHERE b.MitarbeiterID = ? AND b.Gelöscht = 0
        ''', (user_id,)).fetchone()['count']
        
        bemerkung_anzahl = conn.execute('''
            SELECT COUNT(*) as count
            FROM SchichtbuchBemerkungen
            WHERE MitarbeiterID = ? AND Gelöscht = 0
        ''', (user_id,)).fetchone()['count']
    
    return render_template(
        'profil.html',
        user=user,
        alle_abteilungen=alle_abteilungen,
        thema_anzahl=thema_anzahl,
        bemerkung_anzahl=bemerkung_anzahl
    )

