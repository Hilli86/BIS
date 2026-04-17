"""
Helper Utilities
Hilfsfunktionen für Datenkonvertierung, Query-Building etc.
"""


def safe_get(row, key, default=None):
    """
    Sichere Zugriff auf sqlite3.Row oder dict Objekte
    
    Args:
        row: SQLite Row-Objekt oder Dictionary oder None
        key: Schlüssel/Spaltenname
        default: Standardwert wenn Schlüssel nicht existiert oder None
        
    Returns:
        Wert des Schlüssels oder default
    """
    if row is None:
        return default
    if hasattr(row, 'get'):
        return row.get(key, default)
    else:
        # sqlite3.Row - prüfe ob Key existiert und Wert nicht None ist
        try:
            value = row[key]
            return value if value is not None else default
        except (KeyError, IndexError):
            return default


def row_to_dict(row):
    """
    Konvertiert eine SQLite Row zu einem Dictionary
    
    Args:
        row: SQLite Row-Objekt oder None
        
    Returns:
        Dictionary mit den Row-Daten oder None
    """
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def build_sichtbarkeits_filter_query(base_query, sichtbare_abteilungen, params, table_alias='T', sichtbarkeit_table='SchichtbuchThemaSichtbarkeit', sichtbarkeit_id_column='ThemaID'):
    """
    Baut eine SQL-Query mit Sichtbarkeitsfilter auf
    
    Args:
        base_query: Basis-SQL-Query (muss mit WHERE enden oder bereits Filter enthalten)
        sichtbare_abteilungen: Liste von Abteilungs-IDs oder None/leere Liste
        params: Liste von Query-Parametern (wird erweitert)
        table_alias: Alias der Haupttabelle (Standard: 'T')
        sichtbarkeit_table: Name der Sichtbarkeitstabelle (Standard: 'SchichtbuchThemaSichtbarkeit')
        sichtbarkeit_id_column: Name der ID-Spalte in der Sichtbarkeitstabelle (Standard: 'ThemaID')
        
    Returns:
        Tuple (erweiterte_query, erweiterte_params)
    """
    query = base_query
    query_params = params.copy() if params else []
    
    if sichtbare_abteilungen:
        placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
        query += f''' AND EXISTS (
            SELECT 1 FROM {sichtbarkeit_table} sv
            WHERE sv.{sichtbarkeit_id_column} = {table_alias}.ID 
            AND sv.AbteilungID IN ({placeholders})
        )'''
        query_params.extend(sichtbare_abteilungen)
    
    return query, query_params


def format_file_size(size_bytes):
    """
    Formatiert Dateigröße in lesbares Format
    
    Args:
        size_bytes: Größe in Bytes
        
    Returns:
        Formatierter String (z.B. "1.5 MB" oder "512.0 KB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_ersatzteil_zugriff_filter(base_query, mitarbeiter_id, sichtbare_abteilungen, is_admin, params):
    """
    Baut eine SQL-Query mit Ersatzteil-Zugriffsfilter auf
    
    Args:
        base_query: Basis-SQL-Query (muss mit WHERE enden)
        mitarbeiter_id: ID des Mitarbeiters
        sichtbare_abteilungen: Liste von Abteilungs-IDs oder None/leere Liste
        is_admin: Ob Benutzer Admin ist
        params: Liste von Query-Parametern (wird erweitert)
        
    Returns:
        Tuple (erweiterte_query, erweiterte_params)
    """
    query = base_query
    query_params = params.copy() if params else []
    
    if not is_admin:
        if sichtbare_abteilungen:
            placeholders = ','.join(['?'] * len(sichtbare_abteilungen))
            query += f'''
                AND (
                    e.ErstelltVonID = ? OR
                    e.ID IN (
                        SELECT ErsatzteilID FROM ErsatzteilAbteilungZugriff
                        WHERE AbteilungID IN ({placeholders})
                    )
                )
            '''
            query_params.append(mitarbeiter_id)
            query_params.extend(sichtbare_abteilungen)
        else:
            # Keine Berechtigung - nur eigene Ersatzteile
            query += ' AND e.ErstelltVonID = ?'
            query_params.append(mitarbeiter_id)
    
    return query, query_params


def format_schichtbuch_datum(s):
    """
    Formatiert ein Schichtbuch-Datum aus SQLite (TEXT/DATETIME).
    Werte mit Uhrzeit 00:00:00 gelten als reines Kalenderdatum (Vorgangsdatum).
    """
    from datetime import datetime

    if not s:
        return ''
    s = str(s).strip()
    if len(s) >= 19 and s[10:19] == ' 00:00:00':
        try:
            return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d.%m.%Y')
        except ValueError:
            return s[:10] if len(s) >= 10 else s
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            n = 19 if fmt == '%Y-%m-%d %H:%M:%S' else 16
            dt = datetime.strptime(s[:n], fmt)
            return dt.strftime('%d.%m.%Y %H:%M')
        except ValueError:
            continue
    return s


def _ip_matches_trusted(remote_addr, trusted_entries):
    """Prueft, ob ``remote_addr`` in einer Liste aus Hosts/Netzen liegt."""
    if not remote_addr or not trusted_entries:
        return False
    try:
        import ipaddress
        ip = ipaddress.ip_address(remote_addr)
    except (ValueError, TypeError):
        return False
    for entry in trusted_entries:
        entry = (entry or '').strip()
        if not entry:
            continue
        try:
            if '/' in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if ip == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


def get_client_ip(request):
    """
    Öffentliche Client-IP hinter einem Reverse-Proxy (z. B. nginx).

    ``X-Forwarded-For`` / ``X-Real-IP`` werden nur ausgewertet, wenn die
    TCP-Gegenstelle (``request.remote_addr``) in der Konfiguration unter
    ``TRUSTED_PROXIES`` als vertrauenswuerdig gelistet ist. Andernfalls kann
    ein Angreifer die Header frei setzen und damit Rate-Limiting, Audit-Logs
    oder IP-basierte Checks umgehen.
    """
    remote = getattr(request, 'remote_addr', None) or ''
    trusted = []
    try:
        from flask import current_app
        cfg = current_app.config.get('TRUSTED_PROXIES') or ()
        if isinstance(cfg, str):
            trusted = [p.strip() for p in cfg.split(',') if p.strip()]
        else:
            trusted = list(cfg)
    except Exception:
        trusted = []

    if _ip_matches_trusted(remote, trusted):
        xff = (request.headers.get('X-Forwarded-For') or '').strip()
        if xff:
            return xff.split(',')[0].strip() or remote
        xri = (request.headers.get('X-Real-IP') or '').strip()
        if xri:
            return xri
    return remote

