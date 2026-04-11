"""
Hilfsfunktionen für Zebra-ZPL-Drucker (Netzwerkdrucker).
"""

import socket
from typing import Optional

# Zebra Standard-Etikettendichte für Dot-Berechnung aus Millimetern
ZPL_DOTS_PER_MM_203 = 203 / 25.4


def zpl_header_from_dimensions(width_mm: int, height_mm: int) -> str:
    """
    Erzeugt den ZPL-Grundheader (^PW, ^LL) aus Breite und Höhe in mm.

    203 dpi: Druckbreite = width_mm, Etikettenlänge (Vorschub) = height_mm.
    """
    w_mm = int(width_mm)
    h_mm = int(height_mm)
    pw = max(1, int(round(w_mm * ZPL_DOTS_PER_MM_203)))
    ll = max(1, int(round(h_mm * ZPL_DOTS_PER_MM_203)))
    return f"^PW{pw}\n^LL{ll}"


def merge_zpl_header_base_and_extra(base_header: str, extra: Optional[str] = None) -> str:
    """Hängt optionale weitere ZPL-Befehle (eigene Zeilen) an den Grundheader an."""
    t = (extra or "").strip()
    if not t:
        return (base_header or "").strip()
    return f"{(base_header or '').strip()}\n{t}"


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

    # Debug: jeder Druckbefehl in der Server-Konsole (Flask/Werkzeug)
    print("===== BIS ZPL-Druck (Debug) =====")
    print(f"Ziel: {printer_ip}:{port}")
    print(zpl)
    print("===== Ende ZPL =====")

    data = zpl.encode("utf-8")
    with socket.create_connection((printer_ip, port), timeout=timeout) as sock:
        sock.sendall(data)


def _test_label_demo_body(label_text: str) -> str:
    """ZPL-Teil nach dem Etikettenformat: Kodierung, Rahmen, Demo-Text, Ende."""
    lines = [
        "^CI28",
        "^FO10,10^GB600,1200,2^FS",
        f"^FO30,60^A0N,40,40^FDTEST {label_text}^FS",
        "^FO30,120^A0N,25,25^FD203 dpi^FS",
        "^XZ",
    ]
    return "\n".join(lines)


def zpl_test_label_preview_segments(zpl_header: str, label_name: Optional[str] = None) -> dict:
    """
    Zerlegt das Testetikett in ZPL-Start, Etikettenformat-Block und Vorschau-Ergänzung.

    Keys: ``full``, ``xa``, ``format``, ``demo`` (letzteres ab ^CI28 bis ^XZ).
    """
    label_text = label_name or "TEST"
    demo = _test_label_demo_body(label_text)
    fmt = zpl_header if zpl_header is not None else ""
    full = "\n".join(["^XA", fmt, demo])
    return {"full": full, "xa": "^XA", "format": fmt, "demo": demo}


def build_test_label(zpl_header: str, label_name: Optional[str] = None) -> str:
    """
    Erstellt ein einfaches Testetikett basierend auf einem ZPL-Header.

    :param zpl_header: ZPL-Header mit ^PW, ^LL und optional weiteren Befehlen
    :param label_name: Optionaler Anzeigename des Etiketts für den TEST-Text
    :return: Vollständiger ZPL-String
    """
    return zpl_test_label_preview_segments(zpl_header, label_name)["full"]


