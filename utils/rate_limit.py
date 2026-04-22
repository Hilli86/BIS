"""
Rate-Limiting (flask-limiter)

Globale Limiter-Instanz. Wird in app.py mit `limiter.init_app(app)`
gebunden. Für Login und WebAuthn-Verify werden Dekoratoren in
`modules/auth/routes.py` genutzt.

Schlüssel:
- `login_ratelimit_key`: IP + Personalnummer (Form- oder JSON-Body),
  damit parallele Angriffe gegen verschiedene Nutzer aus derselben IP
  einzeln gezählt werden.

Storage-Backend: Standard ist `memory://` (pro Prozess). Für Multi-Worker-
Betrieb (Gunicorn) muss ein geteilter Store genutzt werden, typischerweise
Redis. Konfiguration über `RATELIMIT_STORAGE_URI` in der App-Config (z. B.
`redis://Redis-Service:6379/0`). `Limiter.init_app(app)` liest diesen Wert
automatisch aus `app.config`.
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
    strategy='fixed-window',
)
