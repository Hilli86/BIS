"""
Bestellung Report - PDF/DOCX-Generierung für Bestellungen
"""

from datetime import datetime
import os
import base64
import tempfile
import sys
from io import BytesIO
from flask import current_app
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from utils.firmendaten import get_firmendaten
from modules.ersatzteile.utils.helpers import safe_get
from .pdf_export import convert_docx_to_pdf

try:
    from docx2pdf import convert
    DOCX2PDF_AVAILABLE = True
except ImportError:
    DOCX2PDF_AVAILABLE = False


def generate_bestellung_pdf(bestellung_id, conn):
    """
    Generiert ein PDF/DOCX für eine Bestellung.
    Gibt ein Tupel zurück: (content: bytes, filename: str, mimetype: str, is_pdf: bool)
    """
    # Bestellung laden
    bestellung = conn.execute("""
        SELECT 
            b.*,
            l.Name AS LieferantName,
            l.Strasse AS LieferantStrasse,
            l.PLZ AS LieferantPLZ,
            l.Ort AS LieferantOrt,
            l.Telefon AS LieferantTelefon,
            l.Email AS LieferantEmail,
            m1.Vorname || ' ' || m1.Nachname AS ErstelltVon,
            m1.Email AS ErstelltVonEmail,
            m1.Handynummer AS ErstelltVonHandy,
            m2.Vorname || ' ' || m2.Nachname AS FreigegebenVon,
            m3.Vorname || ' ' || m3.Nachname AS BestelltVon,
            abt.Bezeichnung AS FreigegebenVonAbteilung
        FROM Bestellung b
        LEFT JOIN Lieferant l ON b.LieferantID = l.ID
        LEFT JOIN Mitarbeiter m1 ON b.ErstelltVonID = m1.ID
        LEFT JOIN Mitarbeiter m2 ON b.FreigegebenVonID = m2.ID
        LEFT JOIN Mitarbeiter m3 ON b.BestelltVonID = m3.ID
        LEFT JOIN Abteilung abt ON m2.PrimaerAbteilungID = abt.ID
        WHERE b.ID = ?
    """, (bestellung_id,)).fetchone()
    
    if not bestellung:
        raise ValueError('Bestellung nicht gefunden.')
    
    if bestellung['Status'] not in ['Freigegeben', 'Bestellt']:
        raise ValueError('PDF kann nur für freigegebene oder bestellte Bestellungen generiert werden.')
    
    # Positionen laden
    positionen = conn.execute("""
        SELECT 
            p.*,
            e.ID AS ErsatzteilID,
            COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
            COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
            COALESCE(e.Einheit, 'Stück') AS Einheit
        FROM BestellungPosition p
        LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
        WHERE p.BestellungID = ?
        ORDER BY p.ID
    """, (bestellung_id,)).fetchall()
    
    # Firmendaten laden
    firmendaten = get_firmendaten()
    
    # Template-Pfad
    template_path = os.path.join(current_app.root_path, 'templates', 'reports', 'bestellung_template.docx')
    if not os.path.exists(template_path):
        raise FileNotFoundError('Bestellungsvorlage nicht gefunden.')
    
    # Template laden
    doc = DocxTemplate(template_path)
    
    # Datum formatieren
    datum = ''
    if bestellung['ErstelltAm']:
        try:
            datum = datetime.strptime(bestellung['ErstelltAm'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        except:
            datum = bestellung['ErstelltAm'][:10] if bestellung['ErstelltAm'] else ''
    
    freigabe_datum = ''
    freigegeben_am = safe_get(bestellung, 'FreigegebenAm')
    if freigegeben_am:
        try:
            freigabe_datum = datetime.strptime(freigegeben_am, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
        except:
            freigabe_datum = freigegeben_am[:16] if freigegeben_am else ''
    
    # Kontaktdaten des Erstellers zusammenstellen
    kontakt_details = []
    erstellt_von_email = safe_get(bestellung, 'ErstelltVonEmail')
    erstellt_von_handy = safe_get(bestellung, 'ErstelltVonHandy')
    if erstellt_von_email:
        kontakt_details.append(f"E-Mail: {erstellt_von_email}")
    if erstellt_von_handy:
        kontakt_details.append(f"Tel: {erstellt_von_handy}")
    kontakt_text = ' | '.join(kontakt_details) if kontakt_details else ''
    
    # Positionen für Template vorbereiten mit Gesamtpreis
    positionen_liste = []
    gesamtbetrag = 0
    waehrung = 'EUR'
    
    for idx, pos in enumerate(positionen, 1):
        artikel_nr = pos['Bestellnummer'] or '-'
        bezeichnung = pos['Bezeichnung'] or '-'
        menge_val = pos['Menge'] if pos['Menge'] else 0
        preis_val = pos['Preis'] if pos['Preis'] else 0
        gesamt_preis = menge_val * preis_val
        gesamtbetrag += gesamt_preis
        
        pos_waehrung = safe_get(pos, 'Waehrung')
        if pos_waehrung:
            waehrung = pos_waehrung
        
        einheit = safe_get(pos, 'Einheit', 'Stück')
        # Menge formatieren: Ganze Zahlen ohne Kommastellen, mit Einheit
        if menge_val == int(menge_val):
            menge_text = f"{int(menge_val)} {einheit}"
        else:
            menge_text = f"{menge_val} {einheit}"
        
        positionen_liste.append({
            'position': idx,
            'artikelnummer': artikel_nr,
            'bezeichnung': bezeichnung,
            'menge': menge_text,
            'preis': f"{preis_val:.2f}",
            'gesamtpreis': f"{gesamt_preis:.2f}",
            'waehrung': waehrung
        })
    
    # Unterschrift als Bild vorbereiten (falls vorhanden)
    unterschrift_img = None
    tmp_img_path = None
    unterschrift_data_raw = safe_get(bestellung, 'Unterschrift')
    if unterschrift_data_raw:
        try:
            unterschrift_data = unterschrift_data_raw
            if unterschrift_data.startswith('data:image'):
                unterschrift_data = unterschrift_data.split(',')[1] if ',' in unterschrift_data else unterschrift_data
            
            img_data = base64.b64decode(unterschrift_data)
            
            # Temporäres Bild speichern für InlineImage
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_img:
                tmp_img.write(img_data)
                tmp_img_path = os.path.abspath(tmp_img.name)
            
            # Prüfen ob Datei existiert und lesbar ist
            if not os.path.exists(tmp_img_path):
                raise Exception(f"Temporäres Bild konnte nicht erstellt werden: {tmp_img_path}")
            
            # Dateigröße prüfen
            file_size = os.path.getsize(tmp_img_path)
            if file_size == 0:
                raise Exception(f"Temporäres Bild ist leer: {tmp_img_path}")
            
            # InlineImage erstellen
            unterschrift_img = InlineImage(doc, tmp_img_path, width=Mm(80))
            
            if current_app.config.get('DEBUG'):
                print(f"Unterschrift erfolgreich vorbereitet: {tmp_img_path}, Größe: {len(img_data)} bytes")
        except Exception as e:
            print(f"Fehler beim Vorbereiten der Unterschrift: {e}")
            import traceback
            traceback.print_exc()
            unterschrift_img = None
            if tmp_img_path and os.path.exists(tmp_img_path):
                try:
                    os.unlink(tmp_img_path)
                except:
                    pass
            tmp_img_path = None
    
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
        # Bestellungs-Daten
        'bestellung_id': bestellung['ID'],
        'bestellnummer': safe_get(bestellung, 'Bestellnummer', ''),
        'datum': datum,
        'erstellt_von': safe_get(bestellung, 'ErstelltVon', ''),
        'erstellt_von_kontakt': kontakt_text,
        'status': safe_get(bestellung, 'Status', ''),
        'bemerkung': safe_get(bestellung, 'Bemerkung', ''),
        'freigabe_bemerkung': safe_get(bestellung, 'FreigabeBemerkung', ''),
        
        # Lieferant-Daten
        'lieferant_name': bestellung['LieferantName'] or '',
        'lieferant_strasse': bestellung['LieferantStrasse'] or '',
        'lieferant_plz': bestellung['LieferantPLZ'] or '',
        'lieferant_ort': bestellung['LieferantOrt'] or '',
        'lieferant_plz_ort': f"{bestellung['LieferantPLZ'] or ''} {bestellung['LieferantOrt'] or ''}".strip(),
        'lieferant_telefon': bestellung['LieferantTelefon'] or '',
        'lieferant_email': bestellung['LieferantEmail'] or '',
        
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
        'gesamtbetrag': f"{gesamtbetrag:.2f}",
        'waehrung': waehrung,
        
        # Freigabe-Daten
        'freigegeben_von': safe_get(bestellung, 'FreigegebenVon', ''),
        'freigegeben_von_abteilung': safe_get(bestellung, 'FreigegebenVonAbteilung', ''),
        'freigegeben_am': freigabe_datum,
        'hat_unterschrift': unterschrift_img is not None,
        'unterschrift': unterschrift_img,
    }
    
    # Template rendern
    doc.render(context)
    
    # Temporäres Bild löschen (nach dem Rendern)
    if tmp_img_path and os.path.exists(tmp_img_path):
        try:
            os.unlink(tmp_img_path)
        except:
            pass
    
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
                
                filename = f"Bestellung_{bestellung_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
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
    filename = f"Bestellung_{bestellung_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    return (buffer.getvalue(), filename, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', False)

