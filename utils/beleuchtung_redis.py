"""Redis-URL-Auflösung und Konstanten für Beleuchtungs-Live-Status."""

from __future__ import annotations

import os
import re

# Hash: Feld = lamp_id, Wert = JSON (kanonisierter Status)
REDIS_HASH_BELEUCHTUNG = 'bis:beleuchtung:state'

# Pub/Sub: Nachricht = JSON {"lamp_id": "...", "state": {...}}
REDIS_CHANNEL_BELEUCHTUNG = 'bis:beleuchtung:events'


def resolve_redis_url(app_config: dict | None, db_redis_url: str | None) -> str | None:
    """
    Priorität: explizite DB-Spalte RedisUrl, dann BIS_REDIS_URL, dann
    RATELIMIT_STORAGE_URI wenn redis://, sonst None.
    """
    if db_redis_url and str(db_redis_url).strip():
        return str(db_redis_url).strip()
    env = (os.environ.get('BIS_REDIS_URL') or '').strip()
    if env:
        return env
    if not app_config:
        rl = (os.environ.get('RATELIMIT_STORAGE_URI') or '').strip()
        if rl.startswith('redis://') or rl.startswith('rediss://'):
            return rl
        return None
    rl = (app_config.get('RATELIMIT_STORAGE_URI') or '').strip()
    if rl.startswith('redis://') or rl.startswith('rediss://'):
        return rl
    return None


def is_redis_configured_for_technik() -> bool:
    """
    Prüft nur, ob eine Redis-URL hinterlegt ist (ohne Verbindung).
    Für schnelle Technik-Seiten ohne Wartezeit auf get_redis/hgetall.
    """
    from flask import has_app_context
    from utils.mqtt_konfiguration_db import get_mqtt_konfiguration

    if not has_app_context():
        return False
    row = get_mqtt_konfiguration()
    u = resolve_redis_url(None, (row or {}).get('RedisUrl') if row else None)
    return bool(u and str(u).strip())


def get_redis_connection_for_technik(connect_timeout: float | None = None) -> "redis.Redis | None":  # noqa: F821
    """
    Redis-Client: Request-Kontext, Hintergrund-Thread (set_flask_app) oder reine env-URL.
    connect_timeout: None = 3s (Hintergrund-Threads), für HTTP-Handler z. B. 0,5s setzen.
    """
    import redis as _redis
    from redis.exceptions import RedisError
    from flask import has_app_context
    from utils.mqtt_konfiguration_db import get_mqtt_konfiguration

    row = None
    if has_app_context():
        row = get_mqtt_konfiguration()
    else:
        from modules.technik.mqtt_runtime import get_flask_app_ref
        a = get_flask_app_ref()
        if a is not None:
            with a.app_context():
                row = get_mqtt_konfiguration()

    u = resolve_redis_url(None, (row or {}).get('RedisUrl') if row else None)
    if not u:
        return None
    t = 3.0 if connect_timeout is None else connect_timeout
    try:
        return _redis.from_url(u, decode_responses=True, socket_connect_timeout=t)
    except RedisError:
        return None


def parse_redis_url_for_mqtt_client(redis_url: str) -> tuple[str, int, int | None]:
    """
    Extrahiert Host/Port aus redis://… (kein Passwort-Parsing nötig für interne URL).
    Gibt (host, port, db_index) zurück.
    """
    m = re.match(r'redis(s)?://([^:/@]+)(?::(\d+))?(?:/(\d+))?', redis_url)
    if not m:
        return ('127.0.0.1', 6379, 0)
    host = m.group(2) or '127.0.0.1'
    port = int(m.group(3) or 6379)
    db = int(m.group(4)) if m.group(4) is not None else 0
    return (host, port, db)
