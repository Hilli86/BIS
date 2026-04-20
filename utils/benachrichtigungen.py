"""
Benachrichtigungs-Utilities
Funktionen zum Erstellen und Verwalten von Benachrichtigungen
"""

import json
import logging
from datetime import datetime
from utils import get_db_connection
from utils.abteilungen import get_sichtbare_abteilungen_fuer_mitarbeiter

# Logger für Benachrichtigungen
logger = logging.getLogger(__name__)


def _int_abteilung_set(ids):
    """Abteilungs-IDs als int (Schnittmengen); vermeidet leere Schnitte durch Typ-Mischung (int/str)."""
    out = set()
    if not ids:
        return out
    for x in ids:
        if x is None:
            continue
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _norm_modul_aktion(modul, aktion):
    """Einheitliche Schlüssel für Abgleich mit BenachrichtigungEinstellung (Profil kann Abweichungen haben)."""
    m = (modul or "").strip().lower()
    a = (aktion or "").strip().lower()
    return m, a


def get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, abteilung_id=None, conn=None):
    """
    Prüft ob eine Benachrichtigung für einen Mitarbeiter aktiviert ist.
    
    Logik:
    - Wenn abteilung_id gesetzt ist: Prüfe zuerst spezifische Einstellung (mit Abteilung)
      - Wenn gefunden und Aktiv=0: return False
      - Wenn gefunden und Aktiv=1: return True
      - Wenn nicht gefunden: Prüfe allgemeine Einstellung (ohne Abteilung)
    - Wenn abteilung_id None ist: Prüfe nur allgemeine Einstellung
    - Wenn keine Einstellung gefunden: return False (Standard: deaktiviert)
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        modul: Modul (z.B. 'schichtbuch', 'bestellwesen')
        aktion: Aktion (z.B. 'neues_thema', 'neue_bemerkung')
        abteilung_id: AbteilungID (None = alle Abteilungen)
        conn: Datenbankverbindung (optional)
    
    Returns:
        True wenn Benachrichtigung aktiviert ist, False sonst
    """
    if conn is None:
        with get_db_connection() as conn:
            return get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, abteilung_id, conn)

    modul_n, aktion_n = _norm_modul_aktion(modul, aktion)

    # Wenn abteilung_id gesetzt ist: Prüfe zuerst spezifische Einstellung (mit Abteilung)
    if abteilung_id is not None:
        einstellung = conn.execute('''
            SELECT Aktiv FROM BenachrichtigungEinstellung
            WHERE MitarbeiterID = ?
              AND lower(trim(Modul)) = ?
              AND lower(trim(Aktion)) = ?
              AND AbteilungID = ?
        ''', (mitarbeiter_id, modul_n, aktion_n, abteilung_id)).fetchone()
        if einstellung:
            aktiv = bool(einstellung['Aktiv'])
            logger.debug(f"Benachrichtigungseinstellung gefunden (spezifisch): MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, AbteilungID={abteilung_id}, Aktiv={aktiv}")
            return aktiv
    
    # Prüfe allgemeine Einstellung (alle Abteilungen)
    einstellung = conn.execute('''
        SELECT Aktiv FROM BenachrichtigungEinstellung
        WHERE MitarbeiterID = ?
          AND lower(trim(Modul)) = ?
          AND lower(trim(Aktion)) = ?
          AND AbteilungID IS NULL
    ''', (mitarbeiter_id, modul_n, aktion_n)).fetchone()
    if einstellung:
        aktiv = bool(einstellung['Aktiv'])
        logger.debug(f"Benachrichtigungseinstellung gefunden (allgemein): MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, Aktiv={aktiv}")
        return aktiv
    
    # Standard: Benachrichtigung ist deaktiviert (wenn keine Einstellung vorhanden)
    logger.debug(f"Keine Benachrichtigungseinstellung gefunden, verwende Standard (deaktiviert): MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, AbteilungID={abteilung_id}")
    return False


def get_aktive_benachrichtigungskanaele(mitarbeiter_id, conn=None):
    """
    Gibt alle aktiven Benachrichtigungskanäle für einen Mitarbeiter zurück.
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung (optional)
    
    Returns:
        Liste von KanalTypen (z.B. ['app', 'mail'])
    """
    if conn is None:
        with get_db_connection() as conn:
            return get_aktive_benachrichtigungskanaele(mitarbeiter_id, conn)
    
    kanale = conn.execute('''
        SELECT KanalTyp FROM BenachrichtigungKanal
        WHERE MitarbeiterID = ? AND Aktiv = 1
    ''', (mitarbeiter_id,)).fetchall()
    
    return [k['KanalTyp'] for k in kanale] if kanale else []  # Standard: keine Kanäle


