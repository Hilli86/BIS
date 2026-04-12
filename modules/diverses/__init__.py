"""
Diverses Module
Verschiedene Funktionen und Tools
"""

from flask import Blueprint

diverses_bp = Blueprint(
    'diverses', __name__, url_prefix='/diverses', template_folder='templates'
)

from . import routes

__all__ = ['diverses_bp']

