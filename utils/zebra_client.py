"""
Hilfsfunktionen fuer Zebra-ZPL-Drucker (Netzwerkdrucker).

Unterstuetzt zwei Versandwege je Drucker:

- agent_id IS NULL  -> Direkt-TCP vom Server (klassisch, send_zpl_to_printer)
- agent_id gesetzt  -> Auftrag in print_jobs; ein on-prem Druck-Agent holt ab.

dispatch_print() entscheidet anhand zebra_printers.agent_id automatisch.
"""

import socket
import time
from typing import Optional

# Zebra Standard-Etikettendichte für Dot-Berechnung aus Millimetern
ZPL_DOTS_PER_MM_203 = 203 / 25.4


def zpl_header_from_dimensions(width_mm: int, height_mm: int) -> str:
    """
    Erzeugt den ZPL-Grundheader (^PW, ^LL) aus Breite und Höhe in mm.

    203 dpi: Druckbreite = width_mm, Etikettenlänge (Vorschub) = height_mm.
    """
    w_mm = int(width_mm)
    h_mm = int(height_mm)
    pw = max(1, int(round(w_mm * ZPL_DOTS_PER_MM_203)))
    ll = max(1, int(round(h_mm * ZPL_DOTS_PER_MM_203)))
    return f"^PW{pw}\n^LL{ll}"


def merge_zpl_header_base_and_extra(base_header: str, extra: Optional[str] = None) -> str:
    """Hängt optionale weitere ZPL-Befehle (eigene Zeilen) an den Grundheader an."""
    t = (extra or "").strip()
    if not t:
        return (base_header or "").strip()
    return f"{(base_header or '').strip()}\n{t}"


def send_zpl_to_printer(printer_ip: str, zpl: str, port: int = 9100, timeout: float = 5.0) -> None:
    """
    Sendet einen ZPL-String an einen Zebra-Netzwerkdrucker.

    :param printer_ip: IP-Adresse oder Hostname des Druckers
    :param zpl: Vollständiger ZPL-String (^XA ... ^XZ)
    :param port: TCP-Port (Standard bei Zebra: 9100)
    :param timeout: Socket-Timeout in Sekunden
    """
    if not printer_ip:
        raise ValueError("printer_ip darf nicht leer sein")
    if not zpl:
        raise ValueError("zpl darf nicht leer sein")

    # Debug: jeder Druckbefehl in der Server-Konsole (Flask/Werkzeug)
    print("===== BIS ZPL-Druck (Debug) =====")
    print(f"Ziel: {printer_ip}:{port}")
    print(zpl)
    print("===== Ende ZPL =====")

    data = zpl.encode("utf-8")
    with socket.create_connection((printer_ip, port), timeout=timeout) as sock:
        sock.sendall(data)


def _test_label_demo_body(label_text: str) -> str:
    """ZPL-Teil nach dem Etikettenformat: Kodierung, Rahmen, Demo-Text, Ende."""
    lines = [
        "^CI28",
        "^FO10,10^GB600,1200,2^FS",
        f"^FO30,60^A0N,40,40^FDTEST {label_text}^FS",
        "^FO30,120^A0N,25,25^FD203 dpi^FS",
        "^XZ",
    ]
    return "\n".join(lines)


def zpl_test_label_preview_segments(zpl_header: str, label_name: Optional[str] = None) -> dict:
    """
    Zerlegt das Testetikett in ZPL-Start, Etikettenformat-Block und Vorschau-Ergänzung.

    Keys: ``full``, ``xa``, ``format``, ``demo`` (letzteres ab ^CI28 bis ^XZ).
    """
    label_text = label_name or "TEST"
    demo = _test_label_demo_body(label_text)
    fmt = zpl_header if zpl_header is not None else ""
    full = "\n".join(["^XA", fmt, demo])
    return {"full": full, "xa": "^XA", "format": fmt, "demo": demo}


def build_test_label(zpl_header: str, label_name: Optional[str] = None) -> str:
    """
    Erstellt ein einfaches Testetikett basierend auf einem ZPL-Header.

    :param zpl_header: ZPL-Header mit ^PW, ^LL und optional weiteren Befehlen
    :param label_name: Optionaler Anzeigename des Etiketts fuer den TEST-Text
    :return: Vollstaendiger ZPL-String
    """
    return zpl_test_label_preview_segments(zpl_header, label_name)["full"]


# ---------------------------------------------------------------------------
# Druckwarteschlange / Dispatcher (Hybrid: Direkt-TCP oder Agent-Queue)
# ---------------------------------------------------------------------------


def _load_drucker_dispatch_row(conn, drucker_id):
    """Drucker-Zeile mit ip_address, agent_id, name fuer den Dispatch."""
    if drucker_id is None:
        return None
    return conn.execute(
        '''SELECT id, name, ip_address, agent_id, active
           FROM zebra_printers WHERE id = ?''',
        (drucker_id,),
    ).fetchone()


