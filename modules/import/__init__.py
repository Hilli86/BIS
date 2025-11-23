"""
Import Module
Datei-Import-Funktionalität
"""

from flask import Blueprint

import_bp = Blueprint('import', __name__, url_prefix='/api/import')

from . import routes

__all__ = ['import_bp']

