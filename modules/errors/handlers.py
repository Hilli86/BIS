"""
Error Handlers
Zentrale Fehlerbehandlung für 404, 500 etc.
"""

from flask import render_template
from . import errors_bp


@errors_bp.app_errorhandler(404)
def not_found_error(error):
    """404 Fehlerseite"""
    return render_template('errors/404.html'), 404


@errors_bp.app_errorhandler(500)
def internal_error(error):
    """500 Fehlerseite"""
    return render_template('errors/500.html'), 500

