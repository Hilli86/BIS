"""
CSRF-Schutz (Flask-WTF)

Globale CSRFProtect-Instanz. In app.py wird sie mit `csrf.init_app(app)`
an die App gebunden. Einzelne JSON-APIs (z.B. Service-Worker) koennen per
`@csrf.exempt` ausgenommen werden, sofern sie nicht session-basiert sind.
"""

from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
