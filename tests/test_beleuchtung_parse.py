"""Tests: MQTT-Topic- und IP-Symcon-JSON-Heuristik (Beleuchtung)."""

import json

from modules.technik.beleuchtung_parse import normalize_symcon_payload, parse_topic_lamp_id


def test_parse_topic_lamp_id():
    assert parse_topic_lamp_id('IPS/BM/Beleuchtung/45329', 'IPS/BM/Beleuchtung') == '45329'
    assert parse_topic_lamp_id('IPS/BM/Beleuchtung/45329', 'IPS/BM/Beleuchtung/') == '45329'
    assert parse_topic_lamp_id('x/y', 'IPS') is None


def test_normalize_utf8value():
    o = json.loads('{"UTF8Value":"1","Path":"/x","VariableID":1}')
    n = normalize_symcon_payload(o)
    assert n['on'] is True

    o2 = json.loads('{"UTF8Value":"0","Path":"/x","VariableID":1}')
    assert normalize_symcon_payload(o2)['on'] is False

    o3 = json.loads('{"UTF8Value":"","Path":"/x","VariableID":1}')
    assert normalize_symcon_payload(o3)['on'] is False
