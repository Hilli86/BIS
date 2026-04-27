"""
Ausgehende MQTT-Kommandos für Technik-Übersichten.
"""

from __future__ import annotations

import logging

from flask import current_app

from utils.mqtt_konfiguration_db import get_mqtt_konfiguration_row

log = logging.getLogger('bis.technik.mqtt.command')


def _decrypt_mqtt_password(cfg: dict) -> str | None:
    raw = (cfg.get('PasswortKrypt') or '')
    if not raw:
        return None
    from utils.fernet_secrets import decrypt_text
    import os
    from config import Config

    sk = os.environ.get('SECRET_KEY') or Config.SECRET_KEY
    return decrypt_text(raw, sk)


def publish_beleuchtung_command(lamp_id: str, target_on: bool) -> tuple[bool, str]:
    row = get_mqtt_konfiguration_row()
    cfg = dict(row) if row else {}
    if not cfg:
        return False, 'MQTT-Konfiguration fehlt.'
    if int(cfg.get('Aktiv') or 0) != 1:
        return False, 'MQTT ist deaktiviert.'

    host = (cfg.get('BrokerHost') or '').strip()
    if not host:
        return False, 'MQTT-Broker nicht konfiguriert.'
    port = int(cfg.get('BrokerPort') or 1883)
    prefix = (cfg.get('TopicPrefixBeleuchtung') or 'IPS/BM/Beleuchtung').strip().rstrip('/')
    if not prefix:
        return False, 'MQTT-Topic-Präfix fehlt.'

    topic = f'{prefix}/{lamp_id}/set'
    payload = '1' if target_on else '0'
    use_tls = int(cfg.get('UseTls') or 0) == 1
    tls_insec = int(cfg.get('TlsInsecure') or 0) == 1
    ca = (cfg.get('CaPfad') or '').strip() or None
    user = (cfg.get('Benutzername') or '').strip() or None
    pw = _decrypt_mqtt_password(cfg) or ''

    try:
        import paho.mqtt.publish as publish
    except Exception as ex:
        return False, f'MQTT-Library nicht verfügbar: {ex}'

    auth = {'username': user, 'password': pw} if user else None
    tls = None
    if use_tls:
        tls = {'ca_certs': ca, 'insecure': tls_insec}

    try:
        publish.single(
            topic=topic,
            payload=payload,
            hostname=host,
            port=port,
            qos=0,
            retain=False,
            auth=auth,
            tls=tls,
            client_id=f"bis-technik-cmd-{lamp_id}",
        )
    except Exception as ex:
        log.warning('MQTT publish fehlgeschlagen: topic=%s err=%s', topic, ex)
        return False, f'Publish fehlgeschlagen: {ex}'

    log.info('MQTT command gesendet: topic=%s payload=%s user=%s', topic, payload, bool(user))
    return True, topic

