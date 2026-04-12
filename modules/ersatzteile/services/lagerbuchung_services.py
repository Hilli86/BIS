"""
Lagerbuchung Services
Business-Logik für Lagerbuchungen
"""


def validate_lagerbuchung(ersatzteil_id, typ, menge, aktueller_bestand, conn):
    """
    Validiert eine Lagerbuchung
    
    Args:
        ersatzteil_id: ID des Ersatzteils
        typ: Typ der Buchung ('Eingang', 'Ausgang', 'Inventur')
        menge: Menge der Buchung (bei Inventur: neuer Bestand)
        aktueller_bestand: Aktueller Bestand des Ersatzteils
        conn: Datenbankverbindung
        
    Returns:
        Tuple (is_valid: bool, error_message: str, neuer_bestand: int, buchungsmenge: int)
    """
    if typ == 'Inventur':
        # Bei Inventur ist auch 0 erlaubt, aber nicht negativ
        if menge < 0:
            return False, 'Bestand kann nicht negativ sein.', None, None
        neuer_bestand = menge
        buchungsmenge = menge  # Bei Inventur ist die Buchungsmenge der neue Bestand
    elif typ == 'Eingang':
        if menge <= 0:
            return False, 'Menge muss größer als 0 sein.', None, None
        neuer_bestand = aktueller_bestand + menge
        buchungsmenge = menge
    elif typ == 'Ausgang':
        if menge <= 0:
            return False, 'Menge muss größer als 0 sein.', None, None
        if aktueller_bestand < menge:
            return False, f'Nicht genug Bestand verfügbar! Verfügbar: {aktueller_bestand}, benötigt: {menge}.', None, None
        neuer_bestand = aktueller_bestand - menge
        buchungsmenge = menge
    else:
        return False, f'Unbekannter Buchungstyp: {typ}', None, None
    
    return True, None, neuer_bestand, buchungsmenge


def create_lagerbuchung(ersatzteil_id, typ, menge, grund, mitarbeiter_id, conn,
                        thema_id=None, kostenstelle_id=None, bemerkung=None,
                        preis=None, waehrung=None, wartungsdurchfuehrung_id=None):
    """
    Erstellt eine Lagerbuchung und aktualisiert den Bestand
    
    Args:
        ersatzteil_id: ID des Ersatzteils
        typ: Typ der Buchung ('Eingang', 'Ausgang', 'Inventur')
        menge: Menge der Buchung
        grund: Grund der Buchung
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        thema_id: Optional: Thema-ID
        kostenstelle_id: Optional: Kostenstellen-ID
        wartungsdurchfuehrung_id: Optional: Wartungsdurchführung-ID
        bemerkung: Optional: Bemerkung
        preis: Optional: Preis
        waehrung: Optional: Währung
        
    Returns:
        Tuple (success: bool, message: str, neuer_bestand: int)
    """
    # Ersatzteil-Daten laden
    ersatzteil = conn.execute('''
        SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil 
        WHERE ID = ? AND Gelöscht = 0
    ''', (ersatzteil_id,)).fetchone()
    
    if not ersatzteil:
        return False, 'Ersatzteil nicht gefunden.', None
    
    aktueller_bestand = ersatzteil['AktuellerBestand'] or 0
    artikel_preis = preis if preis is not None else ersatzteil['Preis']
    artikel_waehrung = waehrung if waehrung else (ersatzteil['Waehrung'] or 'EUR')
    
    # Validierung
    is_valid, error_message, neuer_bestand, buchungsmenge = validate_lagerbuchung(
        ersatzteil_id, typ, menge, aktueller_bestand, conn
    )
    
    if not is_valid:
        return False, error_message, None
    
    # Lagerbuchung erstellen
    conn.execute('''
        INSERT INTO Lagerbuchung (
            ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
            WartungsdurchfuehrungID, VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
    ''', (
        ersatzteil_id, typ, buchungsmenge, grund, thema_id, kostenstelle_id,
        wartungsdurchfuehrung_id, mitarbeiter_id, bemerkung, artikel_preis, artikel_waehrung
    ))
    
    # Bestand aktualisieren
    conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', 
                 (neuer_bestand, ersatzteil_id))
    
    return True, f'Lagerbuchung erfolgreich durchgeführt. Neuer Bestand: {neuer_bestand}', neuer_bestand


