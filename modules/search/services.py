"""
Search Services
Business-Logik für globale Suche
"""

from utils.abteilungen import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_sichtbarkeits_filter_query, build_ersatzteil_zugriff_filter


def parse_search_query(query):
    """
    Parst eine Suchanfrage und extrahiert Vorzeichen, Trennezeichen und Suchbegriff
    
    Args:
        query: Suchstring (z.B. "t123", "t@123", "e@ABC-123", "123")
        
    Returns:
        Dictionary mit:
        - prefix: Vorzeichen ('t', 'e', 'b', 'a' oder None)
        - is_id_search: True wenn @ verwendet wird
        - search_term: Der eigentliche Suchbegriff
    """
    if not query:
        return {'prefix': None, 'is_id_search': False, 'search_term': ''}
    
    query = query.strip()
    
    # Prüfe auf @ für ID-Suche
    if '@' in query:
        parts = query.split('@', 1)
        prefix = parts[0].lower() if parts[0] else None
        search_term = parts[1] if len(parts) > 1 else ''
        return {
            'prefix': prefix if prefix in ['t', 'e', 'b', 'a'] else None,
            'is_id_search': True,
            'search_term': search_term
        }
    
    # Prüfe auf Vorzeichen ohne @
    if len(query) > 1 and query[0].lower() in ['t', 'e', 'b', 'a']:
        prefix = query[0].lower()
        search_term = query[1:]
        return {
            'prefix': prefix,
            'is_id_search': False,
            'search_term': search_term
        }
    
    # Kein Vorzeichen - globale Suche
    return {
        'prefix': None,
        'is_id_search': False,
        'search_term': query
    }


def search_themen(query, mitarbeiter_id, conn, limit=10):
    """
    Sucht in Schichtbuch-Themen
    
    Args:
        query: Dictionary von parse_search_query
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        limit: Maximale Anzahl Ergebnisse
        
    Returns:
        Liste von Dictionaries mit Thema-Daten
    """
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    if query['is_id_search']:
        # ID-basierte Suche
        try:
            thema_id = int(query['search_term'])
            base_query = '''
                SELECT 
                    t.ID,
                    'thema' AS type,
                    'Thema #' || t.ID AS title,
                    COALESCE(MAX(bm.Bemerkung), '') AS preview,
                    b.Bezeichnung AS Bereich,
                    g.Bezeichnung AS Gewerk,
                    s.Bezeichnung AS Status
                FROM SchichtbuchThema t
                JOIN Gewerke g ON t.GewerkID = g.ID
                JOIN Bereich b ON g.BereichID = b.ID
                JOIN Status s ON t.StatusID = s.ID
                LEFT JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID AND bm.Gelöscht = 0
                WHERE t.Gelöscht = 0 AND t.ID = ?
            '''
            params = [thema_id]
        except ValueError:
            return []
    else:
        # Text-basierte Suche
        base_query = '''
            SELECT DISTINCT
                t.ID,
                'thema' AS type,
                'Thema #' || t.ID AS title,
                COALESCE(MAX(bm.Bemerkung), '') AS preview,
                b.Bezeichnung AS Bereich,
                g.Bezeichnung AS Gewerk,
                s.Bezeichnung AS Status
            FROM SchichtbuchThema t
            JOIN Gewerke g ON t.GewerkID = g.ID
            JOIN Bereich b ON g.BereichID = b.ID
            JOIN Status s ON t.StatusID = s.ID
            LEFT JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID AND bm.Gelöscht = 0
            WHERE t.Gelöscht = 0
            AND (
                CAST(t.ID AS TEXT) LIKE ? OR
                bm.Bemerkung LIKE ?
            )
        '''
        search_pattern = f'%{query["search_term"]}%'
        params = [search_pattern, search_pattern]
    
    # Sichtbarkeitsfilter anwenden
    if sichtbare_abteilungen:
        base_query, params = build_sichtbarkeits_filter_query(
            base_query,
            sichtbare_abteilungen,
            params,
            table_alias='t'
        )
    else:
        # Keine Berechtigung
        return []
    
    base_query += ' GROUP BY t.ID LIMIT ?'
    params.append(limit)
    
    results = conn.execute(base_query, params).fetchall()
    return [dict(row) for row in results]