def abteilung_ids_empfaenger_in_sichtbarkeit(mitarbeiter_id, sichtbare_abteilungen, conn):
    """
    Abteilungs-IDs aus der Thema-Sichtbarkeit, für die der Mitarbeiter „sichtbar“ ist
    (gleiche Semantik wie check_thema_berechtigung: Schnitt mit
    get_sichtbare_abteilungen_fuer_mitarbeiter inkl. Unterabteilungen).
    Reihenfolge: Primär falls im Schnitt, dann MitarbeiterAbteilung, sonst restliche Schnitt-IDs.
    """
    if not sichtbare_abteilungen:
        return []
    sicht = _int_abteilung_set(sichtbare_abteilungen)
    emp = _int_abteilung_set(get_sichtbare_abteilungen_fuer_mitarbeiter(mitarbeiter_id, conn))
    schnitt = emp & sicht
    if not schnitt:
        return []
    out = []
    m = conn.execute('SELECT PrimaerAbteilungID FROM Mitarbeiter WHERE ID = ?', (mitarbeiter_id,)).fetchone()
    pid = int(m['PrimaerAbteilungID']) if m and m['PrimaerAbteilungID'] is not None else None
    if pid is not None and pid in schnitt:
        out.append(pid)
    for r in conn.execute(
        'SELECT AbteilungID FROM MitarbeiterAbteilung WHERE MitarbeiterID = ?', (mitarbeiter_id,)
    ).fetchall():
        aid = int(r['AbteilungID']) if r['AbteilungID'] is not None else None
        if aid is not None and aid in schnitt and aid not in out:
            out.append(aid)
    for aid in sorted(schnitt):
        if aid not in out:
            out.append(aid)
    return out


def thema_sichtbare_abteilung_ids(thema_id, conn):
    """Alle AbteilungIDs aus SchichtbuchThemaSichtbarkeit für ein Thema."""
    rows = conn.execute(
        'SELECT AbteilungID FROM SchichtbuchThemaSichtbarkeit WHERE ThemaID = ?', (thema_id,)
    ).fetchall()
    return [r['AbteilungID'] for r in rows]


def benachrichtigung_einstellung_aktiv_fuer_empfaenger(mitarbeiter_id, modul, aktion, kandidaten_abteilung_ids, conn):
    """
    True, wenn für den Empfänger mindestens eine passende Einstellung aktiv ist:
    für jede Kandidaten-Abteilung (Schnitt Empfänger und Thema-Sichtbarkeit) wie
    get_benachrichtigungseinstellungen; zuletzt allgemein (AbteilungID NULL).
    """
    if not kandidaten_abteilung_ids:
        return get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, None, conn)
    seen = set()
    for aid in kandidaten_abteilung_ids:
        if aid is None or aid in seen:
            continue
        seen.add(aid)
        if get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, aid, conn):
            return True
    return get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, None, conn)


