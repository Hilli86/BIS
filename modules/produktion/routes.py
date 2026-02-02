"""
Produktion Routes
Routes für Produktionsfunktionen
"""

from flask import render_template
from . import produktion_bp
from utils.decorators import login_required, guest_allowed


@produktion_bp.route('/etikettierung')
@guest_allowed  # Muss ZUERST stehen, damit Attribut gesetzt wird
@login_required  # Prüft dann das Attribut
def etikettierung():
    """Etikettierung-Seite"""
    return render_template('produktion/etikettierung.html')
