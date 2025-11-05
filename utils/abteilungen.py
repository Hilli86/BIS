"""
Abteilungs-Utilities
Hilfsfunktionen für hierarchische Abteilungen
"""


def get_untergeordnete_abteilungen(abteilung_id, conn):
    """
    Ermittelt alle untergeordneten Abteilungen (rekursiv) für eine gegebene Abteilung.
    Gibt eine Liste mit IDs zurück (inkl. der übergebenen Abteilung selbst).
    """
    abteilungen = [abteilung_id]
    
    # Alle direkten Unterabteilungen finden
    unterabteilungen = conn.execute(
        'SELECT ID FROM Abteilung WHERE ParentAbteilungID = ? AND Aktiv = 1',
        (abteilung_id,)
    ).fetchall()
    
    # Rekursiv alle Unterabteilungen dieser Unterabteilungen finden
    for unter in unterabteilungen:
        abteilungen.extend(get_untergeordnete_abteilungen(unter['ID'], conn))
    
    return abteilungen


def get_mitarbeiter_abteilungen(mitarbeiter_id, conn):
    """
    Gibt alle Abteilungen eines Mitarbeiters zurück (primär + zusätzliche).
    """
    # Primärabteilung
    primaer = conn.execute(
        'SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?',
        (mitarbeiter_id,)
    ).fetchone()
    
    abteilungen = []
    if primaer and primaer['PrimaerAbteilungID']:
        abteilungen.append(primaer['PrimaerAbteilungID'])
    
    # Zusätzliche Abteilungen
    zusaetzliche = conn.execute(
        'SELECT AbteilungID FROM MitarbeiterAbteilung WHERE MitarbeiterID = ?',
        (mitarbeiter_id,)
    ).fetchall()
    
    abteilungen.extend([z['AbteilungID'] for z in zusaetzliche])
    
    return list(set(abteilungen))  # Duplikate entfernen


def get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn):
    """
    Ermittelt alle Abteilungen, die ein Mitarbeiter sehen darf:
    - Seine eigenen Abteilungen
    - Alle untergeordneten Abteilungen davon
    """
    mitarbeiter_abteilungen = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    
    alle_sichtbaren = []
    for abt_id in mitarbeiter_abteilungen:
        alle_sichtbaren.extend(get_untergeordnete_abteilungen(abt_id, conn))
    
    return list(set(alle_sichtbaren))  # Duplikate entfernen


def get_direkte_unterabteilungen(abteilung_id, conn):
    """
    Gibt nur die DIREKT untergeordneten Abteilungen zurück (nicht rekursiv).
    """
    unterabteilungen = conn.execute(
        '''SELECT ID, Bezeichnung, ParentAbteilungID 
           FROM Abteilung 
           WHERE ParentAbteilungID = ? AND Aktiv = 1
           ORDER BY Sortierung, Bezeichnung''',
        (abteilung_id,)
    ).fetchall()
    
    return unterabteilungen


def get_auswaehlbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn):
    """
    Ermittelt alle Abteilungen, die ein Mitarbeiter für Sichtbarkeitsauswahl sehen kann:
    - Seine eigenen Abteilungen (primär + zusätzlich)
    - Jeweils die direkt untergeordneten Abteilungen
    
    Rückgabe: Dictionary mit Gruppierung nach Parent-Abteilung
    """
    mitarbeiter_abteilungen_ids = get_mitarbeiter_abteilungen(mitarbeiter_id, conn)
    
    # Abteilungs-Details laden
    if not mitarbeiter_abteilungen_ids:
        return []
    
    placeholders = ','.join(['?'] * len(mitarbeiter_abteilungen_ids))
    eigene_abteilungen = conn.execute(f'''
        SELECT ID, Bezeichnung, ParentAbteilungID
        FROM Abteilung
        WHERE ID IN ({placeholders}) AND Aktiv = 1
        ORDER BY Sortierung, Bezeichnung
    ''', mitarbeiter_abteilungen_ids).fetchall()
    
    # Gruppierte Struktur erstellen
    result = []
    
    for abt in eigene_abteilungen:
        gruppe = {
            'parent': abt,
            'children': get_direkte_unterabteilungen(abt['ID'], conn)
        }
        result.append(gruppe)
    
    return result