def search_ersatzteile(query, mitarbeiter_id, conn, is_admin=False, limit=10):
    """
    Sucht in Ersatzteilen
    
    Args:
        query: Dictionary von parse_search_query
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob Benutzer Admin ist
        limit: Maximale Anzahl Ergebnisse
        
    Returns:
        Liste von Dictionaries mit Ersatzteil-Daten
    """
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    if query['is_id_search']:
        # ID oder Bestellnummer basierte Suche
        base_query = '''
            SELECT 
                e.ID,
                'ersatzteil' AS type,
                e.Bestellnummer AS title,
                e.Bezeichnung AS preview,
                e.Bestellnummer,
                e.Bezeichnung,
                k.Bezeichnung AS Kategorie
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            WHERE e.Gelöscht = 0
            AND (e.ID = ? OR e.Bestellnummer = ?)
        '''
        try:
            # Versuche zuerst als ID
            item_id = int(query['search_term'])
            params = [item_id, query['search_term']]
        except ValueError:
            # Nur Bestellnummer
            params = [0, query['search_term']]
    else:
        # Text-basierte Suche
        base_query = '''
            SELECT 
                e.ID,
                'ersatzteil' AS type,
                e.Bestellnummer AS title,
                e.Bezeichnung AS preview,
                e.Bestellnummer,
                e.Bezeichnung,
                k.Bezeichnung AS Kategorie
            FROM Ersatzteil e
            LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
            WHERE e.Gelöscht = 0
            AND (
                e.Bestellnummer LIKE ? OR
                e.Bezeichnung LIKE ? OR
                CAST(e.ID AS TEXT) LIKE ?
            )
        '''
        search_pattern = f'%{query["search_term"]}%'
        params = [search_pattern, search_pattern, search_pattern]
    
    # Berechtigungsfilter anwenden
    base_query, params = build_ersatzteil_zugriff_filter(
        base_query,
        mitarbeiter_id,
        sichtbare_abteilungen,
        is_admin,
        params
    )
    
    base_query += ' LIMIT ?'
    params.append(limit)
    
    results = conn.execute(base_query, params).fetchall()
    return [dict(row) for row in results]


def search_bestellungen(query, mitarbeiter_id, conn, is_admin=False, limit=10):
    """
    Sucht in Bestellungen
    
    Args:
        query: Dictionary von parse_search_query
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob Benutzer Admin ist
        limit: Maximale Anzahl Ergebnisse
        
    Returns:
        Liste von Dictionaries mit Bestellungs-Daten
    """
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    if query['is_id_search']:
        # ID-basierte Suche
        try:
            bestellung_id = int(query['search_term'])
            base_query = '''
                SELECT 
                    b.ID,
                    'bestellung' AS type,
                    'Bestellung #' || b.ID AS title,
                    l.Name || ' - ' || b.Status AS preview,
                    b.ID AS BestellungID,
                    b.Status,
                    l.Name AS LieferantName,
                    abt.Bezeichnung AS Abteilung
                FROM Bestellung b
                LEFT JOIN Lieferant l ON b.LieferantID = l.ID
                LEFT JOIN Abteilung abt ON b.ErstellerAbteilungID = abt.ID
                WHERE b.Gelöscht = 0 AND b.ID = ?
            '''
            params = [bestellung_id]
        except ValueError:
            return []
    else:
        # Text-basierte Suche
        base_query = '''
            SELECT 
                b.ID,
                'bestellung' AS type,
                'Bestellung #' || b.ID AS title,
                l.Name || ' - ' || b.Status AS preview,
                b.ID AS BestellungID,
                b.Status,
                l.Name AS LieferantName,
                abt.Bezeichnung AS Abteilung
            FROM Bestellung b
            LEFT JOIN Lieferant l ON b.LieferantID = l.ID
            LEFT JOIN Abteilung abt ON b.ErstellerAbteilungID = abt.ID
            WHERE b.Gelöscht = 0
            AND (
                CAST(b.ID AS TEXT) LIKE ? OR
                l.Name LIKE ? OR
                b.Status LIKE ?
            )
        '''
        search_pattern = f'%{query["search_term"]}%'
        params = [search_pattern, search_pattern, search_pattern]
    
    # Berechtigungsfilter
    if not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        base_query += f'''
            AND (
                b.ErstellerAbteilungID IN ({placeholders}) OR
                EXISTS (
                    SELECT 1 FROM BestellungSichtbarkeit bs
                    WHERE bs.BestellungID = b.ID
                    AND bs.AbteilungID IN ({placeholders})
                )
            )
        '''
        params.extend(sichtbare_abteilungen)
        params.extend(sichtbare_abteilungen)
    elif not is_admin:
        # Keine Berechtigung
        return []
    
    base_query += ' LIMIT ?'
    params.append(limit)
    
    results = conn.execute(base_query, params).fetchall()
    return [dict(row) for row in results]


