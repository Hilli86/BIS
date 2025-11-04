"""
Auth Routes - Login, Logout
"""

from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from . import auth_bp
from utils import get_db_connection


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

