"""
Automatische Bereinigung alter Benachrichtigungen
Löscht regelmäßig alte Benachrichtigungen, um die Datenbank schlank zu halten
"""
import logging
from datetime import datetime, timedelta
from utils import get_db_connection

logger = logging.getLogger(__name__)


def bereinige_alte_benachrichtigungen(tage_alt=30, nur_gelesene=True):
    """
    Löscht alte Benachrichtigungen aus der Datenbank
    
    Args:
        tage_alt: Anzahl der Tage, nach denen Benachrichtigungen gelöscht werden (Standard: 30)
        nur_gelesene: Wenn True, werden nur gelesene Benachrichtigungen gelöscht (Standard: True)
    
    Returns:
        Tuple (gelöscht_count, fehler)
    """
    try:
        with get_db_connection() as conn:
            # Datum berechnen (X Tage in der Vergangenheit)
            grenzdatum = datetime.now() - timedelta(days=tage_alt)
            grenzdatum_str = grenzdatum.strftime('%Y-%m-%d %H:%M:%S')
            
            # Query aufbauen
            if nur_gelesene:
                query = '''
                    DELETE FROM Benachrichtigung
                    WHERE Gelesen = 1 
                    AND ErstelltAm < ?
                '''
            else:
                # Alle Benachrichtigungen (gelesen und ungelesen) löschen
                query = '''
                    DELETE FROM Benachrichtigung
                    WHERE ErstelltAm < ?
                '''
            
            cursor = conn.cursor()
            cursor.execute(query, (grenzdatum_str,))
            gelöscht_count = cursor.rowcount
            
            conn.commit()
            
            if gelöscht_count > 0:
                logger.info(f"Bereinigung: {gelöscht_count} alte Benachrichtigungen gelöscht (älter als {tage_alt} Tage, nur_gelesene={nur_gelesene})")
            else:
                logger.debug(f"Bereinigung: Keine alten Benachrichtigungen gefunden (älter als {tage_alt} Tage)")
            
            return gelöscht_count, None
            
    except Exception as e:
        logger.error(f"Fehler bei der Bereinigung alter Benachrichtigungen: {str(e)}", exc_info=True)
        return 0, str(e)


def bereinige_benachrichtigungen_mit_limit(pro_mitarbeiter_max=1000):
    """
    Behält nur die letzten N Benachrichtigungen pro Mitarbeiter
    Löscht die ältesten Benachrichtigungen, wenn das Limit überschritten wird
    
    Args:
        pro_mitarbeiter_max: Maximale Anzahl Benachrichtigungen pro Mitarbeiter (Standard: 1000)
    
    Returns:
        Tuple (gelöscht_count, fehler)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Alle Mitarbeiter mit Benachrichtigungen
            mitarbeiter = conn.execute('''
                SELECT DISTINCT MitarbeiterID 
                FROM Benachrichtigung
            ''').fetchall()
            
            gesamt_gelöscht = 0
            
            for mitarbeiter_row in mitarbeiter:
                mitarbeiter_id = mitarbeiter_row['MitarbeiterID']
                
                # Zähle Benachrichtigungen für diesen Mitarbeiter
                anzahl = conn.execute('''
                    SELECT COUNT(*) as count 
                    FROM Benachrichtigung 
                    WHERE MitarbeiterID = ?
                ''', (mitarbeiter_id,)).fetchone()['count']
                
                if anzahl > pro_mitarbeiter_max:
                    # Finde die IDs der ältesten Benachrichtigungen, die gelöscht werden sollen
                    zu_loeschen = anzahl - pro_mitarbeiter_max
                    
                    alte_ids = conn.execute('''
                        SELECT ID 
                        FROM Benachrichtigung 
                        WHERE MitarbeiterID = ?
                        ORDER BY ErstelltAm ASC
                        LIMIT ?
                    ''', (mitarbeiter_id, zu_loeschen)).fetchall()
                    
                    if alte_ids:
                        ids_liste = [str(row['ID']) for row in alte_ids]
                        placeholders = ','.join(['?'] * len(ids_liste))
                        
                        cursor.execute(f'''
                            DELETE FROM Benachrichtigung
                            WHERE ID IN ({placeholders})
                        ''', ids_liste)
                        
                        gesamt_gelöscht += cursor.rowcount
            
            conn.commit()
            
            if gesamt_gelöscht > 0:
                logger.info(f"Bereinigung: {gesamt_gelöscht} alte Benachrichtigungen gelöscht (Limit: {pro_mitarbeiter_max} pro Mitarbeiter)")
            else:
                logger.debug(f"Bereinigung: Keine Benachrichtigungen über Limit ({pro_mitarbeiter_max} pro Mitarbeiter)")
            
            return gesamt_gelöscht, None
            
    except Exception as e:
        logger.error(f"Fehler bei der Bereinigung alter Benachrichtigungen: {str(e)}", exc_info=True)
        return 0, str(e)


def bereinige_benachrichtigungen_automatisch(app):
    """
    Führt die automatische Bereinigung basierend auf App-Konfiguration durch
    
    Args:
        app: Flask-App-Instanz
    
    Returns:
        Tuple (gelöscht_count, fehler)
    """
    # Konfiguration aus App-Config lesen
    cleanup_aktiv = app.config.get('BENACHRICHTIGUNGEN_CLEANUP_AKTIV', True)
    
    if not cleanup_aktiv:
        logger.debug("Benachrichtigungen-Cleanup ist deaktiviert")
        return 0, None
    
    tage_alt = app.config.get('BENACHRICHTIGUNGEN_CLEANUP_TAGE', 30)
    nur_gelesene = app.config.get('BENACHRICHTIGUNGEN_CLEANUP_NUR_GELESENE', True)
    limit_pro_mitarbeiter = app.config.get('BENACHRICHTIGUNGEN_CLEANUP_LIMIT_PRO_MITARBEITER', None)
    
    gesamt_gelöscht = 0
    
    # Methode 1: Nach Alter löschen
    gelöscht_alter, fehler = bereinige_alte_benachrichtigungen(tage_alt=tage_alt, nur_gelesene=nur_gelesene)
    gesamt_gelöscht += gelöscht_alter
    
    if fehler:
        return gesamt_gelöscht, fehler
    
    # Methode 2: Nach Limit pro Mitarbeiter (optional)
    if limit_pro_mitarbeiter:
        gelöscht_limit, fehler = bereinige_benachrichtigungen_mit_limit(pro_mitarbeiter_max=limit_pro_mitarbeiter)
        gesamt_gelöscht += gelöscht_limit
        
        if fehler:
            return gesamt_gelöscht, fehler
    
    return gesamt_gelöscht, None

