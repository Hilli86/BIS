"""
Lieferant Routes - Lieferanten-Verwaltung
"""

from flask import render_template, request, redirect, url_for, session, flash, jsonify
from .. import ersatzteile_bp
from utils import get_db_connection, login_required, get_sichtbare_abteilungen_fuer_mitarbeiter


@ersatzteile_bp.route('/lieferanten')
@login_required
def lieferanten_liste():
    """Lieferanten-Liste (für alle Benutzer sichtbar, keine Abteilungsfilterung)"""
    with get_db_connection() as conn:
        lieferanten = conn.execute('''
            SELECT 
                l.ID,
                l.Name,
                l.Kontaktperson,
                l.Telefon,
                l.Email,
                l.Strasse,
                l.PLZ,
                l.Ort,
                l.Aktiv,
                COUNT(e.ID) AS ErsatzteilAnzahl
            FROM Lieferant l
            LEFT JOIN Ersatzteil e ON l.ID = e.LieferantID AND e.Gelöscht = 0
            WHERE l.Gelöscht = 0
            GROUP BY l.ID
            ORDER BY l.Name
        ''').fetchall()
    
    return render_template('lieferanten_liste.html', lieferanten=lieferanten)


@ersatzteile_bp.route('/lieferanten/<int:lieferant_id>')
@login_required
def lieferant_detail(lieferant_id):
    """Lieferant-Detailansicht mit zugehörigen Ersatzteilen"""
    with get_db_connection() as conn:
        lieferant = conn.execute('''
            SELECT ID, Name, Kontaktperson, Telefon, Email, Strasse, PLZ, Ort, Aktiv
            FROM Lieferant
            WHERE ID = ? AND Gelöscht = 0
        ''', (lieferant_id,)).fetchone()
        
        if not lieferant:
            flash('Lieferant nicht gefunden.', 'danger')
            return redirect(url_for('ersatzteile.lieferanten_liste'))
        
        # Ersatzteile dieses Lieferanten laden (nur die, auf die der Benutzer Zugriff hat)
        mitarbeiter_id = session.get('user_id')
        sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
        is_admin = 'admin' in session.get('user_berechtigungen', [])
        
        query = '''
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
            WHERE e.LieferantID = ? AND e.Gelöscht = 0
        '''
        params = [lieferant_id]
        
        # Berechtigungsfilter für Ersatzteile
        if not is_admin:
            if sichtbare_abteilungen:
                placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                query += f'''
                    AND (
                        e.ErstelltVonID = ? OR
                        e.ID IN (
                            SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                            WHERE AbteilungID IN ({placeholders})
                        )
                    )
                '''
                params.append(mitarbeiter_id)
                params.extend(sichtbare_abteilungen)
            else:
                # Nur selbst erstellte Artikel
                query += ' AND e.ErstelltVonID = ?'
                params.append(mitarbeiter_id)
        
        query += ' ORDER BY e.Bezeichnung'
        ersatzteile = conn.execute(query, params).fetchall()
    
    return render_template('lieferant_detail.html', lieferant=lieferant, ersatzteile=ersatzteile)


@ersatzteile_bp.route('/api/ersatzteile/lieferant/<int:lieferant_id>')
@login_required
def api_ersatzteile_lieferant(lieferant_id):
    """API: Alle Ersatzteile eines Lieferanten abrufen"""
    mitarbeiter_id = session.get('user_id')
    
    try:
        with get_db_connection() as conn:
            # Berechtigte Abteilungen ermitteln
            sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
            is_admin = 'admin' in session.get('user_berechtigungen', [])
            
            # Ersatzteile laden
            query = '''
                SELECT e.ID, e.Bestellnummer, e.Bezeichnung, e.Preis, e.Waehrung, e.AktuellerBestand, e.Einheit
                FROM Ersatzteil e
                WHERE e.LieferantID = ? AND e.Gelöscht = 0
            '''
            params = [lieferant_id]
            
            # Berechtigungsfilter
            if not is_admin:
                if sichtbare_abteilungen:
                    placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
                    query += f'''
                        AND (
                            e.ErstelltVonID = ? OR
                            e.ID IN (
                                SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                                WHERE AbteilungID IN ({placeholders})
                            )
                        )
                    '''
                    params.append(mitarbeiter_id)
                    params.extend(sichtbare_abteilungen)
                else:
                    # Nur selbst erstellte Artikel
                    query += ' AND e.ErstelltVonID = ?'
                    params.append(mitarbeiter_id)
            
            query += ' ORDER BY e.Bestellnummer, e.Bezeichnung'
            ersatzteile = conn.execute(query, params).fetchall()
            
            # In JSON-Format umwandeln
            result = []
            for e in ersatzteile:
                result.append({
                    'id': e['ID'],
                    'bestellnummer': e['Bestellnummer'],
                    'bezeichnung': e['Bezeichnung'],
                    'preis': float(e['Preis']) if e['Preis'] else None,
                    'waehrung': e['Waehrung'] or 'EUR',
                    'bestand': e['AktuellerBestand'] or 0,
                    'einheit': e['Einheit'] or ''
                })
            
            return jsonify({
                'success': True,
                'ersatzteile': result
            })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Fehler in api_ersatzteile_lieferant: {e}")
        print(error_trace)
        return jsonify({
            'success': False,
            'message': f'Fehler: {str(e)}',
            'trace': error_trace
        }), 500
