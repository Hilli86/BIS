"""Blueprint Wartungen."""

from flask import Blueprint

wartungen_bp = Blueprint(
    'wartungen',
    __name__,
    url_prefix='/wartungen',
    template_folder='templates',
)

from . import routes  # noqa: E402, F401
