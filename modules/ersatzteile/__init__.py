"""
Ersatzteile Module - Ersatzteilverwaltung
"""

from flask import Blueprint

ersatzteile_bp = Blueprint('ersatzteile', __name__, 
                          url_prefix='/ersatzteile',
                          template_folder='templates')

# Importiere alle Routes aus dem routes/ Verzeichnis
from .routes import (
    ersatzteil_routes,
    lagerbuchung_routes,
    angebotsanfrage_routes,
    bestellung_routes,
    wareneingang_routes,
    lieferant_routes,
    auswertungen_routes
)

