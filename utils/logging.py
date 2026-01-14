"""
Logging Utilities für BIS
Zentrale Logging-Funktionen für die gesamte Anwendung
"""

import sys


def log_info(message):
    """Loggt eine Info-Nachricht direkt an stderr (für journalctl)"""
    print(f"[INFO] {message}", file=sys.stderr, flush=True)


def log_error(message):
    """Loggt eine Fehlernachricht direkt an stderr (für journalctl)"""
    print(f"[ERROR] {message}", file=sys.stderr, flush=True)


def log_warning(message):
    """Loggt eine Warnung direkt an stderr (für journalctl)"""
    print(f"[WARNING] {message}", file=sys.stderr, flush=True)


def log_debug(message):
    """Loggt eine Debug-Nachricht direkt an stderr (für journalctl)"""
    print(f"[DEBUG] {message}", file=sys.stderr, flush=True)

