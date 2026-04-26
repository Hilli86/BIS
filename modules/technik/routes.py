"""
Routen für Technik (SVG-Übersichten).
"""

import json
import os
import queue
import logging

from flask import Response, abort, jsonify, render_template, request, stream_with_context, url_for
from redis.exceptions import RedisError

from utils.beleuchtung_redis import (
    REDIS_HASH_BELEUCHTUNG,
    get_redis_connection_for_technik,
    is_redis_configured_for_technik,
)

# Kurzes Connect-Timeout für Web-Anfragen (kein Blockieren im Sekundenbereich, wenn Redis aus ist)
_REDIS_CONNECT_TIMEOUT_HTTP = 0.5
from utils.decorators import login_required, menue_zugriff_erforderlich
from modules.technik.sse_broadcast import count_subscribers, register_subscriber, unregister_subscriber

from . import technik_bp

log_sse = logging.getLogger('bis.technik.sse')

# Registrierte Diagramme: id (URL-Parameter diagram), Anzeigename, Pfad unter static/
TECHNIK_DIAGRAMME = [
    {
        'id': 'schnelllauftore',
        'title': 'Schnelllauftore',
        'static_path': 'technik/Layouts/Schnelllauftore.svg',
    },
    {
        'id': 'hygieneanlagen',
        'title': 'Hygieneanlagen',
        'static_path': 'technik/Layouts/Hygieneanlagen.svg',
    },
    {
        'id': 'beleuchtung',
        'title': 'Beleuchtung',
        'static_path': 'technik/Layouts/Beleuchtung.svg',
    },
]

# Modal & Spalten pro Layout-Id (Feld-„key" = Schlüssel in TECHNIK_LAYOUT_HOTSPOTS)
# format "strip_slt" nur für Schnelllauftore: Tornummer = ID ohne Präfix SLT
TECHNIK_LAYOUT_META = {
    'schnelllauftore': {
        'modal_titel': 'Detail',
        'felder': [
            {'key': 'id', 'label': 'Tornummer', 'format': 'strip_slt'},
            {'key': 'von', 'label': 'Von'},
            {'key': 'nach', 'label': 'Nach'},
            {'key': 'seriennummer', 'label': 'Seriennummer'},
            {'key': 'tortyp', 'label': 'Tortyp'},
            {'key': 'abmessungen', 'label': 'Abmessungen'},
        ],
    },
    'hygieneanlagen': {
        'modal_titel': 'Detail',
        'felder': [
            {'key': 'id', 'label': 'ID'},
            {'key': 'name', 'label': 'Name'},
            {'key': 'ort', 'label': 'Ort'},
            {'key': 'produkt', 'label': 'Produkt'},
            {'key': 'desinfektionsmittel', 'label': 'Desinfektionsmittel'},
            {'key': 'soll', 'label': 'Soll'},
        ],
    },
    'beleuchtung': {
        'modal_titel': 'Beleuchtung',
        'felder': [
            {'key': 'id', 'label': 'Kennung'},
            {'key': 'bezeichnung', 'label': 'Bezeichnung'},
            {'key': 'raum', 'label': 'Raum / Bereich'},
            {'key': 'leuchtmittel', 'label': 'Leuchtmittel / Typ'},
            {'key': 'notizen', 'label': 'Notizen'},
        ],
    },
}

# Klickflächen pro Layout: "id" = data-cell-id im SVG (Draw.io-Objekt-ID)
TECHNIK_LAYOUT_HOTSPOTS = {
    'schnelllauftore': [
        {
            'id': 'SLT01',
            'von': 'Anlieferung',
            'nach': 'Schleuse 1',
            'seriennummer': '1300013329',
            'tortyp': 'RR300I+',
            'abmessungen': '3,0 × 3,0 m (B×H)',
        },
        {
            'id': 'SLT02',
            'von': 'Halle B',
            'nach': 'Außen',
            'seriennummer': 'SN-2024-0002',
            'tortyp': 'Schnelllauftor',
            'abmessungen': '2,5 × 2,8 m (B×H)',
        },
        {
            'id': 'SLT03',
            'von': 'Halle B',
            'nach': 'Außen',
            'seriennummer': 'SN-2024-0002',
            'tortyp': 'Schnelllauftor',
            'abmessungen': '2,5 × 2,8 m (B×H)',
        },
        {
            'id': 'SLT18',
            'von': 'Halle B',
            'nach': 'Außen',
            'seriennummer': 'SN-2024-0002',
            'tortyp': 'Schnelllauftor',
            'abmessungen': '2,5 × 2,8 m (B×H)',
        },
    ],
    'hygieneanlagen': [
        {
            'id': 'PG01',
            'name': 'Profilgate 1',
            'ort': 'Vorbereitung',
            'produkt': 'D',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'HS01',
            'name': 'Eingangsschleuse',
            'ort': 'Haupteingang',
            'produkt': 'Schaumreiniger',
            'desinfektionsmittel': 'Desderman pure',
            'soll': '1× täglich',
        },
    ],
    # Klickflächen: pro Eintrag muss im SVG <g data-cell-id="…"> derselbe Wert in id stehen
    'beleuchtung': [],
}