def enqueue_print_job(conn, drucker_id, zpl, mitarbeiter_id=None):
    """
    Legt einen Druckauftrag in print_jobs an.
    Voraussetzung: Drucker ist einem print_agents-Eintrag zugeordnet.

    Gibt die job_id zurueck. Loest ValueError aus, wenn Drucker keinen Agent hat
    oder die Eingaben unvollstaendig sind.
    """
    if not zpl:
        raise ValueError('zpl darf nicht leer sein')
    row = _load_drucker_dispatch_row(conn, drucker_id)
    if not row:
        raise ValueError('Drucker nicht gefunden.')
    if row['agent_id'] is None:
        raise ValueError('Drucker hat keinen Druck-Agent (agent_id ist NULL).')
    cur = conn.execute(
        '''INSERT INTO print_jobs
               (agent_id, drucker_id, zpl, status, attempts, created_by_mitarbeiter_id, created_at)
           VALUES (?, ?, ?, 'pending', 0, ?, datetime('now'))''',
        (row['agent_id'], drucker_id, zpl, mitarbeiter_id),
    )
    conn.commit()
    return cur.lastrowid


def get_print_job_status(conn, job_id):
    """Aktuellen Status + Fehlermeldung eines Auftrags zurueckgeben (oder None)."""
    return conn.execute(
        '''SELECT id, status, attempts, error_message, completed_at
           FROM print_jobs WHERE id = ?''',
        (job_id,),
    ).fetchone()


