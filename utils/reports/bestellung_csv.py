"""
CSV-Export für Bestellpositionen (Reihenfolge pro Lieferant konfigurierbar).
"""

import csv
import io
import re
from datetime import datetime

# Schlüssel → deutsche Spaltenüberschrift (Kopfzeile)
CSV_COLUMN_LABELS = {
    'bestellnummer': 'Bestellnummer',
    'bezeichnung': 'Bezeichnung',
    'menge': 'Menge',
    'einheit': 'Einheit',
    'preis': 'Preis',
    'waehrung': 'Währung',
    'bemerkung': 'Bemerkung',
    'link': 'Link',
    'ersatzteil_id': 'Ersatzteil-ID',
    'position_id': 'Positions-ID',
    'kostenstelle': 'Kostenstelle',
    'bestellung_id': 'Bestellung-ID',
    'lieferant_name': 'Lieferant',
}

DEFAULT_COLUMN_KEYS = [
    'bestellnummer',
    'bezeichnung',
    'menge',
    'einheit',
    'preis',
    'waehrung',
]


def _csv_delimiter_from_config(config_raw):
    """
    Leere Konfiguration → Semikolon (wie bisher, typisch für Excel DE).
    Sonst: gleiches Trennzeichen wie in der Eingabe – zuerst auftretendes
    Komma vs. Semikolon, bei nur einem der beiden dieses Zeichen.
    """
    if not config_raw or not str(config_raw).strip():
        return ';'
    s = str(config_raw)
    n_comma = s.count(',')
    n_semi = s.count(';')
    if n_comma == 0 and n_semi == 0:
        return ';'
    if n_semi == 0:
        return ','
    if n_comma == 0:
        return ';'
    ic = s.find(',')
    is_ = s.find(';')
    if ic == -1:
        return ';'
    if is_ == -1:
        return ','
    return ',' if ic < is_ else ';'


def _parse_column_keys(config_raw):
    """Komma- oder Semikolon-getrennte Platzhalter; unbekannte Einträge werden verworfen."""
    if not config_raw or not str(config_raw).strip():
        return list(DEFAULT_COLUMN_KEYS)
    parts = re.split(r'[;,]', str(config_raw))
    tokens = [p.strip().lower() for p in parts if p.strip()]
    valid = [t for t in tokens if t in CSV_COLUMN_LABELS]
    return valid if valid else list(DEFAULT_COLUMN_KEYS)


def _format_preis(val):
    if val is None:
        return ''
    try:
        return f'{float(val):.2f}'.replace('.', ',')
    except (TypeError, ValueError):
        return str(val)


def _cell_value(key, pos, bestellung_id, lieferant_name):
    if key == 'bestellnummer':
        return pos['Bestellnummer'] or ''
    if key == 'bezeichnung':
        return pos['Bezeichnung'] or ''
    if key == 'menge':
        return pos['Menge'] if pos['Menge'] is not None else ''
    if key == 'einheit':
        return pos['Einheit'] or ''
    if key == 'preis':
        return _format_preis(pos['Preis'])
    if key == 'waehrung':
        return pos['Waehrung'] or ''
    if key == 'bemerkung':
        return pos['Bemerkung'] or ''
    if key == 'link':
        return pos['Link'] or ''
    if key == 'ersatzteil_id':
        v = pos['ErsatzteilID']
        return v if v is not None else ''
    if key == 'position_id':
        return pos['ID']
    if key == 'kostenstelle':
        return pos['Kostenstelle'] or ''
    if key == 'bestellung_id':
        return bestellung_id
    if key == 'lieferant_name':
        return lieferant_name or ''
    return ''


def generate_bestellung_csv_bytes(bestellung_id, conn):
    """
    Erzeugt CSV-Inhalt (UTF-8 mit BOM) und Dateinamen.
    Raises ValueError wie PDF-Export bei ungültigem Status / fehlender Bestellung.
    """
    row = conn.execute(
        '''
        SELECT
            b.ID,
            b.Status,
            b.LieferantID,
            l.Name AS LieferantName,
            l.CsvExportReihenfolge AS CsvExportReihenfolge
        FROM Bestellung b
        LEFT JOIN Lieferant l ON b.LieferantID = l.ID
        WHERE b.ID = ? AND b.Gelöscht = 0
        ''',
        (bestellung_id,),
    ).fetchone()

    if not row:
        raise ValueError('Bestellung nicht gefunden.')

    if row['Status'] not in ('Freigegeben', 'Bestellt'):
        raise ValueError(
            'CSV kann nur für freigegebene oder bestellte Bestellungen exportiert werden.'
        )

    lieferant_name = row['LieferantName'] or ''
    config_raw = row['CsvExportReihenfolge']
    column_keys = _parse_column_keys(config_raw)
    delimiter = _csv_delimiter_from_config(config_raw)

    positionen = conn.execute(
        '''
        SELECT
            p.*,
            e.ID AS ErsatzteilID,
            COALESCE(p.Bestellnummer, e.Bestellnummer) AS Bestellnummer,
            COALESCE(p.Bezeichnung, e.Bezeichnung) AS Bezeichnung,
            COALESCE(p.Einheit, e.Einheit, 'Stück') AS Einheit,
            COALESCE(p.Link, e.Link) AS Link,
            k.Bezeichnung AS Kostenstelle
        FROM BestellungPosition p
        LEFT JOIN Ersatzteil e ON p.ErsatzteilID = e.ID
        LEFT JOIN Kostenstelle k ON p.KostenstelleID = k.ID
        WHERE p.BestellungID = ?
        ORDER BY p.ID
        ''',
        (bestellung_id,),
    ).fetchall()

    header = [CSV_COLUMN_LABELS[k] for k in column_keys]

    buffer = io.StringIO(newline='')
    writer = csv.writer(
        buffer, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL
    )
    writer.writerow(header)

    for pos in positionen:
        writer.writerow(
            [_cell_value(k, pos, bestellung_id, lieferant_name) for k in column_keys]
        )

    text = buffer.getvalue()
    bom = '\ufeff'
    data = (bom + text).encode('utf-8')

    datum = datetime.now().strftime('%Y%m%d')
    filename = f'Bestellung_{bestellung_id}_{datum}.csv'
    return data, filename
