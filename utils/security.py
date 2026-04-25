"""
Sicherheits-Utilities  Pfad-Auflsung, Farbvalidierung.

Zentraler Helfer `resolve_under_base` sorgt dafr, dass Dateioperationen
ausschlielich innerhalb eines erlaubten Basispfads stattfinden (Schutz
vor Path-Traversal, auch unter Windows).
"""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urlparse, urljoin

from flask import request


class PathTraversalError(ValueError):
    """Wird geworfen, wenn ein aufgelster Pfad auerhalb des Basispfads liegt."""


def resolve_under_base(base_path: str, relative_path: str) -> str:
    """Gibt den absoluten Pfad zurck, wenn er innerhalb `base_path` liegt.

    - Normalisiert Slash/Backslash und entfernt fhrende Separatoren.
    - Verbietet Null-Bytes und leere Komponenten.
    - Nutzt `realpath` (folgt Symlinks) und `commonpath` fr den
      Containment-Check, damit Gro-/Kleinschreibung unter Windows
      korrekt behandelt wird.

    Raises:
        PathTraversalError: wenn der aufgelste Pfad nicht unter
        `base_path` liegt oder ungltige Zeichen enthlt.
    """
    if relative_path is None:
        raise PathTraversalError('Relativer Pfad fehlt.')
    if '\x00' in relative_path or '\x00' in base_path:
        raise PathTraversalError('Null-Byte im Pfad.')

    normalized = relative_path.replace('\\', '/').lstrip('/')
    if not normalized:
        raise PathTraversalError('Leerer Pfad.')

    filesystem_path = normalized.replace('/', os.sep)
    joined = os.path.join(base_path, filesystem_path)

    base_real = os.path.realpath(base_path)
    target_real = os.path.realpath(joined)

    try:
        common = os.path.commonpath([base_real, target_real])
    except ValueError as exc:
        raise PathTraversalError(f'Pfadvergleich nicht mglich: {exc}') from exc

    if os.path.normcase(common) != os.path.normcase(base_real):
        raise PathTraversalError(
            f'Pfad auerhalb des erlaubten Basisordners: {relative_path}'
        )

    return target_real


_COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')


def validate_css_color(value: Optional[str], fallback: str = 'inherit') -> str:
    """Gibt `value` zurck, wenn es eine sichere Hex-Farbe ist, sonst `fallback`.

    Erlaubt sind nur Werte wie `#abc`, `#abcd`, `#aabbcc`, `#aabbccdd`
    oder der String `inherit`/`transparent`. Damit wird CSS-Injection
    ber z.B. `url(...)` in Style-Attributen ausgeschlossen.
    """
    if not value:
        return fallback
    v = str(value).strip()
    if v in ('inherit', 'transparent', 'currentColor', 'currentcolor'):
        return v
    if _COLOR_RE.match(v):
        return v
    return fallback


def is_safe_url(target: Optional[str]) -> bool:
    """Prueft, ob ein Redirect-Ziel sicher ist (gleiche Host-URL, http/https).

    Verhindert Open-Redirects, wenn Werte aus `next`-Parametern oder
    `request.referrer` verwendet werden.
    """
    if not target:
        return False
    try:
        ref_url = urlparse(request.host_url)
        test_url = urlparse(urljoin(request.host_url, target))
    except Exception:
        return False
    if test_url.scheme not in ('http', 'https'):
        return False
    if ref_url.netloc != test_url.netloc:
        return False
    return True


def safe_redirect_target(target: Optional[str], fallback: str) -> str:
    """Liefert `target` zurueck, wenn `is_safe_url(target)` True ist, sonst `fallback`."""
    return target if is_safe_url(target) else fallback


PASSWORT_MIN_LAENGE = 10


def _passwort_policy_streng_laut_config() -> bool:
    """True = volle Policy; False = nur nicht-leer (siehe config PASSWORT_POLICY_STRENG).

    Ohne Flask-App-Kontext (Skripte/Tests): immer streng, damit bestehende Tests gelten.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            return bool(current_app.config.get('PASSWORT_POLICY_STRENG', True))
    except Exception:
        pass
    return True


def validate_passwort_policy(passwort: Optional[str]) -> Optional[str]:
    """Prueft ein Passwort gegen die Policy.

    Gibt None zurueck, wenn das Passwort akzeptiert ist, ansonsten eine
    deutschsprachige Fehlermeldung fuer den Nutzer.

    Ist ``current_app.config['PASSWORT_POLICY_STRENG']`` False, gilt nur: Passwort
    darf nicht leer sein (Whitespace zaehlt als leer).

    Sonst (strenge Policy):
    - Mindestens `PASSWORT_MIN_LAENGE` Zeichen (10)
    - Mindestens drei der vier Zeichenklassen:
      Kleinbuchstabe, Grossbuchstabe, Ziffer, Sonderzeichen
    - Keine reinen Wiederholungen (z. B. "aaaaaaaaaa")
    """
    if not _passwort_policy_streng_laut_config():
        if passwort is None or not str(passwort).strip():
            return 'Bitte ein Passwort eingeben.'
        return None
    if passwort is None:
        return 'Bitte ein Passwort eingeben.'
    if len(passwort) < PASSWORT_MIN_LAENGE:
        return f'Das Passwort muss mindestens {PASSWORT_MIN_LAENGE} Zeichen lang sein.'
    klassen = 0
    if re.search(r'[a-z]', passwort):
        klassen += 1
    if re.search(r'[A-Z]', passwort):
        klassen += 1
    if re.search(r'\d', passwort):
        klassen += 1
    if re.search(r'[^A-Za-z0-9]', passwort):
        klassen += 1
    if klassen < 3:
        return (
            'Das Passwort muss mindestens drei der folgenden Zeichenklassen '
            'enthalten: Kleinbuchstabe, Grossbuchstabe, Ziffer, Sonderzeichen.'
        )
    if len(set(passwort)) <= 2:
        return 'Das Passwort ist zu einfach (zu wenige unterschiedliche Zeichen).'
    return None


def generiere_zufalls_passwort(bytes_: int = 18) -> str:
    """Erzeugt ein starkes, zufaelliges Passwort (URL-safe base64)."""
    import secrets as _secrets
    return _secrets.token_urlsafe(bytes_)
