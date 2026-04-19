"""
Print-Agent REST-API Routes

Endpunkte:

- POST /api/agent/poll       -> naechsten Druckauftrag holen
- POST /api/agent/jobs/<id>/done   -> Auftrag als erledigt melden
- POST /api/agent/jobs/<id>/error  -> Fehler melden (mit Retry-Logik)
- POST /api/agent/heartbeat        -> Lebenszeichen + last_seen aktualisieren

Authentifizierung: Header ``Authorization: Bearer <token>``. Der Token wird
beim Anlegen des Agents im Admin EINMAL angezeigt; in der DB wird nur der
SHA-256-Hash gespeichert.
"""

from functools import wraps

from flask import g, jsonify, request

from utils.csrf import csrf
from utils.database import get_db_connection
from utils.rate_limit import limiter
from utils.zebra_client import (
    PRINT_JOB_LEASE_SECONDS,
    PRINT_JOB_MAX_ATTEMPTS,
    cleanup_old_jobs,
    lease_next_job,
    mark_job_done,
    mark_job_error,
    verify_agent_token,
)

from . import print_agent_bp


def _agent_rate_key():
    """Rate-Limit-Schluessel: pro Agent (Token-Hash) bzw. IP-Fallback."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth[7:].strip()
        if token:
            from utils.zebra_client import hash_agent_token
            return f'agent:{hash_agent_token(token)[:16]}'
    return f'ip:{request.remote_addr or "?"}'


def _extract_bearer_token():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return auth[7:].strip() or None


def _resolve_agent_from_token(conn, token):
    """Sucht aktiven Agent zum Token (Konstantzeit-Vergleich)."""
    if not token:
        return None
    rows = conn.execute(
        '''SELECT id, name, token_hash, active
             FROM print_agents
            WHERE active = 1'''
    ).fetchall()
    for r in rows:
        if verify_agent_token(token, r['token_hash']):
            return r
    return None


def _update_agent_last_seen(conn, agent_id):
    conn.execute(
        '''UPDATE print_agents
              SET last_seen_at = datetime('now'),
                  last_ip = ?
            WHERE id = ?''',
        ((request.remote_addr or '')[:64], agent_id),
    )
    conn.commit()


def agent_token_required(view):
    """Pruefen, ob ein gueltiger Agent-Token vorliegt; Agent in g.agent ablegen."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return jsonify({'success': False, 'message': 'Bearer-Token fehlt.'}), 401
        with get_db_connection() as conn:
            agent = _resolve_agent_from_token(conn, token)
            if not agent:
                return jsonify({'success': False, 'message': 'Token ungueltig.'}), 401
            g.agent_id = int(agent['id'])
            g.agent_name = agent['name']
        return view(*args, **kwargs)
    return wrapper


@print_agent_bp.route('/poll', methods=['POST'])
@csrf.exempt
@limiter.limit('120 per minute', key_func=_agent_rate_key)
@agent_token_required
def poll():
    """Naechsten Druckauftrag fuer den aufrufenden Agent abholen.

    Antwort bei vorhandenem Auftrag (HTTP 200):
        {success: true, job: {id, drucker_id, drucker_name, drucker_ip, zpl, attempts}}

    Antwort wenn nichts ansteht:
        {success: true, job: null}
    """
    with get_db_connection() as conn:
        _update_agent_last_seen(conn, g.agent_id)
        try:
            cleanup_old_jobs(conn)
        except Exception:
            pass
        row = lease_next_job(conn, g.agent_id, lease_seconds=PRINT_JOB_LEASE_SECONDS)
        if row is None:
            return jsonify({'success': True, 'job': None})
        return jsonify({
            'success': True,
            'job': {
                'id': int(row['id']),
                'drucker_id': int(row['drucker_id']),
                'drucker_name': row['drucker_name'],
                'drucker_ip': row['drucker_ip'],
                'attempts': int(row['attempts']),
                'zpl': row['zpl'],
            },
        })


@print_agent_bp.route('/jobs/<int:job_id>/done', methods=['POST'])
@csrf.exempt
@limiter.limit('300 per minute', key_func=_agent_rate_key)
@agent_token_required
def job_done(job_id):
    """Auftrag als erfolgreich gedruckt melden."""
    with get_db_connection() as conn:
        _update_agent_last_seen(conn, g.agent_id)
        ok = mark_job_done(conn, g.agent_id, job_id)
    if not ok:
        return jsonify({'success': False, 'message': 'Auftrag nicht gefunden.'}), 404
    return jsonify({'success': True})


@print_agent_bp.route('/jobs/<int:job_id>/error', methods=['POST'])
@csrf.exempt
@limiter.limit('300 per minute', key_func=_agent_rate_key)
@agent_token_required
def job_error(job_id):
    """Fehler beim Drucken melden. Retry bis PRINT_JOB_MAX_ATTEMPTS."""
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip() or 'Unbekannter Fehler'
    with get_db_connection() as conn:
        _update_agent_last_seen(conn, g.agent_id)
        ok = mark_job_error(
            conn, g.agent_id, job_id, message,
            max_attempts=PRINT_JOB_MAX_ATTEMPTS,
        )
    if not ok:
        return jsonify({'success': False, 'message': 'Auftrag nicht gefunden.'}), 404
    return jsonify({'success': True})


@print_agent_bp.route('/heartbeat', methods=['POST'])
@csrf.exempt
@limiter.limit('60 per minute', key_func=_agent_rate_key)
@agent_token_required
def heartbeat():
    """Lebenszeichen vom Agent. Aktualisiert last_seen_at/last_ip."""
    with get_db_connection() as conn:
        _update_agent_last_seen(conn, g.agent_id)
    return jsonify({'success': True, 'agent_id': g.agent_id, 'agent_name': g.agent_name})