def search_angebotsanfragen(query, mitarbeiter_id, conn, is_admin=False, limit=10):
    """
    Sucht in Angebotsanfragen
    
    Args:
        query: Dictionary von parse_search_query
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob Benutzer Admin ist
        limit: Maximale Anzahl Ergebnisse
        
    Returns:
        Liste von Dictionaries mit Angebotsanfrage-Daten
    """
    sichtbare_abteilungen = get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn)
    
    if query['is_id_search']:
        # ID-basierte Suche
        try:
            anfrage_id = int(query['search_term'])
            base_query = '''
                SELECT 
                    a.ID,
                    'angebotsanfrage' AS type,
                    'Angebotsanfrage #' || a.ID AS title,
                    l.Name || ' - ' || a.Status AS preview,
                    a.ID AS AngebotsanfrageID,
                    a.Status,
                    l.Name AS LieferantName,
                    abt.Bezeichnung AS Abteilung
                FROM Angebotsanfrage a
                LEFT JOIN Lieferant l ON a.LieferantID = l.ID
                LEFT JOIN Abteilung abt ON a.ErstellerAbteilungID = abt.ID
                WHERE a.ID = ?
            '''
            params = [anfrage_id]
        except ValueError:
            return []
    else:
        # Text-basierte Suche
        base_query = '''
            SELECT 
                a.ID,
                'angebotsanfrage' AS type,
                'Angebotsanfrage #' || a.ID AS title,
                l.Name || ' - ' || a.Status AS preview,
                a.ID AS AngebotsanfrageID,
                a.Status,
                l.Name AS LieferantName,
                abt.Bezeichnung AS Abteilung
            FROM Angebotsanfrage a
            LEFT JOIN Lieferant l ON a.LieferantID = l.ID
            LEFT JOIN Abteilung abt ON a.ErstellerAbteilungID = abt.ID
            WHERE (
                CAST(a.ID AS TEXT) LIKE ? OR
                l.Name LIKE ? OR
                a.Status LIKE ?
            )
        '''
        search_pattern = f'%{query["search_term"]}%'
        params = [search_pattern, search_pattern, search_pattern]
    
    # Berechtigungsfilter
    if not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        base_query += f' AND a.ErstellerAbteilungID IN ({placeholders})'
        params.extend(sichtbare_abteilungen)
    elif not is_admin:
        # Keine Berechtigung
        return []
    
    base_query += ' LIMIT ?'
    params.append(limit)
    
    results = conn.execute(base_query, params).fetchall()
    return [dict(row) for row in results]


def search_all(parsed_query, mitarbeiter_id, conn, is_admin=False, limit_per_type=10):
    """
    Sucht in allen Entitäten basierend auf dem Vorzeichen
    
    Args:
        parsed_query: Dictionary von parse_search_query
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob Benutzer Admin ist
        limit_per_type: Maximale Ergebnisse pro Typ
        
    Returns:
        Dictionary mit gruppierten Ergebnissen:
        {
            'themen': [...],
            'ersatzteile': [...],
            'bestellungen': [...],
            'angebotsanfragen': [...]
        }
    """
    results = {
        'themen': [],
        'ersatzteile': [],
        'bestellungen': [],
        'angebotsanfragen': []
    }
    
    prefix = parsed_query.get('prefix')
    
    # Suche basierend auf Vorzeichen
    if prefix is None or prefix == 't':
        # Suche in Themen
        try:
            themes = search_themen(parsed_query, mitarbeiter_id, conn, limit_per_type)
            results['themen'] = themes
        except Exception as e:
            print(f"Fehler bei Themensuche: {e}")
    
    if prefix is None or prefix == 'e':
        # Suche in Ersatzteilen
        try:
            ersatzteile = search_ersatzteile(parsed_query, mitarbeiter_id, conn, is_admin, limit_per_type)
            results['ersatzteile'] = ersatzteile
        except Exception as e:
            print(f"Fehler bei Ersatzteilsuche: {e}")
    
    if prefix is None or prefix == 'b':
        # Suche in Bestellungen
        try:
            bestellungen = search_bestellungen(parsed_query, mitarbeiter_id, conn, is_admin, limit_per_type)
            results['bestellungen'] = bestellungen
        except Exception as e:
            print(f"Fehler bei Bestellungssuche: {e}")
    
    if prefix is None or prefix == 'a':
        # Suche in Angebotsanfragen
        try:
            anfragen = search_angebotsanfragen(parsed_query, mitarbeiter_id, conn, is_admin, limit_per_type)
            results['angebotsanfragen'] = anfragen
        except Exception as e:
            print(f"Fehler bei Angebotsanfragensuche: {e}")
    
    return results
