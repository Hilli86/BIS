"""
Routen für Technik (SVG-Übersichten).
"""

from flask import abort, render_template, request, url_for

from utils.decorators import login_required, menue_zugriff_erforderlich

from . import technik_bp

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
    return render_template(
        'technik/uebersichten.html',
        diagramme=TECHNIK_DIAGRAMME,
        current_diagram=current,
        current_svg_url=svg_url,
        layout_hotspots=layout_hotspots,
        layout_hotspot_config=layout_hotspot_config,
    )