def erstelle_benachrichtigung_mit_filter(modul, aktion, mitarbeiter_id, titel, nachricht, 
                                        thema_id=None, bemerkung_id=None, abteilung_id=None, 
                                        zusatzdaten=None, conn=None, einstellung_abteilung_ids=None):
    """
    Erstellt eine Benachrichtigung mit Filterung basierend auf Einstellungen.
    
    Args:
        modul: Modul (z.B. 'schichtbuch', 'bestellwesen')
        aktion: Aktion (z.B. 'neues_thema', 'neue_bemerkung')
        mitarbeiter_id: ID des Mitarbeiters, der benachrichtigt werden soll
        titel: Titel der Benachrichtigung
        nachricht: Nachricht der Benachrichtigung
        thema_id: ThemaID (optional, für Schichtbuch)
        bemerkung_id: BemerkungID (optional, für Schichtbuch)
        abteilung_id: AbteilungID (optional, für gespeicherte Metadaten)
        zusatzdaten: Zusätzliche Daten als Dict (wird als JSON gespeichert)
        conn: Datenbankverbindung (optional)
        einstellung_abteilung_ids: Optional Liste Abteilungs-IDs für die Einstellungsprüfung
            (Schnitt Empfänger und Thema-Sichtbarkeit) statt nur abteilung_id (z.B. Ersteller).
    
    Returns:
        ID der erstellten Benachrichtigung oder None
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_mit_filter(
                modul, aktion, mitarbeiter_id, titel, nachricht,
                thema_id=thema_id,
                bemerkung_id=bemerkung_id,
                abteilung_id=abteilung_id,
                zusatzdaten=zusatzdaten,
                conn=conn,
                einstellung_abteilung_ids=einstellung_abteilung_ids,
            )

    if einstellung_abteilung_ids is not None:
        einstellung_ok = benachrichtigung_einstellung_aktiv_fuer_empfaenger(
            mitarbeiter_id, modul, aktion, einstellung_abteilung_ids, conn
        )
        abteilung_id_gespeichert = einstellung_abteilung_ids[0] if einstellung_abteilung_ids else abteilung_id
    else:
        einstellung_ok = get_benachrichtigungseinstellungen(mitarbeiter_id, modul, aktion, abteilung_id, conn)
        abteilung_id_gespeichert = abteilung_id

    if not einstellung_ok:
        logger.info(
            f"Benachrichtigung nicht erstellt: Einstellung deaktiviert - MitarbeiterID={mitarbeiter_id}, "
            f"Modul={modul}, Aktion={aktion}, AbteilungID={abteilung_id}, Kandidaten={einstellung_abteilung_ids}"
        )
        return None
    
    # Zusatzdaten als JSON speichern
    zusatzdaten_json = json.dumps(zusatzdaten) if zusatzdaten else None

    tid_insert = int(thema_id) if thema_id is not None else None
    if modul == 'schichtbuch' and (tid_insert is None or tid_insert == 0):
        logger.warning(f"Benachrichtigung nicht erstellt: ungültige ThemaID für Schichtbuch - MitarbeiterID={mitarbeiter_id}")
        return None

    try:
        cursor = conn.execute('''
            INSERT INTO Benachrichtigung (
                MitarbeiterID, ThemaID, BemerkungID, Typ, Titel, Nachricht,
                Modul, Aktion, AbteilungID, Zusatzdaten
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            mitarbeiter_id,
            tid_insert if modul == 'schichtbuch' else (thema_id if thema_id else 0),
            bemerkung_id,
            aktion,  # Typ wird durch Aktion ersetzt
            titel,
            nachricht,
            modul,
            aktion,
            abteilung_id_gespeichert,
            zusatzdaten_json
        ))
        benachrichtigung_id = cursor.lastrowid
        logger.info(f"Benachrichtigung erstellt: ID={benachrichtigung_id}, MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, Titel={titel[:50]}")
    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Benachrichtigung: MitarbeiterID={mitarbeiter_id}, Modul={modul}, Aktion={aktion}, Fehler={str(e)}", exc_info=True)
        raise

    # Versand getrennt: Fehler beim Versand dürfen die App-Benachrichtigung nicht verwerfen
    try:
        aktive_kanale = get_aktive_benachrichtigungskanaele(mitarbeiter_id, conn)
        for kanal_typ in aktive_kanale:
            if kanal_typ != 'app':  # App-Benachrichtigungen werden direkt angezeigt
                try:
                    conn.execute('''
                        INSERT INTO BenachrichtigungVersand (
                            BenachrichtigungID, KanalTyp, Status
                        )
                        VALUES (?, ?, 'pending')
                    ''', (benachrichtigung_id, kanal_typ))
                    logger.debug(f"Versand-Eintrag erstellt: BenachrichtigungID={benachrichtigung_id}, KanalTyp={kanal_typ}")
                    versende_benachrichtigung(benachrichtigung_id, kanal_typ, conn)
                except Exception as ve:
                    logger.error(
                        f"Versand übersprungen nach Benachrichtigung {benachrichtigung_id}, Kanal {kanal_typ}: {ve}",
                        exc_info=True,
                    )
    except Exception as e:
        logger.error(f"Fehler bei Kanal-/Versandvorbereitung für Benachrichtigung {benachrichtigung_id}: {e}", exc_info=True)

    return benachrichtigung_id


def erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id_erstellt, conn=None):
    """
    Erstellt Benachrichtigungen für alle Mitarbeiter, die bereits eine Bemerkung zu diesem Thema haben
    (außer dem Ersteller der neuen Bemerkung)
    Nutzt jetzt die neue Filterlogik.
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_bemerkung(thema_id, bemerkung_id, mitarbeiter_id_erstellt, conn)
    
    logger.info(f"Erstelle Benachrichtigungen für neue Bemerkung: ThemaID={thema_id}, BemerkungID={bemerkung_id}, ErstellerID={mitarbeiter_id_erstellt}")
    
    # Alle Mitarbeiter finden, die bereits eine Bemerkung zu diesem Thema haben
    mitarbeiter_mit_bemerkungen = conn.execute('''
        SELECT DISTINCT BM.MitarbeiterID, M.Vorname, M.Nachname
        FROM SchichtbuchBemerkungen BM
        JOIN Mitarbeiter M ON BM.MitarbeiterID = M.ID
        WHERE BM.ThemaID = ? 
        AND BM.MitarbeiterID != ?
        AND BM.Gelöscht = 0
        AND M.Aktiv = 1
    ''', (thema_id, mitarbeiter_id_erstellt)).fetchall()
    
    logger.debug(f"Gefundene Mitarbeiter mit Bemerkungen zu Thema {thema_id}: {len(mitarbeiter_mit_bemerkungen)}")
    
    # Thema-Informationen holen
    thema_info = conn.execute('''
        SELECT 
            T.ID,
            T.ErstellerAbteilungID,
            G.Bezeichnung AS Gewerk,
            B.Bezeichnung AS Bereich
        FROM SchichtbuchThema T
        JOIN Gewerke G ON T.GewerkID = G.ID
        JOIN Bereich B ON G.BereichID = B.ID
        WHERE T.ID = ?
    ''', (thema_id,)).fetchone()
    
    if not thema_info:
        logger.warning(f"Thema {thema_id} nicht gefunden, keine Benachrichtigungen erstellt")
        return
    
    # Erstellername holen
    ersteller = conn.execute('''
        SELECT Vorname, Nachname FROM Mitarbeiter WHERE ID = ?
    ''', (mitarbeiter_id_erstellt,)).fetchone()
    
    ersteller_name = f"{ersteller['Vorname']} {ersteller['Nachname']}".strip() if ersteller else "Ein Benutzer"
    
    sichtbare_abteilungen_thema = thema_sichtbare_abteilung_ids(thema_id, conn)

    # Benachrichtigungen erstellen mit Filterlogik
    titel = f"Neue Bemerkung zu Thema #{thema_id}"
    nachricht = f"{ersteller_name} hat eine neue Bemerkung zu '{thema_info['Bereich']} / {thema_info['Gewerk']}' hinzugefügt."

    erstellt_count = 0
    uebersprungen_count = 0

    for mitarbeiter in mitarbeiter_mit_bemerkungen:
        mid = mitarbeiter['MitarbeiterID']
        # Ohne Zeilen in SchichtbuchThemaSichtbarkeit ist „if sichtbare_abteilungen_thema“ falsy — dann darf
        # der Abgleich mit BenachrichtigungEinstellung nicht gegen ErstellerAbteilungID laufen, sondern gegen
        # die sichtbaren Abteilungen des jeweiligen Empfängers (Profil: pro eigener Abteilung / „Alle“).
        if sichtbare_abteilungen_thema:
            effektive_sicht = sichtbare_abteilungen_thema
        else:
            effektive_sicht = get_sichtbare_abteilungen_fuer_mitarbeiter(mid, conn)

        kandidaten = abteilung_ids_empfaenger_in_sichtbarkeit(mid, effektive_sicht, conn)
        fallback_abt = thema_info['ErstellerAbteilungID']
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='schichtbuch',
            aktion='neue_bemerkung',
            mitarbeiter_id=mid,
            titel=titel,
            nachricht=nachricht,
            thema_id=thema_id,
            bemerkung_id=bemerkung_id,
            abteilung_id=kandidaten[0] if kandidaten else fallback_abt,
            conn=conn,
            einstellung_abteilung_ids=kandidaten,
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für neue Bemerkung erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (ThemaID={thema_id})")


