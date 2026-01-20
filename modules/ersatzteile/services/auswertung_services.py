"""
Auswertungs Services
Business-Logik für Auswertungen (Bestellungen und Ersatzteilwert)
"""

from datetime import datetime
from utils.abteilungen import get_untergeordnete_abteilungen


def get_bestellungen_auswertung(abteilung_ids, lieferant_id, datum_von, datum_bis, conn, is_admin=False, sichtbare_abteilungen=None):
    """
    Berechnet Bestellungsstatistiken für erledigte Bestellungen
    
    Args:
        abteilung_ids: Liste von Abteilungs-IDs (None = alle)
        lieferant_id: Lieferanten-ID (None = alle)
        datum_von: Startdatum (datetime)
        datum_bis: Enddatum (datetime)
        conn: Datenbankverbindung
        is_admin: Ob der Mitarbeiter Admin ist
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        
    Returns:
        Dictionary mit Statistiken:
        {
            'gesamt': {
                'anzahl': int,
                'summe_nach_waehrung': {waehrung: float, ...}
            },
            'nach_monat': [
                {
                    'jahr_monat': '2024-01',
                    'anzahl': int,
                    'summe_nach_waehrung': {waehrung: float, ...}
                },
                ...
            ],
            'durchschnitt': float
        }
    """
    # Basis-Query für Bestellungen mit Gruppierung nach Jahr/Monat
    # Zuerst Gesamtstatistik
    query_gesamt = '''
        SELECT 
            COUNT(DISTINCT b.ID) AS anzahl,
            bp.Waehrung,
            SUM(bp.Menge * COALESCE(bp.Preis, 0)) AS summe
        FROM Bestellung b
        LEFT JOIN BestellungPosition bp ON b.ID = bp.BestellungID
        WHERE b.Gelöscht = 0
        AND b.Status = 'Erledigt'
        AND b.BestelltAm IS NOT NULL
        AND DATE(b.BestelltAm) BETWEEN DATE(?) AND DATE(?)
    '''
    params_gesamt = [datum_von.strftime('%Y-%m-%d'), datum_bis.strftime('%Y-%m-%d')]
    
    # Abteilungs-Filter
    if abteilung_ids:
        placeholders = ','.join(['?'] * len(abteilung_ids))
        query_gesamt += f' AND b.ErstellerAbteilungID IN ({placeholders})'
        params_gesamt.extend(abteilung_ids)
    elif not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        query_gesamt += f'''
            AND EXISTS (
                SELECT 1 FROM BestellungSichtbarkeit bs
                WHERE bs.BestellungID = b.ID 
                AND bs.AbteilungID IN ({placeholders})
            )
        '''
        params_gesamt.extend(sichtbare_abteilungen)
    elif not is_admin:
        query_gesamt += ' AND 1=0'
    
    # Lieferant-Filter
    if lieferant_id:
        query_gesamt += ' AND b.LieferantID = ?'
        params_gesamt.append(lieferant_id)
    
    query_gesamt += ' GROUP BY bp.Waehrung'
    
    # Gesamtstatistik abrufen
    gesamt_rows = conn.execute(query_gesamt, params_gesamt).fetchall()
    gesamt_summen = {}
    anzahl_bestellungen = 0
    
    # Anzahl aus separater Query (da GROUP BY die Anzahl pro Währung gibt)
    query_anzahl = query_gesamt.replace('COUNT(DISTINCT b.ID) AS anzahl, bp.Waehrung, SUM(bp.Menge * COALESCE(bp.Preis, 0)) AS summe', 'COUNT(DISTINCT b.ID) AS anzahl').replace(' GROUP BY bp.Waehrung', '')
    anzahl_row = conn.execute(query_anzahl, params_gesamt).fetchone()
    anzahl_bestellungen = anzahl_row['anzahl'] if anzahl_row else 0
    
    for row in gesamt_rows:
        waehrung = row['Waehrung'] or 'EUR'
        summe = row['summe'] or 0
        gesamt_summen[waehrung] = summe
    
    # Monatsstatistik - Zuerst Anzahl pro Monat (ohne Währung)
    query_monat_anzahl = '''
        SELECT 
            strftime('%Y-%m', b.BestelltAm) AS jahr_monat,
            COUNT(DISTINCT b.ID) AS anzahl
        FROM Bestellung b
        WHERE b.Gelöscht = 0
        AND b.Status = 'Erledigt'
        AND b.BestelltAm IS NOT NULL
        AND strftime('%Y-%m', b.BestelltAm) IS NOT NULL
        AND DATE(b.BestelltAm) BETWEEN DATE(?) AND DATE(?)
    '''
    params_monat_anzahl = [datum_von.strftime('%Y-%m-%d'), datum_bis.strftime('%Y-%m-%d')]
    
    # Abteilungs-Filter
    if abteilung_ids:
        placeholders = ','.join(['?'] * len(abteilung_ids))
        query_monat_anzahl += f' AND b.ErstellerAbteilungID IN ({placeholders})'
        params_monat_anzahl.extend(abteilung_ids)
    elif not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        query_monat_anzahl += f'''
            AND EXISTS (
                SELECT 1 FROM BestellungSichtbarkeit bs
                WHERE bs.BestellungID = b.ID 
                AND bs.AbteilungID IN ({placeholders})
            )
        '''
        params_monat_anzahl.extend(sichtbare_abteilungen)
    elif not is_admin:
        query_monat_anzahl += ' AND 1=0'
    
    # Lieferant-Filter
    if lieferant_id:
        query_monat_anzahl += ' AND b.LieferantID = ?'
        params_monat_anzahl.append(lieferant_id)
    
    query_monat_anzahl += ' GROUP BY jahr_monat ORDER BY jahr_monat'
    
    # Monatsstatistik - Summen nach Währung
    query_monat_summen = '''
        SELECT 
            strftime('%Y-%m', b.BestelltAm) AS jahr_monat,
            bp.Waehrung,
            SUM(bp.Menge * COALESCE(bp.Preis, 0)) AS summe
        FROM Bestellung b
        LEFT JOIN BestellungPosition bp ON b.ID = bp.BestellungID
        WHERE b.Gelöscht = 0
        AND b.Status = 'Erledigt'
        AND b.BestelltAm IS NOT NULL
        AND strftime('%Y-%m', b.BestelltAm) IS NOT NULL
        AND DATE(b.BestelltAm) BETWEEN DATE(?) AND DATE(?)
    '''
    params_monat_summen = [datum_von.strftime('%Y-%m-%d'), datum_bis.strftime('%Y-%m-%d')]
    
    # Abteilungs-Filter
    if abteilung_ids:
        placeholders = ','.join(['?'] * len(abteilung_ids))
        query_monat_summen += f' AND b.ErstellerAbteilungID IN ({placeholders})'
        params_monat_summen.extend(abteilung_ids)
    elif not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        query_monat_summen += f'''
            AND EXISTS (
                SELECT 1 FROM BestellungSichtbarkeit bs
                WHERE bs.BestellungID = b.ID 
                AND bs.AbteilungID IN ({placeholders})
            )
        '''
        params_monat_summen.extend(sichtbare_abteilungen)
    elif not is_admin:
        query_monat_summen += ' AND 1=0'
    
    # Lieferant-Filter
    if lieferant_id:
        query_monat_summen += ' AND b.LieferantID = ?'
        params_monat_summen.append(lieferant_id)
    
    query_monat_summen += ' GROUP BY jahr_monat, bp.Waehrung ORDER BY jahr_monat'
    
    # Monatsstatistik nach Lieferant (Summen EUR)
    query_monat_lieferant = '''
        SELECT 
            strftime('%Y-%m', b.BestelltAm) AS jahr_monat,
            b.LieferantID,
            l.Name AS LieferantName,
            SUM(
                CASE 
                    WHEN bp.Waehrung IS NULL OR bp.Waehrung = 'EUR' THEN bp.Menge * COALESCE(bp.Preis, 0)
                    ELSE 0
                END
            ) AS summe_eur
        FROM Bestellung b
        LEFT JOIN BestellungPosition bp ON b.ID = bp.BestellungID
        LEFT JOIN Lieferant l ON b.LieferantID = l.ID
        WHERE b.Gelöscht = 0
        AND b.Status = 'Erledigt'
        AND b.BestelltAm IS NOT NULL
        AND strftime('%Y-%m', b.BestelltAm) IS NOT NULL
        AND DATE(b.BestelltAm) BETWEEN DATE(?) AND DATE(?)
    '''
    params_monat_lieferant = [datum_von.strftime('%Y-%m-%d'), datum_bis.strftime('%Y-%m-%d')]
    
    # Abteilungs-Filter
    if abteilung_ids:
        placeholders = ','.join(['?'] * len(abteilung_ids))
        query_monat_lieferant += f' AND b.ErstellerAbteilungID IN ({placeholders})'
        params_monat_lieferant.extend(abteilung_ids)
    elif not is_admin and sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        query_monat_lieferant += f'''
            AND EXISTS (
                SELECT 1 FROM BestellungSichtbarkeit bs
                WHERE bs.BestellungID = b.ID 
                AND bs.AbteilungID IN ({placeholders})
            )
        '''
        params_monat_lieferant.extend(sichtbare_abteilungen)
    elif not is_admin:
        query_monat_lieferant += ' AND 1=0'
    
    # Lieferant-Filter
    if lieferant_id:
        query_monat_lieferant += ' AND b.LieferantID = ?'
        params_monat_lieferant.append(lieferant_id)
    
    query_monat_lieferant += ' GROUP BY jahr_monat, b.LieferantID, l.Name ORDER BY jahr_monat, l.Name'
    
    # Monatsstatistik abrufen
    monats_anzahl_rows = conn.execute(query_monat_anzahl, params_monat_anzahl).fetchall()
    monats_summen_rows = conn.execute(query_monat_summen, params_monat_summen).fetchall()
    monats_lieferant_rows = conn.execute(query_monat_lieferant, params_monat_lieferant).fetchall()
    
    monats_daten = {}
    monats_lieferanten = {}
    
    # Anzahl pro Monat speichern
    for row in monats_anzahl_rows:
        jahr_monat = row['jahr_monat']
        if jahr_monat and str(jahr_monat).strip():  # Nur wenn jahr_monat nicht None/leer ist
            jahr_monat_str = str(jahr_monat).strip()
            monats_daten[jahr_monat_str] = {
                'anzahl': row['anzahl'] or 0,
                'summen': {}
            }
    
    # Summen pro Monat/Währung speichern
    for row in monats_summen_rows:
        jahr_monat = row['jahr_monat']
        if not jahr_monat or not str(jahr_monat).strip():  # Überspringe wenn None/leer
            continue
        jahr_monat_str = str(jahr_monat).strip()
        waehrung = row['Waehrung'] or 'EUR'
        summe = row['summe'] or 0
        
        if jahr_monat_str not in monats_daten:
            monats_daten[jahr_monat_str] = {
                'anzahl': 0,
                'summen': {}
            }
        
        monats_daten[jahr_monat_str]['summen'][waehrung] = summe
    
    # Lieferanten-Summen pro Monat speichern
    for row in monats_lieferant_rows:
        jahr_monat = row['jahr_monat']
        if not jahr_monat or not str(jahr_monat).strip():
            continue
        jahr_monat_str = str(jahr_monat).strip()
        lieferant_name = row['LieferantName'] or 'Kein Lieferant'
        summe_eur = row['summe_eur'] or 0
        
        if jahr_monat_str not in monats_lieferanten:
            monats_lieferanten[jahr_monat_str] = []
        
        monats_lieferanten[jahr_monat_str].append({
            'lieferant_id': row['LieferantID'],
            'lieferant_name': lieferant_name,
            'summe_eur': summe_eur
        })
    
    # Monats-Daten formatieren
    nach_monat = []
    for jahr_monat in sorted(monats_daten.keys()):
        if jahr_monat and str(jahr_monat).strip():  # Nur wenn jahr_monat nicht None/leer ist
            nach_monat.append({
                'jahr_monat': str(jahr_monat).strip(),
                'anzahl': monats_daten[jahr_monat]['anzahl'],
                'summe_nach_waehrung': monats_daten[jahr_monat]['summen'],
                'lieferanten': sorted(
                    monats_lieferanten.get(jahr_monat, []),
                    key=lambda x: x['summe_eur'],
                    reverse=True
                )
            })
    
    # Durchschnitt berechnen (nur EUR für Durchschnitt)
    durchschnitt = 0
    if anzahl_bestellungen > 0 and 'EUR' in gesamt_summen:
        durchschnitt = gesamt_summen['EUR'] / anzahl_bestellungen
    
    return {
        'gesamt': {
            'anzahl': anzahl_bestellungen,
            'summe_nach_waehrung': gesamt_summen
        },
        'nach_monat': nach_monat,
        'durchschnitt': durchschnitt
    }


