"""Produktions-Konfiguration: SECRET_KEY darf nicht der Entwicklungs-Default sein."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_without_secret_key_exits_on_import():
    code = (
        "import os\n"
        "os.environ['FLASK_ENV'] = 'production'\n"
        "os.environ.pop('SECRET_KEY', None)\n"
        "import app\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    combined = (r.stderr or "") + (r.stdout or "")
    assert "SECRET_KEY" in combined
