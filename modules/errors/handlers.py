"""
Error Handlers

Zentrale Fehlerbehandlung für 404, 500 und unbehandelte Exceptions. Stack-
Traces werden ausschließlich ins Log geschrieben, nach außen erhält der
Nutzer eine generische Meldung bzw. eine Fehlerseite. Für AJAX-Clients
wird JSON zurückgegeben, sonst eine HTML-Seite.
"""

from flask import render_template, request, jsonify, current_app
from werkzeug.exceptions import HTTPException

from . import errors_bp


def _wants_json_response() -> bool:
    """Grobe Heuristik: JSON antworten, wenn der Client es akzeptiert bzw. AJAX."""
    if request.path.startswith('/api/'):
        return True
    accept = request.accept_mimetypes
    if accept.best_match(['application/json', 'text/html']) == 'application/json':
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return False


@errors_bp.app_errorhandler(404)
def not_found_error(error):
    """404 Fehlerseite / JSON."""
    if _wants_json_response():
        return jsonify(success=False, error='Nicht gefunden.'), 404
    return render_template('errors/404.html'), 404


@errors_bp.app_errorhandler(500)
def internal_error(error):
    """500 Fehlerseite / JSON (ohne Details nach außen)."""
    current_app.logger.exception('Interner Serverfehler: %s', error)
    if _wants_json_response():
        return jsonify(success=False, error='Interner Fehler.'), 500
    return render_template('errors/500.html'), 500


@errors_bp.app_errorhandler(Exception)
def unhandled_exception(error):
    """Fallback für alle nicht abgefangenen Exceptions."""
    if isinstance(error, HTTPException):
        if _wants_json_response():
            return jsonify(success=False, error=error.description or error.name), error.code
        return error

    current_app.logger.exception('Unbehandelte Exception: %s', error)
    if _wants_json_response():
        return jsonify(success=False, error='Interner Fehler.'), 500
    return render_template('errors/500.html'), 500