def erstelle_benachrichtigung_fuer_neues_thema(thema_id, sichtbare_abteilungen, conn=None):
    """
    Erstellt Benachrichtigungen für alle Mitarbeiter in den sichtbaren Abteilungen
    (außer dem Ersteller)
    Nutzt jetzt die neue Filterlogik.
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_neues_thema(thema_id, sichtbare_abteilungen, conn)
    
    if not sichtbare_abteilungen:
        logger.warning(f"Keine sichtbaren Abteilungen für Thema {thema_id}, keine Benachrichtigungen erstellt")
        return
    
    logger.info(f"Erstelle Benachrichtigungen für neues Thema: ThemaID={thema_id}, SichtbareAbteilungen={sichtbare_abteilungen}")
    
    # Thema-Informationen holen
    thema_info = conn.execute('''
        SELECT 
            T.ID,
            T.ErstellerAbteilungID,
            G.Bezeichnung AS Gewerk,
            B.Bezeichnung AS Bereich
        FROM SchichtbuchThema T
        JOIN Gewerke G ON T.GewerkID = G.ID
        JOIN Bereich B ON G.BereichID = B.ID
        WHERE T.ID = ?
    ''', (thema_id,)).fetchone()
    
    if not thema_info:
        logger.warning(f"Thema {thema_id} nicht gefunden, keine Benachrichtigungen erstellt")
        return
    
    # Ersteller-ID ermitteln (über erste Bemerkung)
    ersteller = conn.execute('''
        SELECT MitarbeiterID FROM SchichtbuchBemerkungen 
        WHERE ThemaID = ? AND Gelöscht = 0 
        ORDER BY Datum ASC LIMIT 1
    ''', (thema_id,)).fetchone()
    
    ersteller_id = ersteller['MitarbeiterID'] if ersteller else None
    
    # Empfänger wie bei check_thema_berechtigung: Schnitt Thema-Sichtbarkeit ∩
    # get_sichtbare_abteilungen_fuer_mitarbeiter (nicht nur exakte Primär/MA-IDs).
    theme_sicht = _int_abteilung_set(sichtbare_abteilungen)
    if ersteller_id is not None:
        kandidaten_rows = conn.execute(
            'SELECT ID FROM Mitarbeiter WHERE Aktiv = 1 AND ID != ?',
            (ersteller_id,),
        ).fetchall()
    else:
        kandidaten_rows = conn.execute(
            'SELECT ID FROM Mitarbeiter WHERE Aktiv = 1',
        ).fetchall()
    mitarbeiter = []
    for row in kandidaten_rows:
        mid = row['ID']
        emp_sicht = _int_abteilung_set(get_sichtbare_abteilungen_fuer_mitarbeiter(mid, conn))
        if emp_sicht & theme_sicht:
            mitarbeiter.append(row)

    if not mitarbeiter:
        logger.info(
            f"Keine Empfänger für neues Thema {thema_id} (Sichtbarkeit={sorted(theme_sicht)}); "
            f"aktive Mitarbeiter außer Ersteller geprüft: {len(kandidaten_rows)}"
        )
    else:
        logger.debug(f"Gefundene Mitarbeiter in sichtbaren Abteilungen: {len(mitarbeiter)}")
    
    # Benachrichtigungen erstellen mit Filterlogik
    titel = f"Neues Thema #{thema_id}"
    nachricht = f"Ein neues Thema '{thema_info['Bereich']} / {thema_info['Gewerk']}' wurde erstellt."
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    for ma in mitarbeiter:
        kandidaten = abteilung_ids_empfaenger_in_sichtbarkeit(ma['ID'], sichtbare_abteilungen, conn)
        fallback_abt = thema_info['ErstellerAbteilungID']
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='schichtbuch',
            aktion='neues_thema',
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            thema_id=thema_id,
            abteilung_id=kandidaten[0] if kandidaten else fallback_abt,
            conn=conn,
            einstellung_abteilung_ids=kandidaten,
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für neues Thema erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (ThemaID={thema_id})")


# ========== Bestellwesen-Benachrichtigungen ==========

def erstelle_benachrichtigung_fuer_angebotsanfrage(angebotsanfrage_id, aktion, conn=None):
    """
    Erstellt Benachrichtigungen für Angebotsanfragen.
    
    Args:
        angebotsanfrage_id: ID der Angebotsanfrage
        aktion: Aktion ('neue_angebotsanfrage', 'angebotsanfrage_bearbeitet', etc.)
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_angebotsanfrage(angebotsanfrage_id, aktion, conn)
    
    # Angebotsanfrage-Informationen holen
    anfrage = conn.execute('''
        SELECT 
            AA.ID,
            AA.ErstellerAbteilungID,
            AA.Status,
            L.Name AS LieferantName,
            M.Vorname || ' ' || M.Nachname AS ErstellerName
        FROM Angebotsanfrage AA
        JOIN Lieferant L ON AA.LieferantID = L.ID
        JOIN Mitarbeiter M ON AA.ErstelltVonID = M.ID
        WHERE AA.ID = ?
    ''', (angebotsanfrage_id,)).fetchone()
    
    if not anfrage:
        return
    
    # Titel und Nachricht je nach Aktion
    aktionen = {
        'neue_angebotsanfrage': ('Neue Angebotsanfrage', f"Eine neue Angebotsanfrage #{angebotsanfrage_id} wurde erstellt."),
        'angebotsanfrage_bearbeitet': ('Angebotsanfrage bearbeitet', f"Die Angebotsanfrage #{angebotsanfrage_id} wurde bearbeitet."),
        'angebotsanfrage_preise_eingegeben': ('Preise eingegeben', f"Preise für Angebotsanfrage #{angebotsanfrage_id} wurden eingegeben."),
    }
    
    titel, nachricht = aktionen.get(aktion, (f"Angebotsanfrage #{angebotsanfrage_id}", f"Aktion bei Angebotsanfrage #{angebotsanfrage_id}"))
    
    logger.info(f"Erstelle Benachrichtigungen für Angebotsanfrage: AngebotsanfrageID={angebotsanfrage_id}, Aktion={aktion}")
    
    # Alle Mitarbeiter in der Abteilung finden (außer Ersteller)
    mitarbeiter = conn.execute('''
        SELECT DISTINCT M.ID
        FROM Mitarbeiter M
        WHERE M.Aktiv = 1
        AND (
            M.PrimaerAbteilungID = ?
            OR EXISTS (
                SELECT 1 FROM MitarbeiterAbteilung MA
                WHERE MA.MitarbeiterID = M.ID
                AND MA.AbteilungID = ?
            )
        )
        AND M.ID != (SELECT ErstelltVonID FROM Angebotsanfrage WHERE ID = ?)
    ''', (anfrage['ErstellerAbteilungID'], anfrage['ErstellerAbteilungID'], angebotsanfrage_id)).fetchall()
    
    logger.debug(f"Gefundene Mitarbeiter für Angebotsanfrage {angebotsanfrage_id}: {len(mitarbeiter)}")
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    # Benachrichtigungen erstellen
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='bestellwesen',
            aktion=aktion,
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            abteilung_id=anfrage['ErstellerAbteilungID'],
            zusatzdaten={'angebotsanfrage_id': angebotsanfrage_id, 'lieferant': anfrage['LieferantName']},
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für Angebotsanfrage erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (AngebotsanfrageID={angebotsanfrage_id})")


