"""
Auth Routes - Login, Logout
"""

import base64
import traceback
from flask import render_template, request, redirect, url_for, session, flash, make_response, jsonify, current_app, g
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from . import auth_bp
from utils import get_db_connection
from utils.helpers import get_client_ip
from utils.decorators import login_required
from utils.rate_limit import limiter, login_ratelimit_key
from utils.security import validate_passwort_policy
from utils.auth_redirect import resolve_post_login_redirect_url
from utils.db_sql import upsert_ignore, upsert_replace
from utils.webauthn import (
    get_fido2_server,
    store_state,
    pop_state,
    build_user_entity,
    build_existing_credentials,
    build_attested_credentials,
    serialize_registration_options,
    serialize_authentication_options,
    extract_attested_credential,
    decode_user_handle_to_id,
)


@auth_bp.teardown_request
def _restore_session_lifetime_after_login(exc=None):
    """Stellt PERMANENT_SESSION_LIFETIME nach Login mit 'Zugangsdaten merken' wieder her."""
    if hasattr(g, 'login_session_lifetime_to_restore'):
        current_app.config['PERMANENT_SESSION_LIFETIME'] = g.login_session_lifetime_to_restore


def _log_login_attempt(conn, personalnummer, mitarbeiter_id, erfolgreich, request, fehlermeldung):
    """Hilfsfunktion zum Loggen von Login-Versuchen"""
    try:
        ip_adresse = get_client_ip(request)
        
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
@limiter.limit('10/minute;50/hour', methods=['POST'], key_func=login_ratelimit_key)
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
                    # Einheitliche Fehlermeldung (keine User-Enumeration)
                    flash('Ungültige Personalnummer oder Passwort.', 'danger')
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
                    
                    # Berechtigungen des Mitarbeiters laden
                    berechtigungen = conn.execute('''
                        SELECT b.Schluessel
                        FROM MitarbeiterBerechtigung mb
                        JOIN Berechtigung b ON mb.BerechtigungID = b.ID
                        WHERE mb.MitarbeiterID = ? AND b.Aktiv = 1
                    ''', (user['ID'],)).fetchall()
                    
                    session['user_berechtigungen'] = [b['Schluessel'] for b in berechtigungen]
                    
                    # Menü-Sichtbarkeit pro Mitarbeiter laden
                    from utils.menue_definitions import get_menue_sichtbarkeit_fuer_mitarbeiter
                    session['user_menue_sichtbarkeit'] = get_menue_sichtbarkeit_fuer_mitarbeiter(user['ID'], conn)
                    
                    # Session dauerhaft speichern (über Browser-Neustart hinweg)
                    session.permanent = True
                    if remember_me_checkbox:
                        # Bei "Zugangsdaten merken": 30 Tage (Restore in teardown nach Session-Speicherung)
                        g.login_session_lifetime_to_restore = current_app.config['PERMANENT_SESSION_LIFETIME']
                        current_app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
                    
                    # Wenn Passwortwechsel erzwungen ist (z.B. Initial-Admin),
                    # direkt zur Passwort-Ändern-Seite leiten.
                    passwort_wechsel_noetig = False
                    try:
                        if 'PasswortWechselErforderlich' in user.keys():
                            passwort_wechsel_noetig = bool(user['PasswortWechselErforderlich'])
                    except Exception:
                        passwort_wechsel_noetig = False
                    session['passwort_wechsel_erforderlich'] = passwort_wechsel_noetig

                    if passwort_wechsel_noetig:
                        flash('Bitte setzen Sie ein neues Passwort, bevor Sie fortfahren.', 'warning')
                        response = make_response(redirect(url_for('auth.passwort_aendern')))
                    else:
                        start_ep = None
                        if 'StartseiteNachLoginEndpunkt' in user.keys():
                            start_ep = user['StartseiteNachLoginEndpunkt']
                        ziel = resolve_post_login_redirect_url(start_ep, request.args.get('next'))
                        response = make_response(redirect(ziel))
                    
                    # Cookie für "Zugangsdaten merken" setzen oder löschen
                    if remember_me_checkbox:
                        expires = datetime.now() + timedelta(days=30)
                        response.set_cookie(
                            'remembered_personalnummer',
                            personalnummer,
                            expires=expires,
                            httponly=True,
                            samesite=current_app.config.get('REMEMBER_COOKIE_SAMESITE', 'Lax'),
                            secure=bool(current_app.config.get('REMEMBER_COOKIE_SECURE', False)),
                        )
                    else:
                        response.set_cookie(
                            'remembered_personalnummer',
                            '',
                            expires=0,
                            httponly=True,
                            samesite=current_app.config.get('REMEMBER_COOKIE_SAMESITE', 'Lax'),
                            secure=bool(current_app.config.get('REMEMBER_COOKIE_SECURE', False)),
                        )
                    
                    return response
                else:
                    # Fehlgeschlagene Anmeldung loggen
                    _log_login_attempt(conn, personalnummer, user['ID'] if user else None, False, request, 'Ungültiges Passwort')
                    flash('Ungültige Personalnummer oder Passwort.', 'danger')
        except Exception as e:
            flash('Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.', 'danger')
            print(f"Login error: {e}")

    return render_template('login.html', personalnummer=personalnummer_param, remember_me=remember_me)