def get_ersatzteilwert_auswertung(abteilung_ids, lieferant_id, conn, mitarbeiter_id, is_admin=False, sichtbare_abteilungen=None):
    """
    Berechnet Ersatzteilwert-Statistiken (Lagerwert)
    
    Args:
        abteilung_ids: Liste von Abteilungs-IDs (None = alle)
        lieferant_id: Lieferanten-ID (None = alle)
        conn: Datenbankverbindung
        mitarbeiter_id: ID des Mitarbeiters (für Berechtigungen)
        is_admin: Ob der Mitarbeiter Admin ist
        sichtbare_abteilungen: Liste von sichtbaren Abteilungs-IDs
        
    Returns:
        Dictionary mit Lagerwert-Statistiken:
        {
            'gesamt': {
                'lagerwert_nach_waehrung': {waehrung: float, ...},
                'anzahl_artikel': int,
                'anzahl_mit_bestand': int
            },
            'nach_waehrung': {waehrung: float, ...},
            'nach_lieferant': [...]  # Optional wenn Filter gesetzt
        }
    """
    # Basis-Query für Ersatzteile
    query = '''
        SELECT 
            e.ID,
            e.AktuellerBestand,
            e.Preis,
            e.Waehrung,
            e.LieferantID,
            e.KategorieID,
            l.Name AS LieferantName,
            k.Bezeichnung AS KategorieName
        FROM Ersatzteil e
        LEFT JOIN Lieferant l ON e.LieferantID = l.ID
        LEFT JOIN ErsatzteilKategorie k ON e.KategorieID = k.ID
        WHERE e.Gelöscht = 0 AND e.Aktiv = 1
    '''
    params = []
    
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
            query += ' AND e.ErstelltVonID = ?'
            params.append(mitarbeiter_id)
    
    # Abteilungs-Filter (über ErsatzteilAbteilungZugriff)
    if abteilung_ids:
        placeholders = ','.join(['?'] * len(abteilung_ids))
        query += f'''
            AND e.ID IN (
                SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                WHERE AbteilungID IN ({placeholders})
            )
        '''
        params.extend(abteilung_ids)
    
    # Lieferant-Filter
    if lieferant_id:
        query += ' AND e.LieferantID = ?'
        params.append(lieferant_id)
    
    ersatzteile = conn.execute(query, params).fetchall()
    
    # Daten verarbeiten
    lagerwert_nach_waehrung = {}
    anzahl_artikel = len(ersatzteile)
    anzahl_mit_bestand = 0
    nach_lieferant = {}
    nach_kategorie = {}
    
    for ersatzteil in ersatzteile:
        bestand = ersatzteil['AktuellerBestand'] or 0
        preis = ersatzteil['Preis'] or 0
        waehrung = ersatzteil['Waehrung'] or 'EUR'
        
        if bestand > 0:
            anzahl_mit_bestand += 1
        
        lagerwert = bestand * preis
        
        # Nach Währung summieren
        if waehrung not in lagerwert_nach_waehrung:
            lagerwert_nach_waehrung[waehrung] = 0
        lagerwert_nach_waehrung[waehrung] += lagerwert
        
        # Nach Lieferant summieren (wenn Filter gesetzt oder für Übersicht)
        if lieferant_id or True:  # Immer nach Lieferant gruppieren
            lieferant_id_val = ersatzteil['LieferantID']
            lieferant_name = ersatzteil['LieferantName'] or 'Kein Lieferant'
            
            if lieferant_id_val not in nach_lieferant:
                nach_lieferant[lieferant_id_val] = {
                    'lieferant_id': lieferant_id_val,
                    'lieferant_name': lieferant_name,
                    'lagerwert_nach_waehrung': {},
                    'anzahl_artikel': 0
                }
            
            nach_lieferant[lieferant_id_val]['anzahl_artikel'] += 1
            
            if waehrung not in nach_lieferant[lieferant_id_val]['lagerwert_nach_waehrung']:
                nach_lieferant[lieferant_id_val]['lagerwert_nach_waehrung'][waehrung] = 0
            nach_lieferant[lieferant_id_val]['lagerwert_nach_waehrung'][waehrung] += lagerwert
        
        # Nach Kategorie summieren
        kategorie_id_val = ersatzteil['KategorieID']
        kategorie_name = ersatzteil['KategorieName'] or 'Keine Kategorie'
        
        if kategorie_id_val not in nach_kategorie:
            nach_kategorie[kategorie_id_val] = {
                'kategorie_id': kategorie_id_val,
                'kategorie_name': kategorie_name,
                'lagerwert_nach_waehrung': {},
                'anzahl_artikel': 0
            }
        
        nach_kategorie[kategorie_id_val]['anzahl_artikel'] += 1
        
        if waehrung not in nach_kategorie[kategorie_id_val]['lagerwert_nach_waehrung']:
            nach_kategorie[kategorie_id_val]['lagerwert_nach_waehrung'][waehrung] = 0
        nach_kategorie[kategorie_id_val]['lagerwert_nach_waehrung'][waehrung] += lagerwert
    
    # Nach Lieferant sortieren nach Lagerwert (EUR bevorzugt)
    nach_lieferant_liste = []
    for lieferant_data in nach_lieferant.values():
        # Sortierwert: EUR-Wert oder erster Wert
        sort_wert = lieferant_data['lagerwert_nach_waehrung'].get('EUR', 0)
        if sort_wert == 0 and lieferant_data['lagerwert_nach_waehrung']:
            sort_wert = list(lieferant_data['lagerwert_nach_waehrung'].values())[0]
        nach_lieferant_liste.append((sort_wert, lieferant_data))
    
    nach_lieferant_liste.sort(reverse=True, key=lambda x: x[0])
    nach_lieferant_final = [item[1] for item in nach_lieferant_liste]
    
    # Nach Kategorie sortieren nach Lagerwert (EUR bevorzugt)
    nach_kategorie_liste = []
    for kategorie_data in nach_kategorie.values():
        # Sortierwert: EUR-Wert oder erster Wert
        sort_wert = kategorie_data['lagerwert_nach_waehrung'].get('EUR', 0)
        if sort_wert == 0 and kategorie_data['lagerwert_nach_waehrung']:
            sort_wert = list(kategorie_data['lagerwert_nach_waehrung'].values())[0]
        nach_kategorie_liste.append((sort_wert, kategorie_data))
    
    nach_kategorie_liste.sort(reverse=True, key=lambda x: x[0])
    nach_kategorie_final = [item[1] for item in nach_kategorie_liste]
    
    return {
        'gesamt': {
            'lagerwert_nach_waehrung': lagerwert_nach_waehrung,
            'anzahl_artikel': anzahl_artikel,
            'anzahl_mit_bestand': anzahl_mit_bestand
        },
        'nach_waehrung': lagerwert_nach_waehrung,
        'nach_lieferant': nach_lieferant_final,
        'nach_kategorie': nach_kategorie_final
    }


