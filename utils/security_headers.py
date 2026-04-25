"""
Zentrale Initialisierung von Security-Headern via Flask-Talisman.

- CSP erlaubt Bootstrap/Icons-CDN, Google Fonts und eigene Assets.
- `unsafe-inline` f?r Styles bleibt vorerst erhalten (viele bestehende
  Inline-`style`-Attribute); Skripte werden per Nonce erlaubt.
- HSTS wird nur in Produktion erzwungen (HTTPS-Deployment).
"""

from __future__ import annotations

from flask_talisman import Talisman


# Externe Quellen fuer OpenCV.js (Skript + WASM/Fetch vom selben CDN) der
# Dokumenterfassung - alle anderen Vendor-Assets liegen lokal unter /static/vendor/.
_OPENCV_CDNS = (
    'https://cdn.jsdelivr.net',
    'https://unpkg.com',
)


def init_security_headers(app) -> Talisman:
    """Bindet Talisman an die App und liefert die Instanz zur?ck."""
    is_prod = app.config.get('FLASK_ENV_EFFECTIVE') == 'production' or not app.debug

    # HINWEIS: Die Templates enthalten zahlreiche inline-<script>-Bloecke und
    # inline-Event-Handler (onclick, onsubmit, onchange, ...) � insbesondere in
    # den Listen-Templates fuer Zeilennavigation. Damit diese weiterhin
    # funktionieren, wird 'unsafe-inline' fuer `script-src` zugelassen und
    # bewusst KEIN Nonce eingesetzt: Aktiviert man Nonces, ignorieren moderne
    # Browser laut CSP-Spec 'unsafe-inline' automatisch, wodurch alle inline
    # Handler abgewiesen wuerden. Spaetere Haertung: Inline-Handler schrittweise
    # durch addEventListener ersetzen, dann Nonces reaktivieren.
    csp = {
        'default-src': "'self'",
        'script-src': [
            "'self'",
            "'unsafe-inline'",
            "'unsafe-eval'",
            *_OPENCV_CDNS,
        ],
        'script-src-attr': ["'unsafe-inline'"],
        'style-src': [
            "'self'",
            "'unsafe-inline'",
        ],
        'img-src': ["'self'", 'data:', 'blob:'],
        'font-src': ["'self'", 'data:'],
        # OpenCV.js laedt WASM per fetch() vom CDN - Hosts in connect-src erlauben.
        'connect-src': ["'self'", *_OPENCV_CDNS],
        'frame-ancestors': "'self'",
        'base-uri': "'self'",
        'form-action': "'self'",
        # Technik-�bersichten: SVG per <object> von /static/ (Hotspots via contentDocument)
        'object-src': "'self'",
        # Emscripten/OpenCV nutzt haefig Worker mit blob:-URLs
        'worker-src': ["'self'", "'blob:'"],
        'manifest-src': "'self'",
    }

    talisman = Talisman(
        app,
        content_security_policy=csp,
        content_security_policy_nonce_in=[],
        force_https=is_prod and app.config.get('PREFERRED_URL_SCHEME', 'https') == 'https',
        strict_transport_security=is_prod,
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        session_cookie_secure=bool(app.config.get('SESSION_COOKIE_SECURE', False)),
        session_cookie_http_only=True,
        referrer_policy='same-origin',
        frame_options='SAMEORIGIN',
        x_content_type_options=True,
    )
    return talisman
