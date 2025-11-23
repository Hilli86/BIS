"""
Ersatzteile Utilities
Gemeinsame Hilfsfunktionen für das Ersatzteile-Modul
"""

from .file_handling import get_datei_anzahl, get_bestellung_dateien, get_angebotsanfrage_dateien, get_auftragsbestätigung_dateien, get_lieferschein_dateien
from .helpers import safe_get, hat_ersatzteil_zugriff

__all__ = [
    'get_datei_anzahl',
    'get_bestellung_dateien',
    'get_angebotsanfrage_dateien',
    'get_auftragsbestätigung_dateien',
    'get_lieferschein_dateien',
    'safe_get',
    'hat_ersatzteil_zugriff'
]