def get_abteilungen_fuer_filter(mitarbeiter_id, conn, is_admin=False):
    """
    Lädt alle Abteilungen hierarchisch strukturiert für Filter-Dropdown
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        is_admin: Ob der Mitarbeiter Admin ist
        
    Returns:
        Liste von Abteilungen mit hierarchischer Struktur:
        [
            {
                'id': int,
                'bezeichnung': str,
                'level': int,  # 0 = Top-Level, 1 = Unterabteilung, etc.
                'parent_id': int or None
            },
            ...
        ]
    """
    from utils.abteilungen import get_alle_unterabteilungen_rekursiv
    
    # Top-Level-Abteilungen laden
    top_level = conn.execute('''
        SELECT ID, Bezeichnung, ParentAbteilungID
        FROM Abteilung
        WHERE ParentAbteilungID IS NULL AND Aktiv = 1
        ORDER BY Sortierung, Bezeichnung
    ''').fetchall()
    
    result = []
    
    for abt in top_level:
        # Top-Level hinzufügen
        result.append({
            'id': abt['ID'],
            'bezeichnung': abt['Bezeichnung'],
            'level': 0,
            'parent_id': None
        })
        
        # Unterabteilungen rekursiv hinzufügen
        unterabteilungen = get_alle_unterabteilungen_rekursiv(abt['ID'], conn)
        for unter in unterabteilungen:
            result.append({
                'id': unter['ID'],
                'bezeichnung': unter['Bezeichnung'],
                'level': unter['level'] + 1,  # +1 weil Top-Level = 0
                'parent_id': unter['ParentAbteilungID']
            })
    
    return result
