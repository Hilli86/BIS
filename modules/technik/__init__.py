"""
Technik-Modul (Layouts, Übersichten)
"""

from flask import Blueprint

technik_bp = Blueprint(
    'technik',
    __name__,
    url_prefix='/technik',
    template_folder='templates',
)

from . import routes

__all__ = ['technik_bp']
