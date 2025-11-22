"""
E-Mail-Versand für Benachrichtigungen
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from utils import get_db_connection


def versende_mail_benachrichtigung(benachrichtigung_id, conn=None):
    """
    Versendet eine Benachrichtigung per E-Mail.
    
    Args:
        benachrichtigung_id: ID der Benachrichtigung
        conn: Datenbankverbindung (optional)
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    if conn is None:
        with get_db_connection() as conn:
            return versende_mail_benachrichtigung(benachrichtigung_id, conn)
    
    # Prüfe ob E-Mail aktiviert ist
    if not current_app.config.get('MAIL_ENABLED', False):
        return False
    
    # Hole Benachrichtigung und Mitarbeiter-Informationen
    benachrichtigung = conn.execute('''
        SELECT 
            B.ID,
            B.Titel,
            B.Nachricht,
            B.Modul,
            B.Aktion,
            M.Email,
            M.Vorname,
            M.Nachname
        FROM Benachrichtigung B
        JOIN Mitarbeiter M ON B.MitarbeiterID = M.ID
        WHERE B.ID = ?
    ''', (benachrichtigung_id,)).fetchone()
    
    if not benachrichtigung or not benachrichtigung['Email']:
        return False
    
    try:
        # Erstelle E-Mail
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"BIS: {benachrichtigung['Titel']}"
        msg['From'] = f"{current_app.config.get('MAIL_DEFAULT_SENDER_NAME', 'BIS System')} <{current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')}>"
        msg['To'] = benachrichtigung['Email']
        
        # HTML-Version der E-Mail
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>BIS Benachrichtigung</h1>
                </div>
                <div class="content">
                    <h2>{benachrichtigung['Titel']}</h2>
                    <p>{benachrichtigung['Nachricht']}</p>
                    <p><strong>Modul:</strong> {benachrichtigung['Modul'] or 'N/A'}</p>
                    <p><strong>Aktion:</strong> {benachrichtigung['Aktion'] or 'N/A'}</p>
                </div>
                <div class="footer">
                    <p>Diese E-Mail wurde automatisch vom BIS System generiert.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain-Text-Version
        text_body = f"""
BIS Benachrichtigung

{benachrichtigung['Titel']}

{benachrichtigung['Nachricht']}

Modul: {benachrichtigung['Modul'] or 'N/A'}
Aktion: {benachrichtigung['Aktion'] or 'N/A'}

Diese E-Mail wurde automatisch vom BIS System generiert.
        """
        
        # Füge beide Versionen hinzu
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Versende E-Mail
        smtp_server = current_app.config.get('MAIL_SERVER', 'localhost')
        smtp_port = current_app.config.get('MAIL_PORT', 587)
        use_tls = current_app.config.get('MAIL_USE_TLS', True)
        use_ssl = current_app.config.get('MAIL_USE_SSL', False)
        username = current_app.config.get('MAIL_USERNAME')
        password = current_app.config.get('MAIL_PASSWORD')
        
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            if use_tls:
                server.starttls()
        
        if username and password:
            server.login(username, password)
        
        server.send_message(msg)
        server.quit()
        
        return True
        
    except Exception as e:
        print(f"Fehler beim Versenden der E-Mail-Benachrichtigung {benachrichtigung_id}: {e}")
        return False

