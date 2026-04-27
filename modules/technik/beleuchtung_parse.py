"""IP-Symcon-MQTT-JSON in kanonischen Lampen-Status mappen."""

from __future__ import annotations

import json
import re
from typing import Any


def _truthy(s: str) -> bool:
    t = s.strip().lower()
    if t in ('1', 'true', 'on', 'yes', 'an', 'ein', 'eins'):
        return True
    if t in ('0', 'false', 'off', 'no', 'aus', 'nein', 'null', ''):
        return False
    # rein numerisch
    if re.match(r'^\d+(\.\d+)?$', t):
        try:
            return float(t) > 0
        except ValueError:
            return False
    return False


def parse_topic_lamp_id(topic: str, prefix: str) -> str | None:
    """
    topic z. B. IPS/BM/Beleuchtung/45329 oder IPS/BM/Beleuchtung/45329/update,
    prefix IPS/BM/Beleuchtung
    Rückgabe: 45329
    """
    p = (prefix or '').strip().rstrip('/')
    if not p:
        return None
    if not topic.startswith(p + '/'):
        return None
    rest = topic[len(p) + 1 :]
    if not rest:
        return None
    parts = [p for p in rest.split('/') if p]
    if not parts:
        return None
    if len(parts) == 1:
        lamp = parts[0]
    elif len(parts) == 2 and parts[1].lower() == 'update':
        lamp = parts[0]
    else:
        return None
    if not re.match(r'^\d+$', lamp):
        return None
    return lamp


def normalize_symcon_payload(raw: bytes | str | dict) -> dict[str, Any]:
    if isinstance(raw, bytes):
        try:
            obj = json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {'on': None, 'raw_text': None, 'error': 'json'}
    elif isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return {'on': None, 'raw_text': None, 'error': 'json'}
    else:
        obj = raw
    if not isinstance(obj, dict):
        return {'on': None, 'variable_id': None, 'path': None, 'error': 'type'}

    on: bool | None = None
    # IP-Symcon: UTF8Value "1" = ein, leerer String "" = aus (transparent in der UI)
    if 'UTF8Value' in obj:
        u = obj.get('UTF8Value')
        if u is None or (isinstance(u, str) and u.strip() == ''):
            on = False
        else:
            on = _truthy(str(u))
    path = (obj.get('Path') or '') or ''
    if on is None and path:
        pl = path.lower()
        if ' ein' in pl or pl.endswith(' ein') or 'an' in pl.split()[-1:]:
            on = _truthy('1')

    return {
        'on': on,
        'variable_id': obj.get('VariableID'),
        'path': path or None,
        'variable_ident': (obj.get('VariableIdent') or None),
        'variable_updated': obj.get('VariableUpdated') or obj.get('TS'),
        'raw': obj,
    }
