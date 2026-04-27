"""
Routen für Technik (SVG-Übersichten).
"""

import json
import os
import queue
import logging
import re

from flask import (
    Response,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    stream_with_context,
    url_for,
)
from redis.exceptions import RedisError

from utils.beleuchtung_redis import (
    REDIS_HASH_BELEUCHTUNG,
    get_redis_connection_for_technik,
    is_redis_configured_for_technik,
)

# Kurzes Connect-Timeout für Web-Anfragen (kein Blockieren im Sekundenbereich, wenn Redis aus ist)
_REDIS_CONNECT_TIMEOUT_HTTP = 0.2
from utils.decorators import login_required, menue_zugriff_erforderlich
from modules.technik.sse_broadcast import count_subscribers, register_subscriber, unregister_subscriber
from modules.technik.mqtt_commands import publish_beleuchtung_command

from . import technik_bp

log_sse = logging.getLogger('bis.technik.sse')

# Standard-Diagramme inkl. Metadaten; die tatsächliche Liste wird dynamisch aus dem Layout-Ordner erzeugt.
TECHNIK_STANDARD_DIAGRAMME = [
    {
        'id': 'schnelllauftore',
        'title': 'Schnelllauftore',
        'layout_filename': 'Schnelllauftore.svg',
    },
    {
        'id': 'hygieneanlagen',
        'title': 'Hygieneanlagen',
        'layout_filename': 'Hygieneanlagen.svg',
    },
    {
        'id': 'beleuchtung',
        'title': 'Beleuchtung',
        'layout_filename': 'Beleuchtung.svg',
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
            'nach': 'Schleuße 1',
            'seriennummer': '1300013329',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT02',
            'von': 'Anlieferung',
            'nach': 'Schleuße 2',
            'seriennummer': '1300013334',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT03',
            'von': 'Frischfischlager',
            'nach': 'Anlieferung',
            'seriennummer': '1300013320',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT04',
            'von': 'Gang 1',
            'nach': 'Anlieferung',
            'seriennummer': '1300013321',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT05',
            'von': 'Verpackungslager',
            'nach': 'Anlieferung',
            'seriennummer': '1300013317',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT06',
            'von': 'Verpackungslager',
            'nach': 'Gang 1',
            'seriennummer': '1300013333',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT07',
            'von': 'Gang 1',
            'nach': 'Frischfischlager',
            'seriennummer': '1300013319',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT08',
            'von': 'Gang 1',
            'nach': 'Schleuße 5',
            'seriennummer': '1700004297',
            'tortyp': 'RR392',
            'abmessungen': '2,00 x 3,50m (B×H)',
        },
        {
            'id': 'SLT09',
            'von': 'Schleuße 5',
            'nach': 'Außenbereich',
            'seriennummer': '2701003745',
            'tortyp': 'RR3000 ISO',
            'abmessungen': '2,00 x 3,50m (B×H)',
        },
        {
            'id': 'SLT10',
            'von': 'Auftauraum',
            'nach': 'Gang 2',
            'seriennummer': '1300013322',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT11',
            'von': 'Vorbereitung',
            'nach': 'Auftauraum',
            'seriennummer': '28000025407',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT12',
            'von': 'Vorbereitung',
            'nach': 'Müllraum',
            'seriennummer': '28000025418',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT13',
            'von': 'Vorbereitung',
            'nach': 'Zwischenlager HC',
            'seriennummer': '28000025419',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT14',
            'von': 'Zwischenlager HC',
            'nach': 'Verpackung HC',
            'seriennummer': '28000025410',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT15',
            'von': 'Materiallager HC',
            'nach': 'Verpackung HC',
            'seriennummer': '28000025411',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT16',
            'von': 'Materiallager HC',
            'nach': 'Gang 2',
            'seriennummer': '1300013323',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT17',
            'von': 'Verpackung HC',
            'nach': 'Müllraum HC',
            'seriennummer': '28000025412',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT18',
            'von': 'Kistenwaschraum',
            'nach': 'Gang 2',
            'seriennummer': '1300013324',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT19',
            'von': 'Küche',
            'nach': 'Gang 2',
            'seriennummer': '28000025415',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT20',
            'von': 'Küche',
            'nach': 'Müllraum',
            'seriennummer': '28000025417',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT21',
            'von': 'Abstelllager',
            'nach': 'Gang 2',
            'seriennummer': '1300013325',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT22',
            'von': 'Küche',
            'nach': 'Zwischenlager HR',
            'seriennummer': '28000025413',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT23',
            'von': 'Abstelllager',
            'nach': 'Fertigwarenlager 3',
            'seriennummer': '28000025416',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT24',
            'von': 'Zwischenlager HR',
            'nach': 'Fertigwarenlager 3',
            'seriennummer': '28000025408',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT25',
            'von': 'Fertigwarenlager 3',
            'nach': 'QM-Labor',
            'seriennummer': '28000025409',
            'tortyp': 'RR300 Clean',
            'abmessungen': '1,50 x 2,40m (B×H)',
        },
        {
            'id': 'SLT26',
            'von': 'Etikettierung',
            'nach': 'Gang 2',
            'seriennummer': '1300013326',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT27',
            'von': 'Fertigwarenlager 1',
            'nach': 'Etikettierung',
            'seriennummer': '1300013327',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT28',
            'von': 'Fertigwarenlager 1',
            'nach': 'Auslieferung',
            'seriennummer': '1300013328',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT29',
            'von': 'Auslieferung',
            'nach': 'Schleuße 3',
            'seriennummer': '1300013335',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
        {
            'id': 'SLT30',
            'von': 'Auslieferung',
            'nach': 'Schleuße 4',
            'seriennummer': '1300013336',
            'tortyp': 'RR300I+',
            'abmessungen': '1,80 x 2,40m (B×H)',
        },
    ],
    'hygieneanlagen': [
        {
            'id': 'PG01',
            'name': 'Profilgate 1',
            'ort': 'Vorbereitung',
            'produkt': 'Bodendesinfektion',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'PG02',
            'name': 'Profilgate 2',
            'ort': 'Vorbereitungslager HC',
            'produkt': 'Bodendesinfektion',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'PG03',
            'name': 'Profilgate 3',
            'ort': 'Verpackungslager HC',
            'produkt': 'Bodendesinfektion',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'PG04',
            'name': 'Profilgate 4',
            'ort': 'Abstelllager',
            'produkt': 'Bodendesinfektion',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'PG05',
            'name': 'Profilgate 5',
            'ort': 'Küche',
            'produkt': 'Bodendesinfektion',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'PG06',
            'name': 'Profilgate 6',
            'ort': 'Zwischenlager HR',
            'produkt': 'Bodendesinfektion',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'HS01',
            'name': 'Hygieneschleuse 1',
            'ort': 'Vorbereitung',
            'produkt': 'Laska Hygieneschleuse',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'HS02',
            'name': 'Hygieneschleuse 2',
            'ort': 'Verpackung',
            'produkt': 'Laska Hygieneschleuse',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'HS03',
            'name': 'Hygieneschleuse 3',
            'ort': 'Küche',
            'produkt': 'Laska Hygieneschleuse',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'HS04',
            'name': 'Hygieneschleuse 4',
            'ort': 'Fertigwarenlager 3',
            'produkt': 'Laska Hygieneschleuse',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'HS05',
            'name': 'Hygieneschleuse 5',
            'ort': 'Hygieneschleußen',
            'produkt': 'Laska Hygieneschleuse',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'SR01',
            'name': 'Stiefelreiniger 1',
            'ort': 'Stiegenhaus',
            'produkt': 'Laska Stiefelreiniger',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
        {
            'id': 'SR02',
            'name': 'Stiefelreiniger 2',
            'ort': 'Technik',
            'produkt': 'Laska Stiefelreiniger',
            'desinfektionsmittel': 'DI Suredis VT1',
            'soll': 'ca. 0,5 - 3%',
        },
    ],
    # Klickflächen: pro Eintrag muss im SVG <g data-cell-id="…"> derselbe Wert in id stehen
    'beleuchtung': [],
}


def _normalize_layout_stem(stem: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', (stem or '').lower())


def _build_layout_diagramme() -> list[dict]:
    known_by_stem = {}
    for d in TECHNIK_STANDARD_DIAGRAMME:
        stem = _normalize_layout_stem(os.path.splitext(d.get('layout_filename') or '')[0])
        if stem:
            known_by_stem[stem] = d

    data_dir = (current_app.config.get('TECHNIK_LAYOUTS_FOLDER') or '').strip()
    files = []
    if data_dir and os.path.isdir(data_dir):
        try:
            files = sorted(
                [n for n in os.listdir(data_dir) if n.lower().endswith('.svg')],
                key=lambda x: x.lower(),
            )
        except OSError:
            files = []

    used_ids = set()
    out = []
    for fname in files:
        stem_raw = os.path.splitext(fname)[0]
        stem_norm = _normalize_layout_stem(stem_raw)
        base = known_by_stem.get(stem_norm)
        if base:
            did = base['id']
            title = base['title']
        else:
            did = re.sub(r'[^a-z0-9]+', '-', stem_raw.lower()).strip('-') or 'layout'
            title = stem_raw.replace('_', ' ').strip() or fname

        candidate = did
        i = 2
        while candidate in used_ids:
            candidate = f'{did}-{i}'
            i += 1
        used_ids.add(candidate)
        out.append({'id': candidate, 'title': title, 'layout_filename': fname})

    return out


def _diagram_by_id(diagram_id: str, diagramme: list[dict]):
    for d in diagramme:
        if d['id'] == diagram_id:
            return d
    return None


def _resolve_technik_layout_file(diagram: dict) -> str | None:
    """Datei unter TECHNIK_LAYOUTS_FOLDER (Datenverzeichnis)."""
    name = (diagram.get('layout_filename') or '').strip()
    if not name or '..' in name or '/' in name or '\\' in name:
        return None
    if not name.lower().endswith('.svg'):
        return None
    data_dir = (current_app.config.get('TECHNIK_LAYOUTS_FOLDER') or '').strip()
    if data_dir:
        try:
            os.makedirs(data_dir, exist_ok=True)
        except OSError:
            pass
        p = os.path.join(data_dir, name)
        if os.path.isfile(p):
            return p
    return None


@technik_bp.route('/layout/<string:diagram_id>')
@login_required
@menue_zugriff_erforderlich('technik_uebersichten')
def technik_layout_svg(diagram_id: str):
    diagramme = _build_layout_diagramme()
    d = _diagram_by_id((diagram_id or '').strip(), diagramme)
    if not d:
        abort(404)
    path = _resolve_technik_layout_file(d)
    if not path:
        abort(404)
    return send_file(path, mimetype='image/svg+xml', max_age=0)


@technik_bp.route('/uebersichten')
@login_required
@menue_zugriff_erforderlich('technik_uebersichten')
def uebersichten():
    diagramme = _build_layout_diagramme()
    if not diagramme:
        abort(404)

    requested = (request.args.get('diagram') or '').strip()
    current = _diagram_by_id(requested, diagramme) if requested else None
    if current is None:
        current = diagramme[0]

    svg_url = url_for('technik.technik_layout_svg', diagram_id=current['id'])
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
        diagramme=diagramme,
        current_diagram=current,
        current_svg_url=svg_url,
        layout_hotspots=layout_hotspots,
        layout_hotspot_config=layout_hotspot_config,
        beleuchtung_initial=beleuchtung_initial,
        beleuchtung_redis_configured=beleuchtung_redis_configured,
    )


@technik_bp.route('/beleuchtung/command', methods=['POST'])
@login_required
@menue_zugriff_erforderlich('technik_uebersichten')
def beleuchtung_command():
    payload = request.get_json(silent=True) or {}
    raw_id = str(payload.get('id') or '').strip()
    if not raw_id:
        return jsonify({'ok': False, 'message': 'Fehlende ID.'}), 400

    m = re.match(r'^(?:BL)?(\d+)$', raw_id, flags=re.IGNORECASE)
    if not m:
        return jsonify({'ok': False, 'message': 'Ungültige BL-ID.'}), 400
    lamp_id = m.group(1)

    target_on = payload.get('target_on')
    if isinstance(target_on, bool):
        on_bool = target_on
    elif isinstance(target_on, (int, float)):
        on_bool = bool(int(target_on))
    elif isinstance(target_on, str):
        t = target_on.strip().lower()
        if t in ('1', 'true', 'on', 'ein', 'an'):
            on_bool = True
        elif t in ('0', 'false', 'off', 'aus'):
            on_bool = False
        else:
            return jsonify({'ok': False, 'message': 'Ungültiger Zielzustand.'}), 400
    else:
        return jsonify({'ok': False, 'message': 'Ungültiger Zielzustand.'}), 400

    ok, info = publish_beleuchtung_command(lamp_id=lamp_id, target_on=on_bool)
    if not ok:
        return jsonify({'ok': False, 'message': info}), 502
    return jsonify({'ok': True, 'id': lamp_id, 'target_on': on_bool, 'topic': info})


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