def erstelle_benachrichtigung_fuer_bestellung(bestellung_id, aktion, conn=None):
    """
    Erstellt Benachrichtigungen für Bestellungen.
    
    Args:
        bestellung_id: ID der Bestellung
        aktion: Aktion ('neue_bestellung', 'bestellung_zur_freigabe', 'bestellung_freigegeben', 'bestellung_bestellt', etc.)
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_bestellung(bestellung_id, aktion, conn)
    
    # Bestellungs-Informationen holen
    bestellung = conn.execute('''
        SELECT 
            B.ID,
            B.ErstellerAbteilungID,
            B.ErstelltVonID,
            B.Status,
            L.Name AS LieferantName,
            M.Vorname || ' ' || M.Nachname AS ErstellerName
        FROM Bestellung B
        JOIN Lieferant L ON B.LieferantID = L.ID
        JOIN Mitarbeiter M ON B.ErstelltVonID = M.ID
        WHERE B.ID = ?
    ''', (bestellung_id,)).fetchone()
    
    if not bestellung:
        return
    
    # Titel und Nachricht je nach Aktion
    aktionen = {
        'neue_bestellung': ('Neue Bestellung', f"Eine neue Bestellung #{bestellung_id} wurde erstellt."),
        'bestellung_zur_freigabe': ('Bestellung zur Freigabe', f"Bestellung #{bestellung_id} wartet auf Freigabe."),
        'bestellung_freigegeben': ('Bestellung freigegeben', f"Bestellung #{bestellung_id} wurde freigegeben."),
        'bestellung_bestellt': ('Bestellung aufgegeben', f"Bestellung #{bestellung_id} wurde beim Lieferanten aufgegeben."),
    }
    
    titel, nachricht = aktionen.get(aktion, (f"Bestellung #{bestellung_id}", f"Aktion bei Bestellung #{bestellung_id}"))
    
    logger.info(f"Erstelle Benachrichtigungen für Bestellung: BestellungID={bestellung_id}, Aktion={aktion}")
    
    # Für Freigabe: Benachrichtige alle mit Freigabeberechtigung
    if aktion == 'bestellung_zur_freigabe':
        mitarbeiter = conn.execute('''
            SELECT DISTINCT M.ID
            FROM Mitarbeiter M
            JOIN MitarbeiterBerechtigung MB ON M.ID = MB.MitarbeiterID
            JOIN Berechtigung B ON MB.BerechtigungID = B.ID
            WHERE M.Aktiv = 1
            AND B.Schluessel = 'bestellungen_freigeben'
            AND B.Aktiv = 1
        ''').fetchall()
        logger.debug(f"Gefundene Mitarbeiter mit Freigabeberechtigung: {len(mitarbeiter)}")
    elif aktion == 'bestellung_freigegeben':
        # Bei Freigabe: Alle Mitarbeiter in der Abteilung einschließlich Ersteller
        mitarbeiter = conn.execute('''
            SELECT DISTINCT M.ID
            FROM Mitarbeiter M
            WHERE M.Aktiv = 1
            AND (
                M.PrimaerAbteilungID = ?
                OR EXISTS (
                    SELECT 1 FROM MitarbeiterAbteilung MA
                    WHERE MA.MitarbeiterID = M.ID
                    AND MA.AbteilungID = ?
                )
            )
        ''', (bestellung['ErstellerAbteilungID'], bestellung['ErstellerAbteilungID'])).fetchall()
        logger.debug(f"Gefundene Mitarbeiter in Abteilung für freigegebene Bestellung {bestellung_id} (inkl. Ersteller): {len(mitarbeiter)}")
    else:
        # Alle Mitarbeiter in der Abteilung finden (außer Ersteller)
        mitarbeiter = conn.execute('''
            SELECT DISTINCT M.ID
            FROM Mitarbeiter M
            WHERE M.Aktiv = 1
            AND (
                M.PrimaerAbteilungID = ?
                OR EXISTS (
                    SELECT 1 FROM MitarbeiterAbteilung MA
                    WHERE MA.MitarbeiterID = M.ID
                    AND MA.AbteilungID = ?
                )
            )
            AND M.ID != ?
        ''', (bestellung['ErstellerAbteilungID'], bestellung['ErstellerAbteilungID'], bestellung['ErstelltVonID'])).fetchall()
        logger.debug(f"Gefundene Mitarbeiter in Abteilung für Bestellung {bestellung_id}: {len(mitarbeiter)}")
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    # Benachrichtigungen erstellen
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='bestellwesen',
            aktion=aktion,
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            abteilung_id=bestellung['ErstellerAbteilungID'],
            zusatzdaten={'bestellung_id': bestellung_id, 'lieferant': bestellung['LieferantName']},
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für Bestellung erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (BestellungID={bestellung_id})")


def erstelle_benachrichtigung_fuer_wareneingang(bestellung_id, conn=None):
    """
    Erstellt Benachrichtigungen für Wareneingang.
    
    Args:
        bestellung_id: ID der Bestellung
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return erstelle_benachrichtigung_fuer_wareneingang(bestellung_id, conn)
    
    # Bestellungs-Informationen holen
    bestellung = conn.execute('''
        SELECT 
            B.ID,
            B.ErstellerAbteilungID,
            L.Name AS LieferantName
        FROM Bestellung B
        JOIN Lieferant L ON B.LieferantID = L.ID
        WHERE B.ID = ?
    ''', (bestellung_id,)).fetchone()
    
    if not bestellung:
        return
    
    logger.info(f"Erstelle Benachrichtigungen für Wareneingang: BestellungID={bestellung_id}")
    
    titel = f"Wareneingang für Bestellung #{bestellung_id}"
    nachricht = f"Wareneingang für Bestellung #{bestellung_id} wurde gebucht."
    
    # Alle Mitarbeiter in der Abteilung finden
    mitarbeiter = conn.execute('''
        SELECT DISTINCT M.ID
        FROM Mitarbeiter M
        WHERE M.Aktiv = 1
        AND (
            M.PrimaerAbteilungID = ?
            OR EXISTS (
                SELECT 1 FROM MitarbeiterAbteilung MA
                WHERE MA.MitarbeiterID = M.ID
                AND MA.AbteilungID = ?
            )
        )
    ''', (bestellung['ErstellerAbteilungID'], bestellung['ErstellerAbteilungID'])).fetchall()
    
    logger.debug(f"Gefundene Mitarbeiter für Wareneingang Bestellung {bestellung_id}: {len(mitarbeiter)}")
    
    erstellt_count = 0
    uebersprungen_count = 0
    
    # Benachrichtigungen erstellen
    for ma in mitarbeiter:
        benachrichtigung_id = erstelle_benachrichtigung_mit_filter(
            modul='bestellwesen',
            aktion='wareneingang',
            mitarbeiter_id=ma['ID'],
            titel=titel,
            nachricht=nachricht,
            abteilung_id=bestellung['ErstellerAbteilungID'],
            zusatzdaten={'bestellung_id': bestellung_id, 'lieferant': bestellung['LieferantName']},
            conn=conn
        )
        if benachrichtigung_id:
            erstellt_count += 1
        else:
            uebersprungen_count += 1
    
    logger.info(f"Benachrichtigungen für Wareneingang erstellt: {erstellt_count} erstellt, {uebersprungen_count} übersprungen (BestellungID={bestellung_id})")


