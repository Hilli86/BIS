"""
Ersatzteile Module - Ersatzteilverwaltung
"""

from flask import Blueprint

ersatzteile_bp = Blueprint('ersatzteile', __name__, 
                          url_prefix='/ersatzteile',
                          template_folder='templates')

from . import routes

