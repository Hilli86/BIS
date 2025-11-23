"""
Ersatzteile Routes Package
Alle Route-Module werden hier importiert und registriert
"""

# Route-Module importieren
from . import ersatzteil_routes
from . import lagerbuchung_routes
from . import angebotsanfrage_routes
from . import bestellung_routes
from . import wareneingang_routes
from . import lieferant_routes

__all__ = ['ersatzteil_routes', 'lagerbuchung_routes', 'angebotsanfrage_routes', 'bestellung_routes', 'wareneingang_routes', 'lieferant_routes']

