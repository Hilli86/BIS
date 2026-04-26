"""Laden und Speichern der MQTT-Konfiguration (Tabelle MqttKonfiguration)."""

from __future__ import annotations

from utils.database import get_db_connection


def row_to_cfg(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    if 'PasswortKrypt' in d:
        d['PasswortKrypt'] = d.get('PasswortKrypt')
    return d


def get_mqtt_konfiguration_row():
    """Liest Zeile aus MqttKonfiguration (muss in Flask-App-Kontext aufgerufen werden)."""
    with get_db_connection() as conn:
        cur = conn.execute('SELECT * FROM MqttKonfiguration ORDER BY ID LIMIT 1')
        row = cur.fetchone()
    return row


def get_mqtt_konfiguration() -> dict | None:
    r = get_mqtt_konfiguration_row()
    if not r:
        return None
    return dict(r)
