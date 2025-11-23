"""
Ersatzteile Routes Package
Alle Route-Module werden hier importiert und registriert

WICHTIG: Solange die Routen noch in routes.py sind, müssen wir diese importieren.
Sobald die Routen in die einzelnen Dateien migriert sind, können wir diese Imports entfernen.
"""

# Importiere die ursprüngliche routes.py (die Routen sind noch dort)
# Wir verwenden importlib, um die routes.py explizit zu importieren
import importlib.util
import sys
from pathlib import Path

# Pfad zur routes.py im übergeordneten Verzeichnis
routes_py_path = Path(__file__).parent.parent / 'routes.py'
if routes_py_path.exists():
    # Importiere die routes.py als Modul
    spec = importlib.util.spec_from_file_location("modules.ersatzteile.routes_module", routes_py_path)
    if spec and spec.loader:
        routes_module = importlib.util.module_from_spec(spec)
        sys.modules["modules.ersatzteile.routes_module"] = routes_module
        spec.loader.exec_module(routes_module)

# Platzhalter für zukünftige Route-Module (noch nicht aktiv)
# from . import ersatzteil_routes
# from . import bestellung_routes
# from . import angebotsanfrage_routes
# from . import wareneingang_routes
# from . import lagerbuchung_routes
# from . import lieferant_routes

__all__ = []

