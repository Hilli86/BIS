"""
Hilfsfunktionen für Zebra-ZPL-Drucker (Netzwerkdrucker).
"""

import socket
from typing import Optional


def send_zpl_to_printer(printer_ip: str, zpl: str, port: int = 9100, timeout: float = 5.0) -> None:
    """
    Sendet einen ZPL-String an einen Zebra-Netzwerkdrucker.

    :param printer_ip: IP-Adresse oder Hostname des Druckers
    :param zpl: Vollständiger ZPL-String (^XA ... ^XZ)
    :param port: TCP-Port (Standard bei Zebra: 9100)
    :param timeout: Socket-Timeout in Sekunden
    """
    if not printer_ip:
        raise ValueError("printer_ip darf nicht leer sein")
    if not zpl:
        raise ValueError("zpl darf nicht leer sein")

    data = zpl.encode("utf-8")
    with socket.create_connection((printer_ip, port), timeout=timeout) as sock:
        sock.sendall(data)


def build_test_label(zpl_header: str, label_name: Optional[str] = None) -> str:
    """
    Erstellt ein einfaches Testetikett basierend auf einem ZPL-Header.

    :param zpl_header: ZPL-Header mit ^PW, ^LL, ^LS usw.
    :param label_name: Optionaler Anzeigename des Etiketts für den TEST-Text
    :return: Vollständiger ZPL-String
    """
    label_text = label_name or "TEST"

    # Sehr einfaches Layout: Rahmen + Text
    # Hinweis: Der Header enthält bereits ^PW/^LL, wir ergänzen nur Inhalt.
    parts = [
        "^XA",
        zpl_header,
        "^CI28",
        # Rahmen (breit/hoch „groß genug“ – passt für unsere 30x30 und 40x160 Beispiele)
        "^FO10,10^GB600,1200,2^FS",
        # Text
        f"^FO30,60^A0N,40,40^FDTEST {label_text}^FS",
        "^FO30,120^A0N,25,25^FD203 dpi^FS",
        "^XZ",
    ]
    return "\n".join(parts)


