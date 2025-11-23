"""
Utils Package - Hilfsfunktionen für BIS
"""

from .database import get_db_connection
from .decorators import login_required, admin_required, permission_required
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
from .firmendaten import get_firmendaten
from .berechtigungen import (
    hat_berechtigung,
    ist_admin,
    get_mitarbeiter_berechtigungen,
    get_alle_berechtigungen,
    mitarbeiter_berechtigung_hinzufuegen,
    mitarbeiter_berechtigung_entfernen
)
from .helpers import (
    row_to_dict,
    build_sichtbarkeits_filter_query,
    build_ersatzteil_zugriff_filter,
    format_file_size
)
from .file_handling import (
    validate_file_extension,
    create_upload_folder,
    get_file_list,
    save_uploaded_file,
    move_file_safe
)

__all__ = [
    'get_db_connection',
    'login_required',
    'admin_required',
    'permission_required',
    'get_untergeordnete_abteilungen',
    'get_mitarbeiter_abteilungen',
    'get_sichtbare_abteilungen_fuer_mitarbeiter',
    'get_direkte_unterabteilungen',
    'get_auswaehlbare_abteilungen_fuer_mitarbeiter',
    'get_auswaehlbare_abteilungen_fuer_neues_thema',
    'erstelle_benachrichtigung_fuer_bemerkung',
    'erstelle_benachrichtigung_fuer_neues_thema',
    'get_firmendaten',
    'hat_berechtigung',
    'ist_admin',
    'get_mitarbeiter_berechtigungen',
    'get_alle_berechtigungen',
    'mitarbeiter_berechtigung_hinzufuegen',
    'mitarbeiter_berechtigung_entfernen',
    'row_to_dict',
    'build_sichtbarkeits_filter_query',
    'build_ersatzteil_zugriff_filter',
    'format_file_size',
    'validate_file_extension',
    'create_upload_folder',
    'get_file_list',
    'save_uploaded_file',
    'move_file_safe'
]

