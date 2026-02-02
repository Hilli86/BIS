"""
Produktion Module
Produktionsfunktionen wie Etikettierung
"""

from flask import Blueprint

produktion_bp = Blueprint('produktion', __name__, url_prefix='/produktion')

from . import routes

__all__ = ['produktion_bp']
