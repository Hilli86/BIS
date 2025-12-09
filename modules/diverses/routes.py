"""
Diverses Routes
Routes für verschiedene Funktionen
"""

from flask import render_template, request, jsonify
from . import diverses_bp
from utils.decorators import permission_required
from utils.zebra_client import send_zpl_to_printer

# Hardcodierte Druckerliste
DRUCKER_LISTE = [
    {'ip': '192.168.1.100', 'bezeichnung': 'BIS-ZD421-01', 'beschreibung': 'Werkstatt Drucker'},
    {'ip': '10.40.40.70', 'bezeichnung': 'BM MORE000011', 'beschreibung': 'Wareneingang 1'},
    {'ip': '10.40.40.71', 'bezeichnung': 'CC MORE000001', 'beschreibung': 'Wareneingang 2'},
    {'ip': '10.40.40.75', 'bezeichnung': 'BM MORE000034', 'beschreibung': 'Warenausgang 1'},
    {'ip': '10.40.40.90', 'bezeichnung': 'BM MORE000054', 'beschreibung': 'Warenausgang 2'},
    {'ip': '10.40.40.60', 'bezeichnung': 'BM MORE000024', 'beschreibung': 'L100 IFCO'},
    {'ip': '10.40.40.61', 'bezeichnung': 'BM MORE000025', 'beschreibung': 'L100 2'},
    {'ip': '10.40.40.62', 'bezeichnung': 'BM MORE000027', 'beschreibung': 'L200 IFCO'},
    {'ip': '10.40.40.63', 'bezeichnung': 'BM MORE000026', 'beschreibung': 'L200 2'},
    {'ip': '10.40.40.67', 'bezeichnung': 'BM MORE000030', 'beschreibung': 'L400 IFCO'},
    {'ip': '10.40.40.66', 'bezeichnung': 'BM MORE000031', 'beschreibung': 'L400 2'},
    {'ip': '10.40.40.64', 'bezeichnung': 'BM MORE000028', 'beschreibung': 'L500 IFCO'},
    {'ip': '10.40.40.65', 'bezeichnung': 'BM MORE000029', 'beschreibung': 'L500 2'},
    {'ip': '10.40.40.100', 'bezeichnung': 'CC MORE000013', 'beschreibung': 'Quako CC EVE'},
    {'ip': '10.40.40.101', 'bezeichnung': 'CC MORE000014', 'beschreibung': 'Quako CC GVE'},
    {'ip': '10.40.40.102', 'bezeichnung': 'CC MORE000015', 'beschreibung': 'Quako CC SSCC'},
    {'ip': '10.40.40.81', 'bezeichnung': 'BM MORE000043', 'beschreibung': 'Quako Moussee'},
]


@diverses_bp.route('/zebra-drucker')
@permission_required('zebra_drucker_produktion')
def zebra_drucker():
    """Zebra-Drucker Seite"""
    return render_template('diverses/zebra_drucker.html', drucker_liste=DRUCKER_LISTE)


@diverses_bp.route('/zebra-drucker/kalibrieren', methods=['POST'])
@permission_required('zebra_drucker_produktion')
def zebra_drucker_kalibrieren():
    """Kalibrierung an Zebra-Drucker senden"""
    data = request.get_json()
    printer_ip = data.get('ip', '').strip()
    
    if not printer_ip:
        return jsonify({'success': False, 'message': 'IP-Adresse fehlt'}), 400
    
    try:
        # ZPL-Befehl für Kalibrierung: ^JC (Print Configuration Label)
        # Format: ^XA (Start), ^JC (Print Config Label), ^XZ (End)
        # Viele Drucker benötigen ein Newline am Ende
        zpl_command = "^XA~JC^XZ"
        send_zpl_to_printer(printer_ip, zpl_command)
        return jsonify({'success': True, 'message': f'Kalibrierung an {printer_ip} gesendet'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Senden: {str(e)}'}), 500


@diverses_bp.route('/zebra-drucker/druckerkonfig', methods=['POST'])
@permission_required('zebra_drucker_produktion')
def zebra_drucker_druckerkonfig():
    """Druckerkonfiguration an Zebra-Drucker senden"""
    data = request.get_json()
    printer_ip = data.get('ip', '').strip()
    
    if not printer_ip:
        return jsonify({'success': False, 'message': 'IP-Adresse fehlt'}), 400
    
    try:
        # ZPL-Befehl für Druckerkonfiguration: ^HH (Print Configuration)
        # Format: ^XA (Start), ^HH (Print Configuration), ^XZ (End)
        # Viele Drucker benötigen ein Newline am Ende
        zpl_command = "^XA~WC^XZ"
        send_zpl_to_printer(printer_ip, zpl_command)
        return jsonify({'success': True, 'message': f'Druckerkonfig an {printer_ip} gesendet'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Senden: {str(e)}'}), 500


@diverses_bp.route('/zebra-drucker/netzwerkkonfig', methods=['POST'])
@permission_required('zebra_drucker_produktion')
def zebra_drucker_netzwerkkonfig():
    """Netzwerkkonfiguration an Zebra-Drucker senden"""
    data = request.get_json()
    printer_ip = data.get('ip', '').strip()
    
    if not printer_ip:
        return jsonify({'success': False, 'message': 'IP-Adresse fehlt'}), 400
    
    try:
        # ZPL-Befehl für Netzwerkkonfiguration: ^HW (Print Network Configuration)
        # Format: ^XA (Start), ^HW (Print Network Config), ^XZ (End)
        # Viele Drucker benötigen ein Newline am Ende
        zpl_command = "^XA~WL^XZ"
        send_zpl_to_printer(printer_ip, zpl_command)
        return jsonify({'success': True, 'message': f'Netzwerkkonfig an {printer_ip} gesendet'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Fehler beim Senden: {str(e)}'}), 500

