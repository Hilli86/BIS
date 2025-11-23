"""
Schichtbuch Services
Business-Logik für Schichtbuch-Funktionen
"""

from utils import get_sichtbare_abteilungen_fuer_mitarbeiter
from utils.helpers import build_sichtbarkeits_filter_query


def build_themen_query(sichtbare_abteilungen, bereich_filter=None, gewerk_filter=None, 
                       status_filter_list=None, q_filter=None, limit=None, offset=None):
    """
    Baut die SQL-Query für Themenliste auf
    
    Args:
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        bereich_filter: Optionaler Bereichs-Filter
        gewerk_filter: Optionaler Gewerks-Filter
        status_filter_list: Optionaler Status-Filter (Liste)
        q_filter: Optionaler Such-Filter
        limit: Optionales Limit
        offset: Optionales Offset
        
    Returns:
        Tuple (query, params)
    """
    query = '''
        SELECT 
            t.ID,
            b.Bezeichnung AS Bereich,
            g.Bezeichnung AS Gewerk,
            s.Bezeichnung AS Status,
            s.Farbe AS Farbe,
            abt.Bezeichnung AS Abteilung,
            COALESCE(MAX(bm.Datum), '1900-01-01') AS LetzteBemerkungDatum,
            COALESCE(MAX(bm.MitarbeiterID), 0) AS LetzteMitarbeiterID,
            COALESCE(MAX(m.Vorname), '') AS LetzteMitarbeiterVorname,
            COALESCE(MAX(m.Nachname), '') AS LetzteMitarbeiterNachname,
            COALESCE(MAX(ta.Bezeichnung), '') AS LetzteTatigkeit
        FROM SchichtbuchThema t
        JOIN Gewerke g ON t.GewerkID = g.ID
        JOIN Bereich b ON g.BereichID = b.ID
        JOIN Status s ON t.StatusID = s.ID
        LEFT JOIN Abteilung abt ON t.ErstellerAbteilungID = abt.ID
        LEFT JOIN SchichtbuchBemerkungen bm ON bm.ThemaID = t.ID AND bm.Gelöscht = 0
        LEFT JOIN Mitarbeiter m ON bm.MitarbeiterID = m.ID
        LEFT JOIN Taetigkeit ta ON bm.TaetigkeitID = ta.ID
        WHERE t.Gelöscht = 0
    '''
    params = []
    
    # Sichtbarkeitsfilter
    query, params = build_sichtbarkeits_filter_query(
        query,
        sichtbare_abteilungen,
        params,
        table_alias='t'
    )
    
    # Filter anwenden
    if bereich_filter:
        query += ' AND b.Bezeichnung = ?'
        params.append(bereich_filter)
    
    if gewerk_filter:
        query += ' AND g.Bezeichnung = ?'
        params.append(gewerk_filter)
    
    if status_filter_list:
        placeholders = ','.join(['?'] * len(status_filter_list))
        query += f' AND s.Bezeichnung IN ({placeholders})'
        params.extend(status_filter_list)
    
    if q_filter:
        query += ' AND EXISTS (SELECT 1 FROM SchichtbuchBemerkungen b2 WHERE b2.ThemaID = t.ID AND b2.Gelöscht = 0 AND b2.Bemerkung LIKE ? )'
        params.append(f'%{q_filter}%')
    
    query += ' GROUP BY t.ID'
    
    # ORDER BY
    query += ''' ORDER BY 
                    LetzteBemerkungDatum DESC,
                    LetzteMitarbeiterNachname ASC,
                    LetzteMitarbeiterVorname ASC,
                    Bereich ASC,
                    Gewerk ASC,
                    LetzteTatigkeit ASC,
                    Status ASC'''
    
    # LIMIT und OFFSET
    if limit is not None:
        query += ' LIMIT ?'
        params.append(limit)
        if offset is not None:
            query += ' OFFSET ?'
            params.append(offset)
    
    return query, params


def get_bemerkungen_fuer_themen(thema_ids, conn):
    """
    Lädt Bemerkungen für mehrere Themen in einer Query
    
    Args:
        thema_ids: Liste von Thema-IDs
        conn: Datenbankverbindung
        
    Returns:
        Dictionary mit ThemaID als Key und Liste von Bemerkungen als Value
    """
    if not thema_ids:
        return {}
    
    placeholders = ','.join(['?'] * len(thema_ids))
    bemerkungen = conn.execute(f'''
        SELECT 
            b.ThemaID,
            b.Datum,
            b.Bemerkung,
            m.Vorname,
            m.Nachname,
            t.Bezeichnung AS Taetigkeit
        FROM SchichtbuchBemerkungen b
        JOIN Mitarbeiter m ON b.MitarbeiterID = m.ID
        LEFT JOIN Taetigkeit t ON b.TaetigkeitID = t.ID
        WHERE b.Gelöscht = 0 AND b.ThemaID IN ({placeholders})
        ORDER BY b.ThemaID DESC, b.Datum DESC
    ''', thema_ids).fetchall()
    
    # Nach Thema gruppieren
    bemerk_dict = {}
    for b in bemerkungen:
        bemerk_dict.setdefault(b['ThemaID'], []).append(b)
    
    return bemerk_dict
