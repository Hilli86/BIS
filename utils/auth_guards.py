"""
Auth-Hilfsfunktionen für konsistente Session-Prüfungen.

Hintergrund: Gast-Logins setzen `session['user_id'] = None`, was den
Check `'user_id' not in session` durchläuft und fälschlich als
"eingeloggt" interpretiert wird. Die Helfer hier vereinheitlichen die
Prüfung und ersetzen das alte Muster.
"""

from __future__ import annotations

from typing import Any, Mapping


def is_authenticated_user(session: Mapping[str, Any]) -> bool:
    """True, wenn ein echter Benutzer (kein Gast) eingeloggt ist."""
    if session.get('is_guest'):
        return False
    return bool(session.get('user_id'))


def is_guest(session: Mapping[str, Any]) -> bool:
    """True für Gast-Sessions."""
    return bool(session.get('is_guest'))


def is_authenticated_or_guest(session: Mapping[str, Any]) -> bool:
    """True, sobald eine Session (echter Nutzer oder Gast) vorliegt."""
    return bool(session.get('user_id')) or bool(session.get('is_guest'))
