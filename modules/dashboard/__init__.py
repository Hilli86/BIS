"""
Dashboard Module
Dashboard-Übersicht und API-Endpunkte
"""

from flask import Blueprint

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

from . import routes

__all__ = ['dashboard_bp']