@auth_bp.route('/login/guest')
def login_guest():
    """Gast-Login - ermöglicht eingeschränkten Zugriff ohne Anmeldung"""
    # Session-Variablen für Gast-Benutzer setzen
    session['user_id'] = None
    session['is_guest'] = True
    session['user_name'] = 'Gast'
    session['user_abteilung'] = None
    session['user_abteilungen'] = []
    session['user_berechtigungen'] = []
    # Gast sieht nur Etikettierung
    from utils.menue_definitions import MENUE_DEFINITIONEN
    session['user_menue_sichtbarkeit'] = {
        m['schluessel']: (m['schluessel'] == 'produktion_etikettierung')
        for m in MENUE_DEFINITIONEN
    }
    
    # Optional: Gast-Login loggen
    try:
        with get_db_connection() as conn:
            _log_login_attempt(conn, 'GAST', None, True, request, 'Gast-Login')
    except Exception as e:
        # Logging-Fehler sollten den Login-Prozess nicht beeinträchtigen
        print(f"Fehler beim Loggen des Gast-Logins: {e}")
    
    flash('Als Gast angemeldet. Sie haben eingeschränkten Zugriff.', 'info')
    return redirect(url_for('produktion.etikettierung'))


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
        
        policy_fehler = validate_passwort_policy(neues_passwort)
        if policy_fehler:
            flash(policy_fehler, 'danger')
            return render_template('passwort_aendern.html')
        if neues_passwort == altes_passwort:
            flash('Das neue Passwort muss sich vom alten Passwort unterscheiden.', 'danger')
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
                
                # Neues Passwort hashen und speichern; ggf. Wechsel-Flag zurücksetzen.
                neues_passwort_hash = generate_password_hash(neues_passwort)
                try:
                    conn.execute(
                        'UPDATE Mitarbeiter SET Passwort = ?, PasswortWechselErforderlich = 0 WHERE ID = ?',
                        (neues_passwort_hash, session['user_id'])
                    )
                except Exception:
                    conn.execute(
                        'UPDATE Mitarbeiter SET Passwort = ? WHERE ID = ?',
                        (neues_passwort_hash, session['user_id'])
                    )
                conn.commit()
                session.pop('passwort_wechsel_erforderlich', None)

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
        email = request.form.get('email', '').strip() or None
        handynummer = request.form.get('handynummer', '').strip() or None
        
        # Validierung
        if not nachname:
            flash('Nachname ist erforderlich.', 'danger')
            return redirect(url_for('auth.profil'))
        
        # Email-Validierung (optional, aber wenn vorhanden, sollte es gültig sein)
        if email and '@' not in email:
            flash('Bitte geben Sie eine gültige E-Mail-Adresse ein.', 'danger')
            return redirect(url_for('auth.profil'))
        
        try:
            with get_db_connection() as conn:
                # Profil aktualisieren
                conn.execute(
                    'UPDATE Mitarbeiter SET Vorname = ?, Nachname = ?, Email = ?, Handynummer = ? WHERE ID = ?',
                    (vorname, nachname, email, handynummer, user_id)
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
                m.Email,
                m.Handynummer,
                m.Aktiv,
                a.Bezeichnung AS PrimaerAbteilung
            FROM Mitarbeiter m
            LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID
            WHERE m.ID = ?
        ''', (user_id,)).fetchone()
        
        # Alle Abteilungen des Benutzers laden (mit IDs)
        alle_abteilungen = conn.execute('''
            SELECT a.ID, a.Bezeichnung, a.ParentAbteilungID
            FROM MitarbeiterAbteilung ma
            JOIN Abteilung a ON ma.AbteilungID = a.ID
            WHERE ma.MitarbeiterID = ? AND a.Aktiv = 1
            ORDER BY a.Sortierung, a.Bezeichnung
        ''', (user_id,)).fetchall()
        
        # Alle aktiven Abteilungen für Auswahl (nicht nur zugeordnete)
        alle_abteilungen_fuer_auswahl = conn.execute('''
            SELECT ID, Bezeichnung, ParentAbteilungID
            FROM Abteilung
            WHERE Aktiv = 1
            ORDER BY Sortierung, Bezeichnung
        ''').fetchall()
        
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
    
    from flask import current_app
    
    return render_template(
        'profil.html',
        user=user,
        alle_abteilungen=alle_abteilungen,
        alle_abteilungen_fuer_auswahl=alle_abteilungen_fuer_auswahl,
        thema_anzahl=thema_anzahl,
        bemerkung_anzahl=bemerkung_anzahl,
        vapid_public_key=current_app.config.get('VAPID_PUBLIC_KEY', ''),
    )


@auth_bp.route("/webauthn/register/options", methods=["POST"])
@login_required
def webauthn_register_options():
    """
    Liefert die Optionen für die Registrierung eines neuen WebAuthn-Credentials
    für den aktuell angemeldeten Benutzer.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Nicht angemeldet"}), 401

    with get_db_connection() as conn:
        user = conn.execute(
            """
            SELECT ID, Personalnummer, Vorname, Nachname
            FROM Mitarbeiter
            WHERE ID = ? AND Aktiv = 1
            """,
            (user_id,),
        ).fetchone()

        if not user:
            return jsonify({"success": False, "message": "Benutzer nicht gefunden"}), 404

        existing = conn.execute(
            """
            SELECT CredentialID
            FROM WebAuthnCredential
            WHERE MitarbeiterID = ? AND Aktiv = 1
            """,
            (user_id,),
        ).fetchall()

    try:
        server = get_fido2_server()
    except RuntimeError as e:
        current_app.logger.error("WebAuthn nicht konfiguriert: %s", e)
        return jsonify({
            "success": False,
            "message": (
                "Biometrische Anmeldung ist auf diesem Server nicht konfiguriert. "
                "Ein Administrator muss WEBAUTHN_RP_ID und WEBAUTHN_ORIGIN setzen."
            ),
        }), 503
    user_entity = build_user_entity(user)
    existing_creds = build_existing_credentials(existing)

    public_key, state = server.register_begin(
        user=user_entity,
        credentials=existing_creds,
        user_verification="required",
        authenticator_attachment="platform",  # bevorzugt integrierte Authenticatoren (Windows Hello, FaceID, TouchID)
        resident_key_requirement="required",  # Discoverable Credential (Passkey) -> Login ohne Personalnummer moeglich
    )

    state_id = store_state(state)
    session["webauthn_register_state_id"] = state_id

    return jsonify(
        {
            "success": True,
            "publicKey": serialize_registration_options(public_key),
        }
    )


@auth_bp.route("/webauthn/register/verify", methods=["POST"])
@login_required
def webauthn_register_verify():
    """
    Prüft die Antwort von navigator.credentials.create() und speichert das Credential.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "Nicht angemeldet"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Keine Daten erhalten"}), 400

    state_id = session.get("webauthn_register_state_id")
    if not state_id:
        return jsonify({"success": False, "message": "Registrierungszustand nicht gefunden"}), 400

    state = pop_state(state_id)
    if state is None:
        return jsonify({"success": False, "message": "Registrierungszustand abgelaufen"}), 400

    server = get_fido2_server()

    try:
        # Neuere python-fido2-Version erwartet ein Response-Mapping,
        # aus dem intern die ClientData/AttestationObject extrahiert werden.
        response = {
            "id": data.get("id"),
            "rawId": data.get("rawId"),
            "type": data.get("type", "public-key"),
            "response": {
                "clientDataJSON": data.get("clientDataJSON"),
                "attestationObject": data.get("attestationObject"),
            },
            "clientExtensionResults": data.get("clientExtensionResults") or {},
        }

        auth_data = server.register_complete(state, response)
        cred_id_b64, public_key_b64, sign_count = extract_attested_credential(auth_data)

        label = data.get("label") or "Biometrisches Gerät"

        from datetime import datetime

        with get_db_connection() as conn:
            sql = upsert_ignore(
                'WebAuthnCredential',
                ('MitarbeiterID', 'CredentialID', 'PublicKey', 'SignCount', 'Label', 'ErstelltAm', 'Aktiv'),
                ('MitarbeiterID', 'CredentialID'),
            )
            conn.execute(
                sql,
                (
                    user_id,
                    cred_id_b64,
                    public_key_b64,
                    sign_count,
                    label,
                    datetime.utcnow().isoformat(timespec="seconds"),
                    1,
                ),
            )

        return jsonify({"success": True})
    except Exception as e:
        print(f"WebAuthn Register Fehler: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Registrierung fehlgeschlagen: {str(e)}"}), 400


@auth_bp.route("/webauthn/login/options", methods=["POST"])
def webauthn_login_options():
    """
    Liefert die Optionen für einen WebAuthn-Login.

    Zwei Betriebsarten:

    * **Mit Personalnummer** (klassisch): Der Server liefert die Liste der
      zulaessigen Credentials (``allowCredentials``) - passend fuer klassische
      Non-Resident-Credentials.
    * **Ohne Personalnummer** (usernameless / Passkey / Conditional UI):
      ``allowCredentials`` bleibt leer. Der Authenticator waehlt ein
      discoverable Credential aus und sendet den ``userHandle`` mit. Der
      eigentliche Benutzer wird dann in ``webauthn_login_verify`` ermittelt.
    """
    data = request.get_json() or {}
    personalnummer = (data.get("personalnummer") or "").strip() or None

    user_id: int | None = None
    existing_creds = []

    if personalnummer:
        with get_db_connection() as conn:
            user = conn.execute(
                """
                SELECT ID, Personalnummer, Vorname, Nachname
                FROM Mitarbeiter
                WHERE Personalnummer = ? AND Aktiv = 1
                """,
                (personalnummer,),
            ).fetchone()

            if not user:
                return jsonify({"success": False, "message": "Benutzer nicht gefunden oder inaktiv"}), 404

            creds = conn.execute(
                """
                SELECT CredentialID
                FROM WebAuthnCredential
                WHERE MitarbeiterID = ? AND Aktiv = 1
                """,
                (user["ID"],),
            ).fetchall()

        if not creds:
            return jsonify({"success": False, "message": "Für diesen Benutzer ist keine biometrische Anmeldung eingerichtet."}), 400

        user_id = user["ID"]
        existing_creds = build_existing_credentials(creds)

    try:
        server = get_fido2_server()
    except RuntimeError as e:
        current_app.logger.error("WebAuthn nicht konfiguriert: %s", e)
        return jsonify({
            "success": False,
            "message": (
                "Biometrische Anmeldung ist auf diesem Server nicht konfiguriert. "
                "Ein Administrator muss WEBAUTHN_RP_ID und WEBAUTHN_ORIGIN setzen."
            ),
        }), 503

    public_key, state = server.authenticate_begin(
        credentials=existing_creds or None,
        user_verification="preferred",
    )

    state_id = store_state(state)
    session["webauthn_login_state_id"] = state_id
    if user_id is not None:
        session["webauthn_login_user_id"] = user_id
    else:
        # Im usernameless-Flow ermitteln wir den Benutzer erst in /verify aus dem userHandle.
        session.pop("webauthn_login_user_id", None)

    return jsonify(
        {
            "success": True,
            "publicKey": serialize_authentication_options(public_key),
        }
    )


@auth_bp.route("/webauthn/login/verify", methods=["POST"])
@limiter.limit('20/minute;100/hour')
def webauthn_login_verify():
    """
    Prüft die Antwort von navigator.credentials.get() und meldet den Benutzer an,
    wenn die Signatur gültig ist.
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Keine Daten erhalten"}), 400

    state_id = session.get("webauthn_login_state_id")
    user_id = session.get("webauthn_login_user_id")

    if not state_id:
        return jsonify({"success": False, "message": "Login-Zustand nicht gefunden"}), 400

    # Usernameless / Conditional UI: Benutzer aus dem userHandle ableiten, den der Authenticator zurueckgibt.
    if not user_id:
        user_handle_b64 = data.get("userHandle")
        if not user_handle_b64:
            return jsonify({
                "success": False,
                "message": "Kein Benutzer zugeordnet. Bitte Personalnummer eingeben oder biometrische Anmeldung neu einrichten."
            }), 400
        try:
            user_id = decode_user_handle_to_id(user_handle_b64)
        except Exception:
            return jsonify({"success": False, "message": "Ungültige Authenticator-Antwort (userHandle)."}), 400

    state = pop_state(state_id)
    if state is None:
        return jsonify({"success": False, "message": "Login-Zustand abgelaufen"}), 400

    server = get_fido2_server()

    try:
        # Passende Credentials aus der Datenbank laden und in AttestedCredentialData umwandeln
        with get_db_connection() as conn:
            cred_rows = conn.execute(
                """
                SELECT CredentialID, PublicKey
                FROM WebAuthnCredential
                WHERE MitarbeiterID = ? AND Aktiv = 1
                """,
                (user_id,),
            ).fetchall()

        if not cred_rows:
            return jsonify({"success": False, "message": "Keine aktiven biometrischen Credentials gefunden."}), 400

        credentials = build_attested_credentials(cred_rows)
        if not credentials:
            # Detailliertere Fehlermeldung für Debugging
            return jsonify({
                "success": False,
                "message": f"Credentials konnten nicht geladen werden. ({len(cred_rows)} Credential(s) in DB gefunden, aber keines konnte verarbeitet werden. Bitte biometrische Anmeldung neu einrichten.)"
            }), 400

        # Response-Objekt für authenticate_complete gemäß aktueller fido2-API aufbauen
        response = {
            "id": data.get("id"),
            "rawId": data.get("rawId"),
            "type": data.get("type", "public-key"),
            "response": {
                "clientDataJSON": data.get("clientDataJSON"),
                "authenticatorData": data.get("authenticatorData"),
                "signature": data.get("signature"),
                "userHandle": data.get("userHandle"),
            },
            "clientExtensionResults": data.get("clientExtensionResults") or {},
        }

        # authenticate_complete validiert Challenge, Origin, Signatur etc.
        auth_cred = server.authenticate_complete(
            state,
            credentials,
            response,
        )

        from datetime import datetime

        # Anmeldesession setzen, Benutzer laden
        with get_db_connection() as conn:
            user = conn.execute(
                """
                SELECT m.*, a.Bezeichnung as AbteilungName
                FROM Mitarbeiter m
                LEFT JOIN Abteilung a ON m.PrimaerAbteilungID = a.ID
                WHERE m.ID = ? AND m.Aktiv = 1
                """,
                (user_id,),
            ).fetchone()

            if not user:
                return jsonify({"success": False, "message": "Benutzer nicht gefunden"}), 404

            # Credential-Datensatz aktualisieren (nur LetzteVerwendung; SignCount bleibt unverändert)
            credential_id_b64 = base64.urlsafe_b64encode(
                auth_cred.credential_id
            ).rstrip(b"=").decode("ascii")
            conn.execute(
                """
                UPDATE WebAuthnCredential
                SET LetzteVerwendung = ?
                WHERE MitarbeiterID = ? AND CredentialID = ?
                """,
                (
                    datetime.utcnow().isoformat(timespec="seconds"),
                    user_id,
                    credential_id_b64,
                ),
            )

            # Session wie beim Passwort-Login setzen
            session["user_id"] = user["ID"]
            session["user_name"] = f"{user['Vorname']} {user['Nachname']}"
            session["user_abteilung"] = (
                user["AbteilungName"] if user["AbteilungName"] else None
            )

            # Alle Abteilungen laden
            alle_abteilungen = []
            if user["AbteilungName"]:
                alle_abteilungen.append(user["AbteilungName"])

            zusaetzliche = conn.execute(
                """
                SELECT a.Bezeichnung
                FROM MitarbeiterAbteilung ma
                JOIN Abteilung a ON ma.AbteilungID = a.ID
                WHERE ma.MitarbeiterID = ? AND a.Aktiv = 1
                """,
                (user["ID"],),
            ).fetchall()

            for abt in zusaetzliche:
                if abt["Bezeichnung"] not in alle_abteilungen:
                    alle_abteilungen.append(abt["Bezeichnung"])

            session["user_abteilungen"] = alle_abteilungen

            # Berechtigungen laden
            berechtigungen = conn.execute(
                """
                SELECT b.Schluessel
                FROM MitarbeiterBerechtigung mb
                JOIN Berechtigung b ON mb.BerechtigungID = b.ID
                WHERE mb.MitarbeiterID = ? AND b.Aktiv = 1
                """,
                (user["ID"],),
            ).fetchall()

            session["user_berechtigungen"] = [b["Schluessel"] for b in berechtigungen]

            from utils.menue_definitions import get_menue_sichtbarkeit_fuer_mitarbeiter

            session["user_menue_sichtbarkeit"] = get_menue_sichtbarkeit_fuer_mitarbeiter(
                user["ID"], conn
            )

            start_ep = (
                user["StartseiteNachLoginEndpunkt"]
                if "StartseiteNachLoginEndpunkt" in user.keys()
                else None
            )
            next_param = data.get("next")
            redirect_url = resolve_post_login_redirect_url(start_ep, next_param)

        # Session dauerhaft speichern (30 Tage bei WebAuthn – biometrische Anmeldung auf vertrauenswürdigem Gerät)
        session.permanent = True
        old_lifetime = current_app.config["PERMANENT_SESSION_LIFETIME"]
        current_app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
        g.login_session_lifetime_to_restore = old_lifetime

        # Vorherige Flash-Messages (z.B. "Abgemeldet", "Bitte zuerst anmelden") entfernen
        session.pop("_flashes", None)
        # Zwischenschritte des WebAuthn-Handshakes aufraeumen
        session.pop("webauthn_login_state_id", None)
        session.pop("webauthn_login_user_id", None)

        return jsonify({"success": True, "redirect_url": redirect_url})
    except Exception as e:
        print(f"WebAuthn Login Fehler: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Biometrischer Login fehlgeschlagen: {str(e)}"}), 400


@auth_bp.route('/profil/benachrichtigungen', methods=['GET'])
@login_required
def benachrichtigungen_get():
    """Lädt die Benachrichtigungseinstellungen des aktuellen Benutzers"""
    user_id = session.get('user_id')
    
    with get_db_connection() as conn:
        # Aktive Kanäle
        kanale = conn.execute('''
            SELECT KanalTyp FROM BenachrichtigungKanal
            WHERE MitarbeiterID = ? AND Aktiv = 1
        ''', (user_id,)).fetchall()
        kanale_list = [k['KanalTyp'] for k in kanale] if kanale else []
        
        # Einstellungen
        einstellungen = conn.execute('''
            SELECT Modul, Aktion, AbteilungID, Aktiv
            FROM BenachrichtigungEinstellung
            WHERE MitarbeiterID = ?
        ''', (user_id,)).fetchall()
        
        einstellungen_list = [
            {
                'modul': e['Modul'],
                'aktion': e['Aktion'],
                'abteilung_id': e['AbteilungID'],
                'aktiv': bool(e['Aktiv'])
            }
            for e in einstellungen
        ]
    
    return jsonify({
        'kanale': kanale_list,
        'einstellungen': einstellungen_list
    })


@auth_bp.route('/profil/benachrichtigungen', methods=['POST'])
@login_required
def benachrichtigungen_save():
    """Speichert die Benachrichtigungseinstellungen des aktuellen Benutzers"""
    user_id = session.get('user_id')
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': 'Keine Daten erhalten'}), 400
    
    try:
        with get_db_connection() as conn:
            # Kanäle speichern
            kanale = data.get('kanale', [])
            
            # Alle Kanäle deaktivieren
            conn.execute('''
                UPDATE BenachrichtigungKanal
                SET Aktiv = 0
                WHERE MitarbeiterID = ?
            ''', (user_id,))
            
            # Aktive Kanäle aktivieren
            kanal_upsert_sql = upsert_replace(
                'BenachrichtigungKanal',
                ('MitarbeiterID', 'KanalTyp', 'Aktiv'),
                ('MitarbeiterID', 'KanalTyp'),
                update_cols=('Aktiv',),
            )
            for kanal_typ in kanale:
                conn.execute(kanal_upsert_sql, (user_id, kanal_typ, 1))
            
            # Einstellungen löschen
            conn.execute('''
                DELETE FROM BenachrichtigungEinstellung
                WHERE MitarbeiterID = ?
            ''', (user_id,))
            
            # Neue Einstellungen speichern
            einstellungen = data.get('einstellungen', [])
            for einstellung in einstellungen:
                modul = (einstellung.get('modul') or '').strip().lower()
                aktion = (einstellung.get('aktion') or '').strip().lower()
                conn.execute('''
                    INSERT INTO BenachrichtigungEinstellung (
                        MitarbeiterID, Modul, Aktion, AbteilungID, Aktiv
                    )
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    modul,
                    aktion,
                    einstellung.get('abteilung_id'),
                    1
                ))
            
            conn.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/profil/push-subscription', methods=['POST'])
@login_required
def push_subscription_save():
    """Speichert eine Web Push Subscription für den aktuellen Benutzer"""
    user_id = session.get('user_id')
    subscription = request.get_json()
    
    if not subscription:
        return jsonify({'success': False, 'message': 'Keine Subscription-Daten erhalten'}), 400
    
    try:
        from utils.benachrichtigungen_push import speichere_push_subscription
        
        with get_db_connection() as conn:
            if speichere_push_subscription(user_id, subscription, conn):
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'message': 'Fehler beim Speichern'}), 500
                
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/profil/push-test', methods=['POST'])
@login_required
def push_test():
    """Sendet eine Test-Push-Benachrichtigung an den aktuellen Benutzer"""
    user_id = session.get('user_id')
    
    try:
        from utils.benachrichtigungen_push import versende_test_push
        
        with get_db_connection() as conn:
            ok, err = versende_test_push(user_id, conn)
            if ok:
                return jsonify({'success': True, 'message': 'Test-Push-Nachricht wurde gesendet'})
            return jsonify({
                'success': False,
                'message': err or 'Push-Benachrichtigungen sind nicht aktiviert oder konfiguriert'
            }), 400
                
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
