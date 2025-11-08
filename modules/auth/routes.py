"""
Auth Routes - Login, Logout
"""

from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from . import auth_bp
from utils import get_db_connection
from utils.decorators import is_safe_url, login_required


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite"""
    if request.method == 'POST':
        personalnummer = request.form['personalnummer']
        passwort = request.form['passwort']

        try:
            with get_db_connection() as conn:
                user = conn.execute(
                    'SELECT m.*, a.Bezeichnung as AbteilungName FROM Mitarbeiter m LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID WHERE m.Personalnummer = ? AND m.Aktiv = 1',
                    (personalnummer,)
                ).fetchone()

            if not user:
                flash('Kein Benutzer mit dieser Personalnummer gefunden oder Benutzer inaktiv.', 'danger')
                return render_template('login.html')

            if user and check_password_hash(user['Passwort'], passwort):
                session['user_id'] = user['ID']
                session['user_name'] = f"{user['Vorname']} {user['Nachname']}"
                session['user_abteilung'] = user['AbteilungName'] if user['AbteilungName'] else None
                
                # Alle Abteilungen des Mitarbeiters laden (primär + zusätzliche)
                with get_db_connection() as conn:
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
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            else:
                flash('Ungültige Personalnummer oder Passwort.', 'danger')
        except Exception as e:
            flash('Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.', 'danger')
            print(f"Login error: {e}")

    return render_template('login.html')


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
                return redirect(url_for('dashboard'))
                
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

