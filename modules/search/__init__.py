"""
Search Module - Globale Suche über alle Entitäten
"""

from flask import Blueprint

search_bp = Blueprint('search', __name__, url_prefix='/search')

from . import routes

__all__ = ['search_bp']