# ========== Versand-Funktionen ==========

def versende_benachrichtigung(benachrichtigung_id, kanal_typ, conn=None):
    """
    Versendet eine Benachrichtigung über einen spezifischen Kanal.
    Diese Funktion wird von den spezifischen Kanal-Implementierungen aufgerufen.
    
    Args:
        benachrichtigung_id: ID der Benachrichtigung
        kanal_typ: Kanal-Typ ('mail', 'push', etc.)
        conn: Datenbankverbindung (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_benachrichtigung(benachrichtigung_id, kanal_typ, conn)
    
    # Importiere spezifische Versand-Module
    try:
        if kanal_typ == 'mail':
            from utils.benachrichtigungen_mail import versende_mail_benachrichtigung
            erfolg = versende_mail_benachrichtigung(benachrichtigung_id, conn)
        elif kanal_typ == 'push':
            from utils.benachrichtigungen_push import versende_push_benachrichtigung
            erfolg = versende_push_benachrichtigung(benachrichtigung_id, conn)
        else:
            # Unbekannter Kanal
            erfolg = False
    except ImportError:
        # Modul nicht verfügbar
        erfolg = False
    except Exception as e:
        logger.error(f"Fehler beim Versenden der Benachrichtigung {benachrichtigung_id} über {kanal_typ}: {e}", exc_info=True)
        erfolg = False
    
    jetzt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if erfolg:
        conn.execute('''
            UPDATE BenachrichtigungVersand
            SET Status = 'sent', VersandAm = ?
            WHERE BenachrichtigungID = ? AND KanalTyp = ?
        ''', (jetzt, benachrichtigung_id, kanal_typ))
    else:
        conn.execute('''
            UPDATE BenachrichtigungVersand
            SET Status = 'failed', VersandAm = ?, Fehlermeldung = ?
            WHERE BenachrichtigungID = ? AND KanalTyp = ?
        ''', (jetzt, f"Fehler beim Versenden über {kanal_typ}", benachrichtigung_id, kanal_typ))
    
    return erfolg


def versende_alle_benachrichtigungen(conn=None):
    """
    Versendet alle ausstehenden Benachrichtigungen.
    Sollte regelmäßig (z.B. per Cron-Job) aufgerufen werden.
    
    Args:
        conn: Datenbankverbindung (optional)
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_alle_benachrichtigungen(conn)
    
    # Hole alle ausstehenden Versand-Einträge
    versand_eintraege = conn.execute('''
        SELECT BV.BenachrichtigungID, BV.KanalTyp
        FROM BenachrichtigungVersand BV
        WHERE BV.Status = 'pending'
        ORDER BY BV.ID ASC
        LIMIT 100
    ''').fetchall()
    
    erfolg_count = 0
    fehler_count = 0
    
    for eintrag in versand_eintraege:
        if versende_benachrichtigung(eintrag['BenachrichtigungID'], eintrag['KanalTyp'], conn):
            erfolg_count += 1
        else:
            fehler_count += 1
    
    return {'erfolg': erfolg_count, 'fehler': fehler_count}


