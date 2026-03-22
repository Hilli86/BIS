"""
VAPID-Schlüssel für Web-Push (einmalig pro Installation erzeugen).

Die private PEM-Datei kann als VAPID_PRIVATE_KEY gesetzt werden (Pfad oder Inhalt).
Der öffentliche Key (eine Zeile Base64-URL) gehört in VAPID_PUBLIC_KEY.
"""

from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pywebpush import Vapid01
from py_vapid.utils import b64urlencode


def generate_vapid_files(pem_path: str | Path) -> str:
    """
    Erzeugt ein VAPID-Schlüsselpaar und speichert den privaten Schlüssel als PEM.

    Args:
        pem_path: Zielpfad für die private PEM-Datei

    Returns:
        Öffentlicher Schlüssel (Base64-URL, eine Zeile) für VAPID_PUBLIC_KEY
    """
    path = Path(pem_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    v = Vapid01()
    v.generate_keys()
    v.save_key(str(path))

    raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return b64urlencode(raw)


def _load_vapid01_from_private(private_key: str) -> Vapid01:
    """Privaten Schlüssel aus PEM-Text oder Pfad zu einer PEM-Datei laden."""
    p = private_key.strip()
    path = Path(p)
    if path.is_file():
        raw = path.read_text(encoding='utf-8')
    else:
        raw = p
    # PEM muss mit from_pem kommen; from_string() nur für Raw/DER (ohne Header)
    if '-----BEGIN' in raw:
        return Vapid01.from_pem(raw.encode('utf-8'))
    return Vapid01.from_string(raw)


def verify_vapid_pair(private_key: str | None, public_key_b64: str | None) -> tuple[bool, str]:
    """
    Prüft, ob VAPID_PUBLIC_KEY zum privaten Schlüssel passt (gleiches Schlüsselpaar).

    Returns:
        (True, kurzer_ok_text) oder (False, fehlerbeschreibung)
    """
    if not private_key or not str(private_key).strip():
        return False, 'VAPID_PRIVATE_KEY fehlt.'
    if not public_key_b64 or not str(public_key_b64).strip():
        return False, 'VAPID_PUBLIC_KEY fehlt.'
    try:
        v = _load_vapid01_from_private(str(private_key))
        raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        derived = b64urlencode(raw)
    except Exception as e:
        return False, f'Privater Schlüssel ungültig oder nicht lesbar: {e}'
    want = str(public_key_b64).strip()
    if derived != want:
        return (
            False,
            'VAPID_PUBLIC_KEY stimmt nicht mit VAPID_PRIVATE_KEY überein. '
            'Mit flask vapid-generate neu erzeugen oder beide Werte aus derselben Erzeugung kopieren.',
        )
    return True, 'VAPID-Schlüsselpaar ist konsistent.'
