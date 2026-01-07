"""
PDF Export Utilities - Gemeinsame PDF-Konvertierungs-Funktionen
"""

import os
import subprocess
import shutil
import sys

try:
    from docx2pdf import convert
    DOCX2PDF_AVAILABLE = True
except ImportError:
    DOCX2PDF_AVAILABLE = False


def convert_docx_to_pdf(docx_path, pdf_path):
    """
    Konvertiert eine DOCX-Datei zu PDF.
    Versucht zuerst docx2pdf (Windows), dann LibreOffice (Linux/Cross-Platform).
    """
    # Methode 1: docx2pdf (funktioniert auf Windows mit Word)
    if DOCX2PDF_AVAILABLE:
        try:
            # COM-Initialisierung für Windows
            if sys.platform == 'win32':
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except ImportError:
                    pass
            
            convert(docx_path, pdf_path)
            
            # COM aufräumen (Windows)
            if sys.platform == 'win32':
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except:
                    pass
            
            # Prüfen ob PDF erstellt wurde
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                return True
        except Exception as e:
            # Weiter zu LibreOffice
            pass
    
    # Methode 2: LibreOffice (funktioniert auf Linux und Windows)
    libreoffice_cmd = None
    if sys.platform == 'win32':
        # Windows: Suche nach LibreOffice
        possible_paths = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                libreoffice_cmd = path
                break
    else:
        # Linux/Unix: Suche nach LibreOffice
        libreoffice_cmd = shutil.which('libreoffice') or shutil.which('soffice')
        
        # Falls nicht im PATH, bekannte Linux-Pfade prüfen
        if not libreoffice_cmd:
            possible_paths = [
                '/usr/bin/libreoffice',
                '/usr/bin/soffice',
                '/usr/local/bin/libreoffice',
                '/usr/local/bin/soffice',
                '/snap/bin/libreoffice',
                '/opt/libreoffice*/program/soffice',
            ]
            for path in possible_paths:
                # Unterstützung für Wildcards
                if '*' in path:
                    import glob
                    matches = glob.glob(path)
                    if matches:
                        path = matches[0]
                
                if os.path.exists(path) and os.access(path, os.X_OK):
                    libreoffice_cmd = path
                    break
    
    if not libreoffice_cmd:
        print("LibreOffice nicht gefunden. Bitte installieren Sie LibreOffice.")
        return False
    
    try:
        # LibreOffice im headless-Modus für Konvertierung
        output_dir = os.path.dirname(pdf_path)
        cmd = [
            libreoffice_cmd,
            '--headless',
            '--nodefault',
            '--nolockcheck',
            '--invisible',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            docx_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        # Prüfen ob PDF erstellt wurde
        expected_pdf = os.path.join(output_dir, os.path.splitext(os.path.basename(docx_path))[0] + '.pdf')
        if os.path.exists(expected_pdf) and os.path.getsize(expected_pdf) > 0:
            # PDF an gewünschten Ort verschieben
            if expected_pdf != pdf_path:
                shutil.move(expected_pdf, pdf_path)
            return True
        
        return False
    except Exception as e:
        print(f"Fehler bei LibreOffice-Konvertierung: {e}")
        return False