def _diagram_by_id(diagram_id: str):
    for d in TECHNIK_DIAGRAMME:
        if d['id'] == diagram_id:
            return d
    return None


@technik_bp.route('/uebersichten')
@login_required
@menue_zugriff_erforderlich('technik_uebersichten')
def uebersichten():
    if not TECHNIK_DIAGRAMME:
        abort(404)

    requested = (request.args.get('diagram') or '').strip()
    current = _diagram_by_id(requested) if requested else None
    if current is None:
        current = TECHNIK_DIAGRAMME[0]

    svg_url = url_for('static', filename=current['static_path'])
    layout_hotspots = TECHNIK_LAYOUT_HOTSPOTS.get(current['id'], [])
    meta = TECHNIK_LAYOUT_META.get(current['id'], {})
    layout_hotspot_config = {
        'felder': meta.get('felder', []),
        'modal_titel': meta.get('modal_titel', 'Detail'),
    }
    # Beleuchtung: kein synchrones Redis im Request – sonst warten Nutzer u. a. socket_connect_timeout.
    beleuchtung_initial = None
    beleuchtung_redis_configured = None
    if current['id'] == 'beleuchtung':
        if is_redis_configured_for_technik():
            beleuchtung_redis_configured = True
            # ok: null = kein serverseitiger hget, Echtzeit/Init kommt per SSE/Client
            beleuchtung_initial = {'ok': None, 'states': {}}
        else:
            beleuchtung_redis_configured = False
            beleuchtung_initial = {'ok': False, 'states': {}}

    return render_template(
        'technik/uebersichten.html',
        diagramme=TECHNIK_DIAGRAMME,
        current_diagram=current,
        current_svg_url=svg_url,
        layout_hotspots=layout_hotspots,
        layout_hotspot_config=layout_hotspot_config,
        beleuchtung_initial=beleuchtung_initial,
        beleuchtung_redis_configured=beleuchtung_redis_configured,
    )


@technik_bp.route('/beleuchtung/zustand')
@login_required
@menue_zugriff_erforderlich('technik_uebersichten')
def beleuchtung_zustand():
    r = get_redis_connection_for_technik(connect_timeout=_REDIS_CONNECT_TIMEOUT_HTTP)
    st = {}
    if r:
        try:
            h = r.hgetall(REDIS_HASH_BELEUCHTUNG)
            for k, v in h.items():
                if not k:
                    continue
                key = k if isinstance(k, str) else k.decode('utf-8', errors='replace')
                try:
                    st[key] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass
            return jsonify({'ok': True, 'states': st})
        except RedisError:
            return jsonify({'ok': False, 'states': {}})
    return jsonify({'ok': False, 'states': st})


@technik_bp.route('/beleuchtung/stream')
@login_required
@menue_zugriff_erforderlich('technik_uebersichten')
def beleuchtung_stream():
    r = get_redis_connection_for_technik(connect_timeout=_REDIS_CONNECT_TIMEOUT_HTTP)
    q = register_subscriber()
    n_after = count_subscribers()

    @stream_with_context
    def gen():
        initial = {}
        redis_live = False
        if r:
            try:
                h = r.hgetall(REDIS_HASH_BELEUCHTUNG)
                for k, v in h.items():
                    if not k:
                        continue
                    key = k if isinstance(k, str) else k.decode('utf-8', errors='replace')
                    try:
                        initial[key] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        pass
                redis_live = True
            except RedisError:
                initial = {}
        log_sse.info(
            'Beleuchtung SSE: Init (PID %s, lokale Abonnenten: %d, redis_ok=%s, remote=%s)',
            os.getpid(),
            n_after,
            redis_live,
            request.headers.get('X-Forwarded-For', request.remote_addr),
        )
        try:
            yield f"event: init\ndata: {json.dumps({'ok': redis_live, 'states': initial}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    line = q.get(timeout=25)
                    yield f"data: {line}\n\n"
                except queue.Empty:
                    yield ': keepalive\n\n'
        finally:
            unregister_subscriber(q)
            log_sse.info('Beleuchtung SSE: Stream beendet (PID %s, lokale Abonnenten: %d)', os.getpid(), count_subscribers())

    resp = Response(gen(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp
