"""
Utils Package - Hilfsfunktionen für BIS
"""

from .database import get_db_connection
from .decorators import login_required, admin_required
from .abteilungen import (
    get_untergeordnete_abteilungen,
    get_mitarbeiter_abteilungen,
    get_sichtbare_abteilungen_fuer_mitarbeiter,
    get_direkte_unterabteilungen,
    get_auswaehlbare_abteilungen_fuer_mitarbeiter,
    get_auswaehlbare_abteilungen_fuer_neues_thema
)
from .benachrichtigungen import (
    erstelle_benachrichtigung_fuer_bemerkung,
    erstelle_benachrichtigung_fuer_neues_thema
)

__all__ = [
    'get_db_connection',
    'login_required',
    'admin_required',
    'get_untergeordnete_abteilungen',
    'get_mitarbeiter_abteilungen',
    'get_sichtbare_abteilungen_fuer_mitarbeiter',
    'get_direkte_unterabteilungen',
    'get_auswaehlbare_abteilungen_fuer_mitarbeiter',
    'get_auswaehlbare_abteilungen_fuer_neues_thema',
    'erstelle_benachrichtigung_fuer_bemerkung',
    'erstelle_benachrichtigung_fuer_neues_thema'
]

