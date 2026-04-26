"""
MQTT-Leader (Redis-Lock) + Beleuchtung-Handler; Redis-Pub-Sub-Listener in jedem Worker.
Wird pro Gunicorn-Worker bzw. Dev-Prozess gestartet.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

import redis
from redis.exceptions import RedisError

from utils.beleuchtung_redis import (
    REDIS_CHANNEL_BELEUCHTUNG,
    REDIS_HASH_BELEUCHTUNG,
    get_redis_connection_for_technik,
)
from modules.technik.beleuchtung_parse import normalize_symcon_payload, parse_topic_lamp_id
from modules.technik.sse_broadcast import broadcast_dict, count_subscribers

log = logging.getLogger('bis.mqtt')

# Per Umgebung: ausführliche MQTT-/Redis-Logs (Payloads, Topic-Details)
def _mqtt_verbose() -> bool:
    return os.environ.get('BIS_MQTT_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')


_no_redis_logged = False
_not_leader_logged = False
_pubsub_unreach_logged = False
_supervisor_unreach_logged = False

# Flask-App-Referenz für DB-Zugriff aus Hintergrund-Threads (siehe set_flask_app).
_flask_app = None
_mqtt_lock = threading.Lock()
_mqtt_client = None
_shutdown = False
_config_cache: dict | None = None
_config_cache_ts: float = 0.0
_CACHED_TTL = 5.0

LEADER_REDIS_KEY = 'bis:mqtt:leader'
LEADER_TTL_S = 25


def set_flask_app(app) -> None:
    """Von app.py einmalig setzen, damit Hintergrund-Threads DB-Config lesen dürfen."""
    global _flask_app
    _flask_app = app


def get_flask_app_ref():
    """Für Redis-URL (beleuchtung_redis) aus Nicht-Request-Threads."""
    return _flask_app


def invalidate_mqtt_konfig_cache() -> None:
    global _config_cache, _config_cache_ts
    _config_cache = None
    _config_cache_ts = 0.0


def _get_mqtt_konfiguration_cached() -> dict | None:
    global _config_cache, _config_cache_ts, _flask_app
    now = time.time()
    if _config_cache is not None and (now - _config_cache_ts) < _CACHED_TTL:
        return _config_cache
    if _flask_app is None:
        return None
    from utils.mqtt_konfiguration_db import get_mqtt_konfiguration_row

    with _flask_app.app_context():
        row = get_mqtt_konfiguration_row()
    _config_cache = dict(row) if row else None
    _config_cache_ts = now
    return _config_cache


def ensure_mqtt_leader(redis_c: redis.Redis, my_pid: int) -> bool:
    try:
        v = redis_c.get(LEADER_REDIS_KEY)
        if v is not None and str(v) == str(my_pid):
            redis_c.expire(LEADER_REDIS_KEY, LEADER_TTL_S)
            return True
        ok = redis_c.set(LEADER_REDIS_KEY, str(my_pid), nx=True, ex=LEADER_TTL_S)
        return bool(ok)
    except RedisError as e:
        log.debug('Redis leader: %s', e)
        return False


def _stop_mqtt_client() -> None:
    global _mqtt_client
    with _mqtt_lock:
        m = _mqtt_client
        _mqtt_client = None
    if m is not None:
        try:
            m.loop_stop()
            m.disconnect()
        except Exception as e:
            log.debug('MQTT stop: %s', e)


def _build_on_message(cfg_prefix: str):
    def _cb(client, userdata, msg):
        try:
            topic = msg.topic
            pl = msg.payload
        except Exception as ex:
            log.warning('MQTT on_message: Zugriff auf msg fehlgeschlagen: %s', ex)
            return
        lamp_id = parse_topic_lamp_id(topic, cfg_prefix)
        if not lamp_id:
            if _mqtt_verbose():
                log.info(
                    'MQTT Nachricht ignoriert (Topic passt nicht zum Präfix %r): %r',
                    cfg_prefix,
                    topic,
                )
                if pl:
                    log.info(
                        'MQTT Payload (Auszug): %s',
                        pl[:500] if isinstance(pl, (bytes, bytearray)) else str(pl)[:500],
                    )
            else:
                log.debug('MQTT ignoriert (kein lamp_id) topic=%r präfix=%r', topic, cfg_prefix)
            return
        norm = normalize_symcon_payload(pl)
        on = norm.get('on')
        r = get_redis_connection_for_technik()
        if not r:
            log.warning('MQTT: Redis nicht erreichbar (HSET/PUBLISH übersprungen) für topic=%r lamp_id=%s', topic, lamp_id)
            return
        event = {'lamp_id': lamp_id, 'state': norm}
        try:
            r.hset(
                REDIS_HASH_BELEUCHTUNG,
                lamp_id,
                json.dumps(event, ensure_ascii=False, default=str),
            )
            r.publish(
                REDIS_CHANNEL_BELEUCHTUNG,
                json.dumps(event, ensure_ascii=False, default=str),
            )
        except RedisError as e:
            log.warning('Redis HSET/PUBLISH: %s', e)
            return
        if _mqtt_verbose():
            log.info('MQTT vollständig: topic=%r lamp_id=%r on=%r event=%s', topic, lamp_id, on, json.dumps(event, default=str)[:800])
        else:
            log.debug('MQTT -> Redis/SSE: topic=%r lamp_id=%r on=%r', topic, lamp_id, on)

    return _cb


def _build_on_connect(sub_topic: str):
    def _cb(client, userdata, flags, reason_code, properties):
        if getattr(reason_code, 'is_failure', False):
            log.warning('MQTT on_connect: %s', reason_code)
            return
        client.subscribe(sub_topic, qos=0)
        log.info('MQTT abonniert: %r', sub_topic)

    return _cb


def _decrypt_mqtt_password(cfg: dict) -> str | None:
    raw = (cfg.get('PasswortKrypt') or '')
    if not raw:
        return None
    from utils.fernet_secrets import decrypt_text
    import os
    from config import Config

    sk = os.environ.get('SECRET_KEY') or Config.SECRET_KEY
    return decrypt_text(raw, sk)


def _start_mqtt_if_leader(cfg: dict) -> None:
    global _mqtt_client
    import paho.mqtt.client as mqtt

    with _mqtt_lock:
        if _mqtt_client is not None:
            return
        if not (cfg and int(cfg.get('Aktiv') or 0) and (cfg.get('BrokerHost') or '').strip()):
            return
        host = (cfg.get('BrokerHost') or '').strip()
        port = int(cfg.get('BrokerPort') or 1883)
        prefix = (cfg.get('TopicPrefixBeleuchtung') or 'IPS/BM/Beleuchtung').strip()
        use_tls = int(cfg.get('UseTls') or 0) == 1
        tls_insec = int(cfg.get('TlsInsecure') or 0) == 1
        ca = (cfg.get('CaPfad') or '').strip() or None
        user = (cfg.get('Benutzername') or '').strip() or None
        pw = _decrypt_mqtt_password(cfg) or ''
        base_cid = (cfg.get('MqttClientId') or '').strip() or 'bis-technik'
        cid = f'{base_cid}-{os.getpid()}'
        c = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=cid,
            protocol=mqtt.MQTTv311,
        )
        sub_topic = f'{prefix.rstrip("/")}/#'
        c.on_message = _build_on_message(prefix)
        c.on_connect = _build_on_connect(sub_topic)
        if user:
            c.username_pw_set(user, pw)
        if use_tls:
            c.tls_set(ca_certs=ca)
            if tls_insec:
                c.tls_insecure_set(True)
        c.connect(host, port, keepalive=30)
        c.loop_start()
        _mqtt_client = c
        log.info('MQTT verbunden, subscribe %s', sub_topic)


def _supervisor_run():
    global _no_redis_logged, _not_leader_logged, _supervisor_unreach_logged
    my_pid = os.getpid()
    while not _shutdown:
        r = get_redis_connection_for_technik()
        if not r:
            if not _no_redis_logged:
                log.warning(
                    'Technik: Kein Redis (BIS_MQTT_DEBUG für Details) – MQTT-Leader & Live-Updates brauchen '
                    'BIS_REDIS_URL / MqttKonfiguration.RedisUrl bzw. RATELIMIT_STORAGE_URI=redis://… (PID %s).',
                    my_pid,
                )
                _no_redis_logged = True
            _stop_mqtt_client()
            time.sleep(2)
            continue
        _no_redis_logged = False
        try:
            r.ping()
        except (RedisError, OSError) as e:
            if not _supervisor_unreach_logged:
                log.info(
                    'MQTT-Supervisor: Redis nicht erreichbar (%s), Hintergrund erneuert die Verbindung. '
                    '(PID %s; Detail-Logs: BIS_MQTT_DEBUG=1).',
                    e,
                    my_pid,
                )
                _supervisor_unreach_logged = True
            elif _mqtt_verbose():
                # Kein exc_info: Verbindungsfehler kommen im Retry alle paar Sekunden – Trace wäre Log-Spam.
                log.debug('MQTT-Supervisor: Redis-Ping-Retry: %s', e)
            _stop_mqtt_client()
            time.sleep(2)
            continue
        _supervisor_unreach_logged = False
        try:
            if not ensure_mqtt_leader(r, my_pid):
                if not _not_leader_logged or _mqtt_verbose():
                    lock_val = r.get(LEADER_REDIS_KEY)
                    if isinstance(lock_val, (bytes, bytearray)):
                        lock_val = lock_val.decode('utf-8', errors='replace')
                    log.info(
                        'Technik: anderer Prozess ist MQTT-Leader (PID %s, Lock=%r)',
                        my_pid,
                        lock_val,
                    )
                    _not_leader_logged = True
                _stop_mqtt_client()
            else:
                _not_leader_logged = False
                cfg = _get_mqtt_konfiguration_cached()
                if cfg and int(cfg.get('Aktiv') or 0) and (cfg.get('BrokerHost') or '').strip():
                    _start_mqtt_if_leader(cfg)
                else:
                    _stop_mqtt_client()
        except (RedisError, OSError) as e:
            log.info('MQTT-Supervisor: Redis %s, MQTT gestoppt, nächster Versuch.', e)
            _stop_mqtt_client()
        except Exception as e:
            log.warning('MQTT-Supervisor: %s', e, exc_info=_mqtt_verbose())
            _stop_mqtt_client()
        time.sleep(1.0)


def _redis_pubsub_run():
    global _pubsub_unreach_logged
    while not _shutdown:
        r = get_redis_connection_for_technik()
        if not r:
            time.sleep(2)
            continue
        try:
            r.ping()
        except (RedisError, OSError) as e:
            if not _pubsub_unreach_logged:
                log.info(
                    'Redis Pub/Sub: Server nicht erreichbar (%s), Hintergrund erneuert die Verbindung. '
                    'Technik-Layouts: Standardansicht bleibt nutzbar. (PID %s).',
                    e,
                    os.getpid(),
                )
                _pubsub_unreach_logged = True
            elif _mqtt_verbose():
                log.debug('Redis Pub/Sub: Ping-Retry: %s', e)
            time.sleep(2)
            continue
        _pubsub_unreach_logged = False
        try:
            p = r.pubsub(ignore_subscribe_messages=True)
            p.subscribe(REDIS_CHANNEL_BELEUCHTUNG)
            log.info('Redis Pub/Sub: Kanal %r abonniert (PID %s)', REDIS_CHANNEL_BELEUCHTUNG, os.getpid())
            for m in p.listen():
                if _shutdown:
                    break
                if m is None or m.get('type') != 'message':
                    if _mqtt_verbose() and m is not None and m.get('type') not in ('message', 'pong'):
                        log.debug('Redis pubsub: %s', m)
                    continue
                data = m.get('data')
                if not data:
                    continue
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode('utf-8', errors='replace')
                try:
                    o = json.loads(data)
                except (json.JSONDecodeError, TypeError) as je:
                    log.warning('Redis Pub/Sub: ungültiges JSON: %s', je)
                    continue
                n = count_subscribers()
                broadcast_dict(o)
                lid = o.get('lamp_id', '?')
                if _mqtt_verbose():
                    if n > 0:
                        log.info('Redis Pub/Sub -> SSE: lamp_id=%r, %d Abonnenten (PID %s)', lid, n, os.getpid())
                    else:
                        log.info(
                            'Redis Pub/Sub: lamp_id=%r, 0 Abonnenten in diesem Prozess (Gunicorn: anderer Worker hat den Stream; PID %s)',
                            lid,
                            os.getpid(),
                        )
                else:
                    log.debug('Redis Pub/Sub -> push lamp_id=%r subs=%d', lid, n)
        except (RedisError, OSError) as e:
            log.info('Redis pubsub: Verbindung ab (%s), Schleife startet neu.', e)
            time.sleep(1)


_threads_started = False
_threads_lock = threading.Lock()


def start_technik_mqtt_threads():
    global _threads_started, _shutdown
    with _threads_lock:
        if _threads_started:
            return
        _threads_started = True
        _shutdown = False
    t1 = threading.Thread(target=_supervisor_run, name='bis-mqtt-supervisor', daemon=True)
    t2 = threading.Thread(target=_redis_pubsub_run, name='bis-redis-pubsub', daemon=True)
    t1.start()
    t2.start()
    log.info('Technik-MQTT-Hintergrundthreads gestartet (PID %s)', os.getpid())


def stop_technik_mqtt_threads():
    global _shutdown, _threads_started
    _shutdown = True
    _stop_mqtt_client()
    _threads_started = False