# ========== API / UI: Ziel-URL und ungelesene Liste ==========

def _parse_zusatzdaten_benachrichtigung(z):
    if z is None:
        return {}
    if isinstance(z, dict):
        return z
    if isinstance(z, str) and z.strip():
        try:
            return json.loads(z)
        except json.JSONDecodeError:
            return {}
    return {}


def ziel_url_fuer_benachrichtigung(b_dict):
    """
    Ziel-URL für „Ansehen“ aus Modul, ThemaID und Zusatzdaten.
    Benötigt Flask-Anwendungskontext (url_for). Gibt None zurück, wenn kein Link sinnvoll ist.
    """
    from flask import url_for

    modul = (b_dict.get('Modul') or '').strip().lower()
    zusatz = _parse_zusatzdaten_benachrichtigung(b_dict.get('Zusatzdaten'))

    if modul == 'schichtbuch':
        tid = b_dict.get('ThemaID')
        if tid and tid != 0:
            return url_for('schichtbuch.thema_detail', thema_id=tid)
    if modul == 'bestellwesen':
        bid = zusatz.get('bestellung_id')
        if bid:
            return url_for('ersatzteile.bestellung_detail', bestellung_id=bid)
        aid = zusatz.get('angebotsanfrage_id')
        if aid:
            return url_for('ersatzteile.angebotsanfrage_detail', angebotsanfrage_id=aid)
    return None


