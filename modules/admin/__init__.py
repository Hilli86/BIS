"""
Admin Module - Stammdaten-Verwaltung
Mitarbeiter, Abteilungen, Bereiche, Gewerke, Tätigkeiten, Status
"""

from flask import Blueprint

admin_bp = Blueprint('admin', __name__, 
                    url_prefix='/admin',
                    template_folder='templates')


@admin_bp.context_processor
def _bis_admin_shell():
    return {'bis_admin_shell': True}


from . import routes

