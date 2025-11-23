"""
Dashboard Services
Business-Logik für Dashboard-Daten
"""

from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import row_to_dict


def get_status_statistiken(sichtbare_abteilungen, conn):
    """
    Ermittelt Status-Statistiken für Schichtbuch-Themen
    
    Args:
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        conn: Datenbankverbindung
        
    Returns:
        Liste von Status-Daten
    """
    from utils.helpers import build_sichtbarkeits_filter_query
    
    base_query = '''
        SELECT S.Bezeichnung AS Status, S.Farbe, COUNT(T.ID) AS Anzahl
        FROM SchichtbuchThema T
        JOIN Status S ON S.ID = T.StatusID
        WHERE T.Gelöscht = 0
    '''
    
    query, params = build_sichtbarkeits_filter_query(
        base_query, 
        sichtbare_abteilungen, 
        [],
        table_alias='T'
    )
    
    query += ' GROUP BY S.Bezeichnung, S.Farbe ORDER BY S.Sortierung ASC'
    
    return conn.execute(query, params).fetchall()


def get_gesamtanzahl_themen(sichtbare_abteilungen, conn):
    """
    Ermittelt Gesamtanzahl aller sichtbaren Themen
    
    Args:
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        conn: Datenbankverbindung
        
    Returns:
        Anzahl der Themen
    """
    from utils.helpers import build_sichtbarkeits_filter_query
    
    base_query = '''
        SELECT COUNT(DISTINCT T.ID) AS Gesamt
        FROM SchichtbuchThema T
        WHERE T.Gelöscht = 0
    '''
    
    query, params = build_sichtbarkeits_filter_query(
        base_query,
        sichtbare_abteilungen,
        [],
        table_alias='T'
    )
    
    result = conn.execute(query, params).fetchone()
    return result['Gesamt'] if result else 0


def get_aktuelle_themen(sichtbare_abteilungen, conn, limit=10):
    """
    Ermittelt aktuelle Themen (nach letzter Aktivität)
    
    Args:
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        conn: Datenbankverbindung
        limit: Maximale Anzahl (Standard: 10)
        
    Returns:
        Liste von Themen
    """
    from utils.helpers import build_sichtbarkeits_filter_query
    
    base_query = '''
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
    
    query, params = build_sichtbarkeits_filter_query(
        base_query,
        sichtbare_abteilungen,
        [],
        table_alias='T'
    )
    
    query += ''' GROUP BY T.ID
        ORDER BY LetzteAktivitaet DESC
        LIMIT ?'''
    params.append(limit)
    
    return conn.execute(query, params).fetchall()


def get_meine_themen(mitarbeiter_id, sichtbare_abteilungen, conn, limit=10):
    """
    Ermittelt Themen mit eigenen Bemerkungen
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        conn: Datenbankverbindung
        limit: Maximale Anzahl (Standard: 10)
        
    Returns:
        Liste von Themen
    """
    from utils.helpers import build_sichtbarkeits_filter_query
    
    base_query = '''
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
    
    params = [mitarbeiter_id]
    query, params = build_sichtbarkeits_filter_query(
        base_query,
        sichtbare_abteilungen,
        params,
        table_alias='T'
    )
    
    query += ''' GROUP BY T.ID
        ORDER BY LetzteBemerkung DESC
        LIMIT ?'''
    params.append(limit)
    
    return conn.execute(query, params).fetchall()


def get_aktivitaeten(sichtbare_abteilungen, conn, limit=15):
    """
    Ermittelt Aktivitätsübersicht (letzte Bemerkungen)
    
    Args:
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        conn: Datenbankverbindung
        limit: Maximale Anzahl (Standard: 15)
        
    Returns:
        Liste von Aktivitäten
    """
    from utils.helpers import build_sichtbarkeits_filter_query
    
    base_query = '''
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
    
    query, params = build_sichtbarkeits_filter_query(
        base_query,
        sichtbare_abteilungen,
        [],
        table_alias='T'
    )
    
    query += ''' ORDER BY BM.Datum DESC
        LIMIT ?'''
    params.append(limit)
    
    return conn.execute(query, params).fetchall()


def get_ersatzteil_statistiken(mitarbeiter_id, sichtbare_abteilungen, is_admin, conn):
    """
    Ermittelt Ersatzteil-Statistiken
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        is_admin: Ob Benutzer Admin ist
        conn: Datenbankverbindung
        
    Returns:
        Dictionary mit Statistiken und Warnungen
    """
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
    
    return {
        'gesamt': ersatzteil_gesamt,
        'warnungen': len(ersatzteil_warnungen),
        'kategorien': [row_to_dict(row) for row in kategorie_stats],
        'warnungen_liste': [row_to_dict(row) for row in ersatzteil_warnungen]
    }

