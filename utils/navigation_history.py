"""
Appweiter Navigationsverlauf in der Session (Pfad inkl. Query = Filterzustand).

Hinweise:
- Der Stack ist pro Browser-Session (nicht tab-isoliert); bei mehreren Tabs
  kann sich die Reihenfolge mischen.
- Views koennen vor ``render_template`` optional ``g.breadcrumb_title`` setzen
  (kurzer deutscher Titel); sonst Fallback aus Endpunkt-Mapping bzw. generisch.
"""

from __future__ import annotations

from typing import Any

from flask import g, request, session, url_for

SESSION_KEY = 'bis_nav_history'
MAX_STACK_ENTRIES = 20
MAX_FULL_PATH_LEN = 2000

# Endpunkte, die nie in den Verlauf sollen (Login, Assets, ...).
EXCLUDED_ENDPOINTS: frozenset[str | None] = frozenset(
    {
        'static',
        'service_worker',
        'auth.login',
        'auth.login_guest',
    }
)

# Haeufige Seiten; erweiterbar ohne Views anzufassen.
ENDPOINT_BREADCRUMB_LABEL: dict[str, str] = {
    'dashboard.dashboard': 'Dashboard',
    'schichtbuch.themaliste': 'Themenliste',
    'schichtbuch.thema_detail': 'Thema',
    'ersatzteile.ersatzteil_liste': 'Artikelliste',
    'ersatzteile.ersatzteil_detail': 'Artikel',
    'ersatzteile.ersatzteil_bearbeiten': 'Artikel bearbeiten',
    'ersatzteile.bestellung_liste': 'Bestellungen',
    'ersatzteile.bestellung_detail': 'Bestellung',
    'ersatzteile.lagerbuchungen_liste': 'Lagerbuchungen',
    'ersatzteile.suche_artikel': 'Suche Artikel',
    'wartungen.wartung_liste': 'Wartungen',
    'wartungen.plaene_uebersicht': 'Wartungspl\u00e4ne',
    'wartungen.jahresuebersicht': 'Jahres\u00fcbersicht',
    'wartungen.durchfuehrung_detail': 'Protokoll',
    'wartungen.durchfuehrung_neu': 'Protokoll erfassen',
    'search.search': 'Suche',
    'admin.index': 'Admin',
    'produktion.etikettierung': 'Etikettierung',
}


def _session_has_navigation_identity() -> bool:
    return bool(session.get('user_id') or session.get('is_guest'))


def _home_url() -> str:
    if session.get('is_guest'):
        return url_for('produktion.etikettierung')
    if session.get('user_id'):
        return url_for('dashboard.dashboard')
    return url_for('auth.login')


def current_full_path(req: Any = None) -> str:
    """Pfad + Query wie im Browser (intern, relativ)."""
    req = req or request
    path = req.path or ''
    if not path.startswith('/'):
        return '/'
    raw_qs = req.query_string
    if raw_qs:
        try:
            qs = raw_qs.decode('utf-8', errors='replace')
        except Exception:
            qs = ''
        return f'{path}?{qs}' if qs else path
    return path


def _safe_path_for_stack(req: Any) -> str | None:
    path = req.path or ''
    if not path.startswith('/') or path.startswith('//'):
        return None
    if path.startswith('/static/'):
        return None
    full = current_full_path(req)
    if len(full) > MAX_FULL_PATH_LEN:
        return None
    if '\r' in full or '\n' in full or '\x00' in full:
        return None
    return full


def _should_consider_recording(req: Any) -> bool:
    if req.method != 'GET':
        return False
    if not _session_has_navigation_identity():
        return False
    ep = req.endpoint
    if ep in EXCLUDED_ENDPOINTS:
        return False
    if ep is None:
        return False
    if ep == 'search.search' and req.args.get('format') == 'json':
        return False
    if _safe_path_for_stack(req) is None:
        return False
    return True


def _label_for_endpoint(endpoint: str | None) -> str:
    if not endpoint:
        return 'Seite'
    if endpoint in ENDPOINT_BREADCRUMB_LABEL:
        return ENDPOINT_BREADCRUMB_LABEL[endpoint]
    short = endpoint.split('.')[-1].replace('_', ' ').strip()
    return short[:1].upper() + short[1:] if short else 'Seite'


