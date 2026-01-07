"""
Angebotsanfrage Report - PDF/DOCX-Generierung für Angebotsanfragen
"""

from datetime import datetime
import os
import tempfile
import sys
from io import BytesIO
from flask import current_app
from docxtpl import DocxTemplate
from utils.firmendaten import get_firmendaten
from modules.ersatzteile.utils.helpers import safe_get
from .pdf_export import convert_docx_to_pdf

try:
    from docx2pdf import convert
    DOCX2PDF_AVAILABLE = True
except ImportError:
    DOCX2PDF_AVAILABLE = False


def generate_angebotsanfrage_pdf(angebotsanfrage_id, conn):
    """
    Generiert ein PDF/DOCX für eine Angebotsanfrage.
    Gibt ein Tupel zurück: (content: bytes, filename: str, mimetype: str, is_pdf: bool)
    """
    # Angebotsanfrage laden
    anfrage = conn.execute("""
        SELECT 
            a.*,
            l.Name AS LieferantName,
            l.Strasse AS LieferantStrasse,
            l.PLZ AS LieferantPLZ,
            l.Ort AS LieferantOrt,
            l.Telefon AS LieferantTelefon,
            l.Email AS LieferantEmail,
            m.Vorname || ' ' || m.Nachname AS ErstelltVon,
            m.Email AS ErstelltVonEmail,
            m.Handynummer AS ErstelltVonHandy,
            abt.Bezeichnung AS ErstelltVonAbteilung
        FROM Angebotsanfrage a
        LEFT JOIN Lieferant l ON a.LieferantID = l.ID
        LEFT JOIN Mitarbeiter m ON a.ErstelltVonID = m.ID
        LEFT JOIN Abteilung abt ON a.ErstellerAbteilungID = abt.ID
        WHERE a.ID = ?
    """, (angebotsanfrage_id,)).fetchone()
    
    if not anfrage:
        raise ValueError('Angebotsanfrage nicht gefunden.')
    
    # Positionen laden
    positionen = conn.execute("""
        SELECT 
            p.*,
            e.ID AS ErsatzteilID,
            COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
            COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
            COALESCE(e.Einheit, 'Stück') AS Einheit,
            e.Preis AS AktuellerPreis,
            e.Waehrung AS AktuelleWaehrung
        FROM AngebotsanfragePosition p
        LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
        WHERE p.AngebotsanfrageID = ?
        ORDER BY p.ID
    """, (angebotsanfrage_id,)).fetchall()
    
    # Firmendaten laden
    firmendaten = get_firmendaten()
    
    # Template-Pfad
    template_path = os.path.join(current_app.root_path, 'templates', 'reports', 'angebot_template.docx')
    if not os.path.exists(template_path):
        raise FileNotFoundError('Angebotsvorlage nicht gefunden.')
    
    # Template laden
    doc = DocxTemplate(template_path)
    
    # Datum formatieren
    datum = ''
    if anfrage['ErstelltAm']:
        try:
            datum = datetime.strptime(anfrage['ErstelltAm'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        except:
            datum = anfrage['ErstelltAm'][:10] if anfrage['ErstelltAm'] else ''
    
    # Kontaktdaten des Erstellers zusammenstellen
    kontakt_details = []
    if anfrage['ErstelltVonEmail']:
        kontakt_details.append(f"E-Mail: {anfrage['ErstelltVonEmail']}")
    if anfrage['ErstelltVonHandy']:
        kontakt_details.append(f"Tel: {anfrage['ErstelltVonHandy']}")
    kontakt_text = ' | '.join(kontakt_details) if kontakt_details else ''
    
    # Positionen für Template vorbereiten
    positionen_liste = []
    for idx, pos in enumerate(positionen, 1):
        # Bestellnummer hat Priorität, dann ErsatzteilID, sonst '-'
        if pos['Bestellnummer']:
            artikel_nr = pos['Bestellnummer']
        elif pos['ErsatzteilID']:
            artikel_nr = str(pos['ErsatzteilID'])
        else:
            artikel_nr = '-'
        bezeichnung = pos['Bezeichnung'] or '-'
        menge_val = pos['Menge'] if pos['Menge'] else 1.0
        einheit = safe_get(pos, 'Einheit', 'Stück')
        # Menge formatieren: Ganze Zahlen ohne Kommastellen, sonst ohne unnötige Nullen
        if menge_val == int(menge_val):
            menge_text = f"{int(menge_val)} {einheit}"
        else:
            menge_text = f"{menge_val} {einheit}"
        
        positionen_liste.append({
            'position': idx,
            'artikelnummer': artikel_nr,
            'bezeichnung': bezeichnung,
            'menge': menge_text,
            'bemerkung': pos['Bemerkung'] or ''
        })
    
    # Footer-Informationen zusammenstellen
    footer_lines = []
    if firmendaten:
        if safe_get(firmendaten, 'Geschaeftsfuehrer'):
            footer_lines.append(f"Geschäftsführer: {firmendaten['Geschaeftsfuehrer']}")
        if safe_get(firmendaten, 'UStIdNr'):
            footer_lines.append(f"UStIdNr.: {firmendaten['UStIdNr']}")
        if safe_get(firmendaten, 'Steuernummer'):
            footer_lines.append(f"Steuernr.: {firmendaten['Steuernummer']}")
        if safe_get(firmendaten, 'Telefon'):
            footer_lines.append(f"Telefon: {firmendaten['Telefon']}")
        bank_name = safe_get(firmendaten, 'BankName')
        iban = safe_get(firmendaten, 'IBAN')
        if bank_name and iban:
            footer_lines.append(f"Bankverbindung: {firmendaten['BankName']}")
            footer_lines.append(f"IBAN: {firmendaten['IBAN']}")
            bic = safe_get(firmendaten, 'BIC')
            if bic:
                footer_lines.append(f"BIC: {firmendaten['BIC']}")
    footer_text = ' | '.join(footer_lines) if footer_lines else ''
    
    # Lieferanschrift zusammenstellen (falls abweichend)
    lieferanschrift = []
    if firmendaten:
        liefer_strasse = safe_get(firmendaten, 'LieferStrasse')
        if liefer_strasse:
            lieferanschrift.append(firmendaten['LieferStrasse'])
        liefer_plz = safe_get(firmendaten, 'LieferPLZ')
        liefer_ort = safe_get(firmendaten, 'LieferOrt')
        if liefer_plz and liefer_ort:
            lieferanschrift.append(f"{firmendaten['LieferPLZ']} {firmendaten['LieferOrt']}")
    lieferanschrift_text = '\n'.join(lieferanschrift) if lieferanschrift else ''
    
    # Kontext für Template
    context = {
        # Angebotsanfrage-Daten
        'angebotsanfrage_id': anfrage['ID'],
        'datum': datum,
        'erstellt_von': anfrage['ErstelltVon'] or '',
        'erstellt_von_abteilung': safe_get(anfrage, 'ErstelltVonAbteilung', ''),
        'erstellt_von_kontakt': kontakt_text,
        'bemerkung': anfrage['Bemerkung'] or '',
        
        # Lieferant-Daten
        'lieferant_name': anfrage['LieferantName'] or '',
        'lieferant_strasse': anfrage['LieferantStrasse'] or '',
        'lieferant_plz': anfrage['LieferantPLZ'] or '',
        'lieferant_ort': anfrage['LieferantOrt'] or '',
        'lieferant_plz_ort': f"{anfrage['LieferantPLZ'] or ''} {anfrage['LieferantOrt'] or ''}".strip(),
        'lieferant_telefon': anfrage['LieferantTelefon'] or '',
        'lieferant_email': anfrage['LieferantEmail'] or '',
        
        # Firmendaten
        'firmenname': safe_get(firmendaten, 'Firmenname', '') if firmendaten else '',
        'firmenstrasse': safe_get(firmendaten, 'Strasse', '') if firmendaten else '',
        'firmenplz': safe_get(firmendaten, 'PLZ', '') if firmendaten else '',
        'firmenort': safe_get(firmendaten, 'Ort', '') if firmendaten else '',
        'firmenplz_ort': f"{safe_get(firmendaten, 'PLZ', '')} {safe_get(firmendaten, 'Ort', '')}".strip() if firmendaten else '',
        'firmen_telefon': safe_get(firmendaten, 'Telefon', '') if firmendaten else '',
        'firmen_website': safe_get(firmendaten, 'Website', '') if firmendaten else '',
        'firmen_email': safe_get(firmendaten, 'Email', '') if firmendaten else '',
        'firma_lieferstraße': safe_get(firmendaten, 'LieferStrasse', '') if firmendaten else '',
        'firma_lieferPLZ': safe_get(firmendaten, 'LieferPLZ', '') if firmendaten else '',
        'firma_lieferOrt': safe_get(firmendaten, 'LieferOrt', '') if firmendaten else '',
        'lieferanschrift': lieferanschrift_text,
        'footer': footer_text,
        
        # Positionen
        'positionen': positionen_liste,
        'hat_positionen': len(positionen_liste) > 0,
    }
    
    # Template rendern
    doc.render(context)
    
    # Als PDF konvertieren oder DOCX zurückgeben
    if DOCX2PDF_AVAILABLE:
        # PDF-Konvertierung versuchen
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        # Temporäre DOCX-Datei erstellen
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_docx:
            tmp_docx.write(buffer.getvalue())
            tmp_docx_path = tmp_docx.name
        
        # PDF erstellen
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
            tmp_pdf_path = tmp_pdf.name
        
        try:
            # PDF-Konvertierung
            if convert_docx_to_pdf(tmp_docx_path, tmp_pdf_path):
                # PDF lesen
                with open(tmp_pdf_path, 'rb') as f:
                    pdf_content = f.read()
                
                # Temporäre Dateien löschen
                os.unlink(tmp_docx_path)
                os.unlink(tmp_pdf_path)
                
                filename = f"Angebotsanfrage_{angebotsanfrage_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
                return (pdf_content, filename, 'application/pdf', True)
        except Exception as e:
            # Temporäre Dateien aufräumen
            if os.path.exists(tmp_docx_path):
                try:
                    os.unlink(tmp_docx_path)
                except:
                    pass
            if os.path.exists(tmp_pdf_path):
                try:
                    os.unlink(tmp_pdf_path)
                except:
                    pass
            
            # COM aufräumen (Windows)
            if sys.platform == 'win32':
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except:
                    pass
    
    # Fallback: DOCX zurückgeben
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    filename = f"Angebotsanfrage_{angebotsanfrage_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    return (buffer.getvalue(), filename, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', False)