def fetch_ungelesen_benachrichtigungen_rows(conn, mitarbeiter_id, limit=20):
    """
    Ungelesene Benachrichtigungen für alle Module (LEFT JOIN Schichtbuch, kein Ausschluss von Bestellwesen).
    Schichtbuch-Einträge mit fehlendem oder gelöschtem Thema werden ausgeblendet.
    """
    return conn.execute('''
        SELECT
            B.ID,
            B.Typ,
            B.Titel,
            B.Nachricht,
            B.ThemaID,
            B.ErstelltAm,
            B.Modul,
            B.Aktion,
            B.Zusatzdaten,
            T.GewerkID,
            G.Bezeichnung AS Gewerk,
            BE.Bezeichnung AS Bereich
        FROM Benachrichtigung B
        LEFT JOIN SchichtbuchThema T ON B.ThemaID = T.ID AND B.ThemaID != 0
        LEFT JOIN Gewerke G ON T.GewerkID = G.ID
        LEFT JOIN Bereich BE ON G.BereichID = BE.ID
        WHERE B.MitarbeiterID = ? AND B.Gelesen = 0
        AND NOT (
            B.Modul = 'schichtbuch'
            AND B.ThemaID != 0
            AND (T.ID IS NULL OR T.Gelöscht = 1)
        )
        ORDER BY B.ErstelltAm DESC
        LIMIT ?
    ''', (mitarbeiter_id, limit)).fetchall()


def count_ungelesen_benachrichtigungen(conn, mitarbeiter_id):
    row = conn.execute('''
        SELECT COUNT(*) AS cnt
        FROM Benachrichtigung
        WHERE MitarbeiterID = ? AND Gelesen = 0
    ''', (mitarbeiter_id,)).fetchone()
    return int(row['cnt']) if row else 0


def benachrichtigungen_rows_zu_api_liste(rows):
    """Konvertiert DB-Zeilen zu Dicts inkl. ziel_url (JSON-serialisierbar)."""
    out = []
    for r in rows:
        d = dict(r)
        if d.get('ErstelltAm') is not None and hasattr(d['ErstelltAm'], 'isoformat'):
            d['ErstelltAm'] = d['ErstelltAm'].isoformat(sep=' ', timespec='seconds')
        d['ziel_url'] = ziel_url_fuer_benachrichtigung(d)
        out.append(d)
    return out


def build_ungelesen_benachrichtigungen_api_dict(mitarbeiter_id, conn, limit=20):
    """Payload für Glocke/Toasts: success, benachrichtigungen, anzahl_ungelesen."""
    rows = fetch_ungelesen_benachrichtigungen_rows(conn, mitarbeiter_id, limit=limit)
    return {
        'success': True,
        'benachrichtigungen': benachrichtigungen_rows_zu_api_liste(rows),
        'anzahl_ungelesen': count_ungelesen_benachrichtigungen(conn, mitarbeiter_id),
    }