def _label_for_entry(entry: dict[str, Any]) -> str:
    t = (entry.get('title') or '').strip()
    if t:
        return _short_label(t)
    return _short_label(_label_for_endpoint(entry.get('endpoint')))


def _short_label(text: str, max_len: int = 40) -> str:
    t = (text or '').strip()
    if len(t) <= max_len:
        return t or 'Seite'
    return t[: max_len - 1] + '...'


def _get_stack() -> list[dict[str, Any]]:
    raw = session.get(SESSION_KEY)
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get('path'), str):
            out.append(
                {
                    'path': item['path'],
                    'endpoint': item.get('endpoint'),
                    'title': item.get('title'),
                }
            )
    return out


def _set_stack(stack: list[dict[str, Any]]) -> None:
    session[SESSION_KEY] = stack
    session.modified = True


def record_navigation_after_request(response: Any) -> None:
    """Nach erfolgreicher HTML-Antwort einen Verlaufseintrag speichern."""
    if not _should_consider_recording(request):
        return
    ct = (response.content_type or '') or ''
    if 'text/html' not in ct.split(';')[0].strip().lower():
        return
    if response.status_code < 200 or response.status_code >= 300:
        return

    safe_path = _safe_path_for_stack(request)
    if not safe_path:
        return

    title = None
    try:
        title = getattr(g, 'breadcrumb_title', None)
    except RuntimeError:
        title = None
    if title is not None:
        title = str(title).strip() or None

    stack = _get_stack()
    if stack and stack[-1].get('path') == safe_path:
        return

    stack.append(
        {
            'path': safe_path,
            'endpoint': request.endpoint,
            'title': title,
        }
    )
    overflow = len(stack) - MAX_STACK_ENTRIES
    if overflow > 0:
        stack = stack[overflow:]
    _set_stack(stack)


def get_previous_url(stack: list[dict[str, Any]] | None = None, req: Any = None) -> str | None:
    """Interne URL der logisch vorherigen Seite (fuer Zurueck-Link)."""
    req = req or request
    stack = stack if stack is not None else _get_stack()
    cur = current_full_path(req)
    if not stack:
        return None
    last = stack[-1].get('path')
    if last != cur:
        return last
    if len(stack) >= 2:
        return stack[-2].get('path')
    return None


def build_breadcrumb_items(stack: list[dict[str, Any]] | None = None, req: Any = None) -> list[dict[str, Any]]:
    """
    Eintraege fuer die Breadcrumb-Zeile: Start, bis zu drei fruehere URLs (ohne
    aktuelle URL), aktuelle Seite (aktiv, ohne href).
    """
    req = req or request
    stack = stack if stack is not None else _get_stack()
    cur = current_full_path(req)

    if not (session.get('user_id') or session.get('is_guest')):
        return []

    past = [e for e in stack if e.get('path') != cur][-3:]

    crumbs: list[dict[str, Any]] = [
        {'href': _home_url(), 'label': 'Start', 'active': False},
    ]
    for e in past:
        p = e.get('path')
        if not isinstance(p, str) or not p.startswith('/'):
            continue
        crumbs.append({'href': p, 'label': _label_for_entry(e), 'active': False})

    cur_title = None
    try:
        cur_title = getattr(g, 'breadcrumb_title', None)
    except RuntimeError:
        cur_title = None
    if cur_title:
        cur_label = _short_label(str(cur_title).strip())
    else:
        cur_label = _short_label(_label_for_endpoint(req.endpoint))

    crumbs.append({'href': None, 'label': cur_label, 'active': True})
    return crumbs


def navigation_history_context() -> dict[str, Any]:
    """Flask context_processor: Template-Variablen fuer Navigation."""
    stack = _get_stack()
    cur = current_full_path(request)
    return {
        'bis_nav_breadcrumbs': build_breadcrumb_items(stack, request),
        'bis_nav_previous_url': get_previous_url(stack, request),
        'bis_nav_current_path': cur,
    }


def clear_navigation_history() -> None:
    """Optional z. B. nach explizitem Verlauf leeren (derzeit nicht genutzt)."""
    session.pop(SESSION_KEY, None)
    session.modified = True
