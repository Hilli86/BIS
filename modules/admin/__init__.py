"""
Admin Module - Stammdaten-Verwaltung
Mitarbeiter, Abteilungen, Bereiche, Gewerke, Tätigkeiten, Status
"""

from flask import Blueprint

admin_bp = Blueprint('admin', __name__, 
                    url_prefix='/admin',
                    template_folder='templates')

from . import routes

