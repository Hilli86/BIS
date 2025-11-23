"""
Ersatzteile Module - Ersatzteilverwaltung
"""

from flask import Blueprint
import importlib.util
from pathlib import Path

ersatzteile_bp = Blueprint('ersatzteile', __name__, 
                          url_prefix='/ersatzteile',
                          template_folder='templates')

# Importiere routes.py direkt (umgeht das routes/ Verzeichnis)
routes_py_path = Path(__file__).parent / 'routes.py'
if routes_py_path.exists():
    spec = importlib.util.spec_from_file_location("modules.ersatzteile.routes", routes_py_path)
    if spec and spec.loader:
        routes_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(routes_module)

