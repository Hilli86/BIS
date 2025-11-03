"""
Schichtbuch Module - Themenverwaltung, Bemerkungen
"""

from flask import Blueprint

schichtbuch_bp = Blueprint('schichtbuch', __name__, 
                          url_prefix='/schichtbuch',
                          template_folder='templates')

from . import routes