def wait_for_job(conn, job_id, timeout: float = 4.0, poll_interval: float = 0.25):
    """
    Wartet kurz auf Endstatus eines Auftrags (done|error|expired) oder gibt
    den letzten Status zurueck. Liefert ein dict mit status/error_message.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        row = get_print_job_status(conn, job_id)
        if row is None:
            return {'status': 'unknown', 'error_message': None}
        status = row['status']
        if status in ('done', 'error', 'expired'):
            return {'status': status, 'error_message': row['error_message']}
        if time.monotonic() >= deadline:
            return {'status': status, 'error_message': row['error_message']}
        time.sleep(poll_interval)


def dispatch_print(conn, drucker_id, zpl, mitarbeiter_id=None, wait_seconds: float = 4.0):
    """
    Zentrale API: druckt direkt oder ueber Agent-Queue, je nach zebra_printers.agent_id.

    Rueckgabewerte:

    - {'mode': 'direct', 'ok': True}
    - {'mode': 'direct', 'ok': False, 'error_message': str}
    - {'mode': 'agent', 'ok': True, 'job_id': int, 'status': 'done'|'pending'|'leased'|...}
    - {'mode': 'agent', 'ok': False, 'job_id': int|None, 'status': str, 'error_message': str}

    Bei Direktdruck wird die Verbindung sofort aufgebaut. Bei Agent-Queue wird
    bis zu ``wait_seconds`` synchron auf das Endergebnis gewartet (Default 4s);
    laeuft das Fenster ab, ist ``ok`` True (uebergeben) und ``status`` z. B.
    ``pending`` oder ``leased``.
    """
    row = _load_drucker_dispatch_row(conn, drucker_id)
    if not row:
        return {'mode': 'direct', 'ok': False, 'error_message': 'Drucker nicht gefunden.'}

    if row['agent_id'] is None:
        try:
            send_zpl_to_printer(row['ip_address'], zpl)
            return {'mode': 'direct', 'ok': True}
        except Exception as e:
            return {
                'mode': 'direct',
                'ok': False,
                'error_message': f'Fehler beim Senden an Drucker: {e}',
            }

    try:
        job_id = enqueue_print_job(conn, drucker_id, zpl, mitarbeiter_id)
    except Exception as e:
        return {
            'mode': 'agent',
            'ok': False,
            'job_id': None,
            'status': 'error',
            'error_message': f'Auftrag konnte nicht eingestellt werden: {e}',
        }

    res = wait_for_job(conn, job_id, timeout=wait_seconds)
    status = res['status']
    if status == 'error':
        return {
            'mode': 'agent',
            'ok': False,
            'job_id': job_id,
            'status': status,
            'error_message': res.get('error_message') or 'Druck fehlgeschlagen.',
        }
    return {
        'mode': 'agent',
        'ok': True,
        'job_id': job_id,
        'status': status,
    }


# ---------------------------------------------------------------------------
# Agent-seitige Helfer (Lease-Recovery, Cleanup)
# ---------------------------------------------------------------------------

PRINT_JOB_LEASE_SECONDS = 60
PRINT_JOB_MAX_ATTEMPTS = 3
PRINT_JOB_RETENTION_DAYS = 7


def recover_expired_leases(conn, lease_seconds: int = PRINT_JOB_LEASE_SECONDS):
    """Auftraege mit abgelaufenem Lease (Crash des Agents) wieder auf pending setzen."""
    cur = conn.execute(
        '''UPDATE print_jobs
              SET status = 'pending', lease_until = NULL
            WHERE status = 'leased'
              AND lease_until IS NOT NULL
              AND lease_until < datetime('now')''',
    )
    conn.commit()
    return cur.rowcount


def cleanup_old_jobs(conn, retention_days: int = PRINT_JOB_RETENTION_DAYS):
    """Erledigte/abgebrochene Auftraege aelter als retention_days entfernen."""
    cur = conn.execute(
        '''DELETE FROM print_jobs
            WHERE status IN ('done', 'expired')
              AND completed_at IS NOT NULL
              AND completed_at < datetime('now', ?)''',
        (f'-{int(retention_days)} days',),
    )
    conn.commit()
    return cur.rowcount


def lease_next_job(conn, agent_id: int, lease_seconds: int = PRINT_JOB_LEASE_SECONDS):
    """
    Holt atomar den naechsten pending-Auftrag fuer einen Agent und setzt
    Status auf 'leased' inkl. lease_until. Gibt die Job-Zeile (mit ZPL,
    Drucker-Daten) zurueck oder None.
    """
    recover_expired_leases(conn, lease_seconds)
    row = conn.execute(
        '''SELECT id FROM print_jobs
            WHERE agent_id = ? AND status = 'pending'
            ORDER BY id ASC LIMIT 1''',
        (agent_id,),
    ).fetchone()
    if not row:
        return None
    job_id = row['id']
    cur = conn.execute(
        '''UPDATE print_jobs
              SET status = 'leased',
                  attempts = attempts + 1,
                  lease_until = datetime('now', ?)
            WHERE id = ? AND status = 'pending' AND agent_id = ?''',
        (f'+{int(lease_seconds)} seconds', job_id, agent_id),
    )
    if cur.rowcount == 0:
        conn.commit()
        return None
    conn.commit()
    return conn.execute(
        '''SELECT j.id, j.agent_id, j.drucker_id, j.zpl, j.attempts,
                  p.name AS drucker_name, p.ip_address AS drucker_ip
             FROM print_jobs j
             JOIN zebra_printers p ON j.drucker_id = p.id
            WHERE j.id = ?''',
        (job_id,),
    ).fetchone()


def mark_job_done(conn, agent_id: int, job_id: int):
    """Auftrag als erledigt markieren (nur wenn er zum Agent gehoert)."""
    cur = conn.execute(
        '''UPDATE print_jobs
              SET status = 'done',
                  completed_at = datetime('now'),
                  error_message = NULL,
                  lease_until = NULL
            WHERE id = ? AND agent_id = ?''',
        (job_id, agent_id),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_job_error(
    conn,
    agent_id: int,
    job_id: int,
    error_message: str,
    max_attempts: int = PRINT_JOB_MAX_ATTEMPTS,
):
    """
    Fehler melden. Wenn Versuche < max_attempts: zurueck auf pending fuer Retry,
    sonst Endstatus 'error'.
    """
    row = conn.execute(
        '''SELECT attempts FROM print_jobs WHERE id = ? AND agent_id = ?''',
        (job_id, agent_id),
    ).fetchone()
    if row is None:
        return False
    if row['attempts'] >= max_attempts:
        conn.execute(
            '''UPDATE print_jobs
                  SET status = 'error',
                      completed_at = datetime('now'),
                      error_message = ?,
                      lease_until = NULL
                WHERE id = ? AND agent_id = ?''',
            (error_message[:500] if error_message else None, job_id, agent_id),
        )
    else:
        conn.execute(
            '''UPDATE print_jobs
                  SET status = 'pending',
                      error_message = ?,
                      lease_until = NULL
                WHERE id = ? AND agent_id = ?''',
            (error_message[:500] if error_message else None, job_id, agent_id),
        )
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Token-Helfer fuer print_agents (Erzeugung, Hash, Vergleich)
# ---------------------------------------------------------------------------

import hashlib
import hmac
import secrets


def generate_agent_token() -> str:
    """Erzeugt einen URL-sicheren Bearer-Token (>= 256 Bit Entropie)."""
    return secrets.token_urlsafe(32)


def hash_agent_token(token: str) -> str:
    """SHA-256 Hex-Hash eines Tokens (in DB nur Hash speichern)."""
    if not token:
        return ''
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def verify_agent_token(token: str, token_hash: str) -> bool:
    """Konstantzeitvergleich Token <-> gespeicherter Hash."""
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_agent_token(token), token_hash)


