"""
Error Handler Module
Zentrale Fehlerbehandlung für die gesamte Anwendung
"""

from flask import Blueprint

errors_bp = Blueprint('errors', __name__)

from . import handlers

