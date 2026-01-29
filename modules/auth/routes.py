"""
Auth Routes - Login, Logout
"""

import base64
import traceback
from flask import render_template, request, redirect, url_for, session, flash, make_response, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
from . import auth_bp
from utils import get_db_connection
from utils.decorators import is_safe_url, login_required
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
)


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
                    
                    # Berechtigungen des Mitarbeiters laden
                    berechtigungen = conn.execute('''
                        SELECT b.Schluessel
                        FROM MitarbeiterBerechtigung mb
                        JOIN Berechtigung b ON mb.BerechtigungID = b.ID
                        WHERE mb.MitarbeiterID = ? AND b.Aktiv = 1
                    ''', (user['ID'],)).fetchall()
                    
                    session['user_berechtigungen'] = [b['Schluessel'] for b in berechtigungen]
                    
                    # Weiterleitung zur ursprünglichen URL (next-Parameter) oder zum Dashboard
                    next_page = request.args.get('next')
                    if next_page and is_safe_url(next_page):
                        response = make_response(redirect(next_page))
                    else:
                        response = make_response(redirect(url_for('dashboard.dashboard')))
                    
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

    server = get_fido2_server()
    user_entity = build_user_entity(user)
    existing_creds = build_existing_credentials(existing)

    public_key, state = server.register_begin(
        user=user_entity,
        credentials=existing_creds,
        user_verification="preferred",
        authenticator_attachment="platform",  # bevorzugt integrierte Authenticatoren (Windows Hello, FaceID, TouchID)
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
            conn.execute(
                """
                INSERT OR IGNORE INTO WebAuthnCredential (
                    MitarbeiterID, CredentialID, PublicKey, SignCount, Label, ErstelltAm, Aktiv
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user_id,
                    cred_id_b64,
                    public_key_b64,
                    sign_count,
                    label,
                    datetime.utcnow().isoformat(timespec="seconds"),
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
    Erwartet die Personalnummer des Benutzers, um die passenden Credentials zu finden.
    """
    data = request.get_json() or {}
    personalnummer = data.get("personalnummer")

    if not personalnummer:
        return jsonify({"success": False, "message": "Personalnummer erforderlich"}), 400

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

    server = get_fido2_server()
    existing_creds = build_existing_credentials(creds)

    public_key, state = server.authenticate_begin(
        credentials=existing_creds,
        user_verification="preferred",
    )

    state_id = store_state(state)
    session["webauthn_login_state_id"] = state_id
    session["webauthn_login_user_id"] = user["ID"]

    return jsonify(
        {
            "success": True,
            "publicKey": serialize_authentication_options(public_key),
        }
    )


@auth_bp.route("/webauthn/login/verify", methods=["POST"])
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

    if not state_id or not user_id:
        return jsonify({"success": False, "message": "Login-Zustand nicht gefunden"}), 400

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

        # Vorherige Flash-Messages (z.B. "Abgemeldet", "Bitte zuerst anmelden") entfernen
        session.pop("_flashes", None)

        # Aufrufende Seite entscheidet über Redirect
        return jsonify({"success": True})
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
            for kanal_typ in kanale:
                conn.execute('''
                    INSERT OR REPLACE INTO BenachrichtigungKanal (
                        MitarbeiterID, KanalTyp, Aktiv
                    )
                    VALUES (?, ?, 1)
                ''', (user_id, kanal_typ))
            
            # Einstellungen löschen
            conn.execute('''
                DELETE FROM BenachrichtigungEinstellung
                WHERE MitarbeiterID = ?
            ''', (user_id,))
            
            # Neue Einstellungen speichern
            einstellungen = data.get('einstellungen', [])
            for einstellung in einstellungen:
                conn.execute('''
                    INSERT INTO BenachrichtigungEinstellung (
                        MitarbeiterID, Modul, Aktion, AbteilungID, Aktiv
                    )
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    einstellung['modul'],
                    einstellung['aktion'],
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
            if versende_test_push(user_id, conn):
                return jsonify({'success': True, 'message': 'Test-Push-Nachricht wurde gesendet'})
            else:
                return jsonify({'success': False, 'message': 'Push-Benachrichtigungen sind nicht aktiviert oder konfiguriert'}), 400
                
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