def create_inventur_buchung(ersatzteil_id, neuer_bestand, mitarbeiter_id, conn, bemerkung=None):
    """
    Erstellt eine Inventur-Buchung
    
    Args:
        ersatzteil_id: ID des Ersatzteils
        neuer_bestand: Neuer Bestand (wird direkt gesetzt)
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung
        bemerkung: Optional: Bemerkung
        
    Returns:
        Tuple (success: bool, message: str)
    """
    # Ersatzteil-Daten laden
    ersatzteil = conn.execute('''
        SELECT AktuellerBestand, Preis, Waehrung FROM Ersatzteil 
        WHERE ID = ? AND Gelöscht = 0
    ''', (ersatzteil_id,)).fetchone()
    
    if not ersatzteil:
        return False, 'Ersatzteil nicht gefunden.'
    
    if neuer_bestand < 0:
        return False, 'Bestand kann nicht negativ sein.'
    
    aktueller_bestand = ersatzteil['AktuellerBestand'] or 0
    artikel_preis = ersatzteil['Preis']
    artikel_waehrung = ersatzteil['Waehrung'] or 'EUR'
    
    # Inventur-Buchung erstellen
    inventur_bemerkung = bemerkung or f'Inventur: Bestand von {aktueller_bestand} auf {neuer_bestand} geändert'
    
    conn.execute('''
        INSERT INTO Lagerbuchung (
            ErsatzteilID, Typ, Menge, Grund, ThemaID, KostenstelleID,
            VerwendetVonID, Bemerkung, Preis, Waehrung, Buchungsdatum
        ) VALUES (?, 'Inventur', ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
    ''', (
        ersatzteil_id, neuer_bestand, 'Inventur aus Inventurliste', None, None,
        mitarbeiter_id, inventur_bemerkung, artikel_preis, artikel_waehrung
    ))
    
    # Bestand aktualisieren
    conn.execute('UPDATE Ersatzteil SET AktuellerBestand = ? WHERE ID = ?', 
                 (neuer_bestand, ersatzteil_id))
    
    return True, f'Inventur-Buchung erfolgreich durchgeführt. Neuer Bestand: {neuer_bestand}'


def rueckbuche_lager_fuer_geloeschtes_thema(thema_id, mitarbeiter_id, conn):
    """
    Erstellt Gegenbuchungen für alle Lagerbuchungen mit diesem Thema (vor Soft-Delete).
    Ausgang wird mit Eingang, Eingang mit Ausgang ausgeglichen. Inventur-Zeilen werden übersprungen.

    Returns:
        Tuple (success: bool, message: str)
    """
    rows = conn.execute(
        '''
        SELECT ID, ErsatzteilID, Typ, Menge, KostenstelleID, Preis, Waehrung
        FROM Lagerbuchung
        WHERE ThemaID = ?
        ORDER BY ID ASC
        ''',
        (thema_id,),
    ).fetchall()

    if not rows:
        return True, None

    skipped_inventur = 0
    gegengebucht = 0
    for row in rows:
        typ = row['Typ']
        et_id = row['ErsatzteilID']
        menge = row['Menge']
        ks_id = row['KostenstelleID']
        preis = row['Preis']
        waehrung = row['Waehrung']
        buchung_ref = row['ID']
        grund = f'Rückbuchung nach Löschen von Thema #{thema_id}'
        bem = f'Gegenbuchung zu Lagerbuchung #{buchung_ref}'

        if typ == 'Ausgang':
            ok, msg, _ = create_lagerbuchung(
                ersatzteil_id=et_id,
                typ='Eingang',
                menge=menge,
                grund=grund,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                thema_id=None,
                kostenstelle_id=ks_id,
                bemerkung=bem,
                preis=preis,
                waehrung=waehrung,
            )
            if not ok:
                return False, msg
            gegengebucht += 1
        elif typ == 'Eingang':
            ok, msg, _ = create_lagerbuchung(
                ersatzteil_id=et_id,
                typ='Ausgang',
                menge=menge,
                grund=grund,
                mitarbeiter_id=mitarbeiter_id,
                conn=conn,
                thema_id=None,
                kostenstelle_id=ks_id,
                bemerkung=bem,
                preis=preis,
                waehrung=waehrung,
            )
            if not ok:
                return False, msg
            gegengebucht += 1
        else:
            skipped_inventur += 1

    if gegengebucht == 0:
        if skipped_inventur:
            return (
                True,
                'Es liegen nur Inventur-Buchungen zu diesem Thema vor; der Lagerbestand wurde nicht geändert.',
            )
        return True, None

    parts = ['Ersatzteile wurden zum Lager zurückgebucht.']
    if skipped_inventur:
        parts.append(
            f'Hinweis: {skipped_inventur} Buchung(en) vom Typ Inventur wurden nicht automatisch angepasst.'
        )
    return True, ' '.join(parts)

