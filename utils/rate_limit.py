"""
Rate-Limiting (flask-limiter)

Globale Limiter-Instanz. Wird in app.py mit `limiter.init_app(app)`
gebunden. Für Login und WebAuthn-Verify werden Dekoratoren in
`modules/auth/routes.py` genutzt.

Schlüssel:
- `login_ratelimit_key`: IP + Personalnummer (Form- oder JSON-Body),
  damit parallele Angriffe gegen verschiedene Nutzer aus derselben IP
  einzeln gezählt werden.
"""

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def login_ratelimit_key() -> str:
    """Kombiniert IP und Personalnummer für Login-Routen."""
    personalnummer = (request.form.get('personalnummer') or '').strip()
    if not personalnummer:
        try:
            data = request.get_json(silent=True) or {}
            personalnummer = str(data.get('personalnummer') or '').strip()
        except Exception:
            personalnummer = ''
    return f'{get_remote_address()}|{personalnummer or "-"}'


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri='memory://',
    strategy='fixed-window',
)
