"""
Push-Benachrichtigungen für Benachrichtigungen
Web Push API Integration
"""

from flask import current_app
from utils import get_db_connection
import json


def versende_push_benachrichtigung(benachrichtigung_id, conn=None):
    """
    Versendet eine Benachrichtigung per Web Push.
    
    Args:
        benachrichtigung_id: ID der Benachrichtigung
        conn: Datenbankverbindung (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_push_benachrichtigung(benachrichtigung_id, conn)
    
    # Hole Benachrichtigung und Push-Konfiguration
    benachrichtigung = conn.execute('''
        SELECT 
            B.ID,
            B.Titel,
            B.Nachricht,
            B.MitarbeiterID,
            BK.Konfiguration
        FROM Benachrichtigung B
        JOIN BenachrichtigungKanal BK ON B.MitarbeiterID = BK.MitarbeiterID
        WHERE B.ID = ? AND BK.KanalTyp = 'push' AND BK.Aktiv = 1
    ''', (benachrichtigung_id,)).fetchone()
    
    if not benachrichtigung or not benachrichtigung['Konfiguration']:
        return False
    
    try:
        # Parse Push-Konfiguration (enthält Subscription-Objekt)
        push_config = json.loads(benachrichtigung['Konfiguration'])
        
        # Prüfe ob pywebpush verfügbar ist
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            print("pywebpush ist nicht installiert. Push-Benachrichtigungen sind nicht verfügbar.")
            return False
        
        # VAPID-Keys aus Konfiguration
        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        vapid_email = current_app.config.get('VAPID_EMAIL', 'noreply@example.com')
        
        if not vapid_private_key or not vapid_public_key:
            print("VAPID-Keys sind nicht konfiguriert. Push-Benachrichtigungen sind nicht verfügbar.")
            return False
        
        # Erstelle Push-Payload
        payload = {
            'title': benachrichtigung['Titel'],
            'body': benachrichtigung['Nachricht'],
            'icon': '/static/icons/icon-192.png',
            'badge': '/static/icons/icon-32.png',
            'data': {
                'benachrichtigung_id': benachrichtigung_id,
                'url': '/dashboard'  # Standard-URL, kann später erweitert werden
            }
        }
        
        # Versende Push-Benachrichtigung
        webpush(
            subscription_info=push_config,
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={
                'sub': f'mailto:{vapid_email}'
            }
        )
        
        return True
        
    except Exception as e:
        print(f"Fehler beim Versenden der Push-Benachrichtigung {benachrichtigung_id}: {e}")
        # Bei ungültiger Subscription: Deaktiviere Push für diesen Benutzer
        if '410' in str(e) or 'Gone' in str(e):
            conn.execute('''
                UPDATE BenachrichtigungKanal
                SET Aktiv = 0
                WHERE MitarbeiterID = ? AND KanalTyp = 'push'
            ''', (benachrichtigung['MitarbeiterID'],))
        return False


def speichere_push_subscription(mitarbeiter_id, subscription, conn=None):
    """
    Speichert eine Web Push Subscription für einen Mitarbeiter.
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        subscription: Subscription-Objekt (dict mit keys, endpoint, etc.)
        conn: Datenbankverbindung (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    if conn is None:
        with get_db_connection() as conn:
            return speichere_push_subscription(mitarbeiter_id, subscription, conn)
    
    try:
        subscription_json = json.dumps(subscription)
        
        # Aktualisiere oder erstelle Kanal
        conn.execute('''
            INSERT OR REPLACE INTO BenachrichtigungKanal (
                MitarbeiterID, KanalTyp, Aktiv, Konfiguration
            )
            VALUES (?, 'push', 1, ?)
        ''', (mitarbeiter_id, subscription_json))
        
        return True
        
    except Exception as e:
        print(f"Fehler beim Speichern der Push-Subscription für Mitarbeiter {mitarbeiter_id}: {e}")
        return False


def versende_test_push(mitarbeiter_id, conn=None):
    """
    Sendet eine Test-Push-Benachrichtigung an einen Mitarbeiter.
    
    Args:
        mitarbeiter_id: ID des Mitarbeiters
        conn: Datenbankverbindung (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_test_push(mitarbeiter_id, conn)
    
    # Hole Push-Konfiguration
    kanal = conn.execute('''
        SELECT Konfiguration FROM BenachrichtigungKanal
        WHERE MitarbeiterID = ? AND KanalTyp = 'push' AND Aktiv = 1
    ''', (mitarbeiter_id,)).fetchone()
    
    if not kanal or not kanal['Konfiguration']:
        return False
    
    try:
        # Parse Push-Konfiguration (enthält Subscription-Objekt)
        push_config = json.loads(kanal['Konfiguration'])
        
        # Prüfe ob pywebpush verfügbar ist
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            print("pywebpush ist nicht installiert. Push-Benachrichtigungen sind nicht verfügbar.")
            return False
        
        # VAPID-Keys aus Konfiguration
        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        vapid_email = current_app.config.get('VAPID_EMAIL', 'noreply@example.com')
        
        if not vapid_private_key or not vapid_public_key:
            print("VAPID-Keys sind nicht konfiguriert. Push-Benachrichtigungen sind nicht verfügbar.")
            return False
        
        # Erstelle Test-Push-Payload
        payload = {
            'title': 'BIS Test-Benachrichtigung',
            'body': 'Dies ist eine Test-Push-Benachrichtigung. Wenn Sie diese sehen, funktionieren Push-Benachrichtigungen korrekt!',
            'icon': '/static/icons/icon-192.png',
            'badge': '/static/icons/icon-32.png',
            'data': {
                'url': '/dashboard',
                'test': True
            }
        }
        
        # Versende Push-Benachrichtigung
        webpush(
            subscription_info=push_config,
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={
                'sub': f'mailto:{vapid_email}'
            }
        )
        
        return True
        
    except Exception as e:
        print(f"Fehler beim Versenden der Test-Push-Benachrichtigung für Mitarbeiter {mitarbeiter_id}: {e}")
        # Bei ungültiger Subscription: Deaktiviere Push für diesen Benutzer
        if '410' in str(e) or 'Gone' in str(e):
            conn.execute('''
                UPDATE BenachrichtigungKanal
                SET Aktiv = 0
                WHERE MitarbeiterID = ? AND KanalTyp = 'push'
            ''', (mitarbeiter_id,))
        return False
