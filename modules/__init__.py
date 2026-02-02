"""
Modules Package - Alle Blueprints für BIS
"""

from .auth import auth_bp
from .schichtbuch import schichtbuch_bp
from .admin import admin_bp
from .ersatzteile import ersatzteile_bp
from .dashboard import dashboard_bp
from .errors import errors_bp
from .diverses import diverses_bp
from .search import search_bp
from .produktion import produktion_bp
# Import-Modul: import ist ein Python-Schlüsselwort, daher verwenden wir importlib
import importlib
_import_module = importlib.import_module('modules.import')
import_bp = _import_module.import_bp

__all__ = ['auth_bp', 'schichtbuch_bp', 'admin_bp', 'ersatzteile_bp', 'dashboard_bp', 'import_bp', 'errors_bp', 'diverses_bp', 'search_bp', 'produktion_bp']

