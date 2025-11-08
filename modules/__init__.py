"""
Modules Package - Alle Blueprints für BIS
"""

from .auth import auth_bp
from .schichtbuch import schichtbuch_bp
from .admin import admin_bp
from .ersatzteile import ersatzteile_bp

__all__ = ['auth_bp', 'schichtbuch_bp', 'admin_bp', 'ersatzteile_bp']

