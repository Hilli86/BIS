"""
Hilfsfunktionen für WebAuthn / Passkeys (biometrische Anmeldung).

Verwendet die Bibliothek `fido2`, um Challenges zu erzeugen und Antworten zu prüfen.
Die state-Informationen von python-fido2 werden pro Prozess in einem einfachen
In-Memory-Store gehalten und über eine ID in der Flask-Session referenziert.
"""

import base64
import os
import uuid
from typing import Any, Dict, List, Tuple

from flask import current_app
from fido2 import cbor
from fido2.cose import CoseKey
from fido2.server import Fido2Server
from fido2.webauthn import (
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialUserEntity,
    AttestedCredentialData,
    PublicKeyCredentialDescriptor,
    Aaguid,
)


_STATE_STORE: Dict[str, Any] = {}


def _b64url_encode(data: Any) -> str:
    """
    Hilfsfunktion für Base64URL-Encoding.
    Akzeptiert sowohl Bytes als auch Strings und gibt einen str zurück.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def get_fido2_server() -> Fido2Server:
    """Erzeugt eine Fido2Server-Instanz basierend auf der Flask-Konfiguration."""
    rp = PublicKeyCredentialRpEntity(
        id=current_app.config["WEBAUTHN_RP_ID"],
        name=current_app.config["WEBAUTHN_RP_NAME"],
    )
    return Fido2Server(rp)


def store_state(state: Any) -> str:
    """Speichert den von Fido2Server zurückgegebenen State im Prozessspeicher."""
    state_id = str(uuid.uuid4())
    _STATE_STORE[state_id] = state
    return state_id


def pop_state(state_id: str) -> Any:
    """Liest einen gespeicherten State und entfernt ihn aus dem Store."""
    return _STATE_STORE.pop(state_id, None)


def build_user_entity(user_row) -> PublicKeyCredentialUserEntity:
    """Erzeugt die UserEntity für WebAuthn basierend auf einem Mitarbeiter-DB-Row."""
    user_id_bytes = str(user_row["ID"]).encode("utf-8")
    display_name = f"{user_row['Vorname']} {user_row['Nachname']}".strip() or str(
        user_row["Personalnummer"]
    )
    return PublicKeyCredentialUserEntity(
        id=user_id_bytes,
        name=str(user_row["Personalnummer"]),
        display_name=display_name,
    )


def build_existing_credentials(rows) -> List[PublicKeyCredentialDescriptor]:
    """Erzeugt die Liste vorhandener Credentials für authenticate_begin / register_begin."""
    creds: List[PublicKeyCredentialDescriptor] = []
    for row in rows:
        try:
            cred_id_bytes = _b64url_decode(row["CredentialID"])
        except Exception:
            continue
        creds.append(
            PublicKeyCredentialDescriptor(id=cred_id_bytes, type="public-key")
        )
    return creds


def build_attested_credentials(rows) -> List[AttestedCredentialData]:
    """
    Erzeugt eine Liste von AttestedCredentialData-Objekten für authenticate_complete().
    Erwartet Rows mit Feldern "CredentialID" (base64url) und "PublicKey" (base64url
    des CBOR-codierten COSE-Schlüssels).
    """
    creds: List[AttestedCredentialData] = []
    for row in rows:
        try:
            cred_id_bytes = _b64url_decode(row["CredentialID"])
            pubkey_bytes = _b64url_decode(row["PublicKey"])
            pubkey_dict = cbor.decode(pubkey_bytes)
            pubkey_cose = CoseKey.parse(pubkey_dict)
            acd = AttestedCredentialData.create(Aaguid.NONE, cred_id_bytes, pubkey_cose)
            creds.append(acd)
        except Exception as e:
            # Logging für Debugging, aber nicht abbrechen - andere Credentials könnten funktionieren
            import traceback
            print(f"Fehler beim Laden eines Credentials (ID: {row.get('CredentialID', 'unbekannt')[:20]}...): {e}")
            print(traceback.format_exc())
            continue
    return creds


def serialize_registration_options(public_key: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialisiert die von Fido2Server.register_begin gelieferten Optionen so,
    dass sie direkt an navigator.credentials.create() im Browser gegeben werden können.
    """
    # python-fido2 kann entweder direkt ein Dict mit den Feldern der
    # PublicKeyCredentialCreationOptions zurückgeben oder ein Objekt,
    # das eine "publicKey"-Eigenschaft enthält. Wir normalisieren das hier.
    pk = dict(public_key)

    # Falls das eigentliche publicKey-Objekt noch verschachtelt ist
    if "publicKey" in pk and "challenge" not in pk:
        pk = dict(pk["publicKey"])

    # challenge: nur Bytes in base64url wandeln, Strings unverändert lassen
    challenge = pk.get("challenge")
    if isinstance(challenge, (bytes, bytearray)):
        pk["challenge"] = _b64url_encode(challenge)

    # user.id analog behandeln
    user = dict(pk["user"])
    user_id = user.get("id")
    if isinstance(user_id, (bytes, bytearray)):
        user["id"] = _b64url_encode(user_id)
    else:
        user["id"] = user_id
    pk["user"] = user

    # excludeCredentials: id-Feld ggf. von Bytes in base64url wandeln
    exclude_credentials = []
    for cred in pk.get("excludeCredentials", []):
        c = dict(cred)
        cid = c.get("id")
        if isinstance(cid, (bytes, bytearray)):
            c["id"] = _b64url_encode(cid)
        else:
            c["id"] = cid
        exclude_credentials.append(c)
    pk["excludeCredentials"] = exclude_credentials

    return pk


def serialize_authentication_options(public_key: Dict[str, Any]) -> Dict[str, Any]:
    """Serialisiert die Optionen für navigator.credentials.get()."""
    pk = dict(public_key)

    # Auch hier ggf. verschachteltes "publicKey"-Objekt entfalten
    if "publicKey" in pk and "challenge" not in pk:
        pk = dict(pk["publicKey"])

    # challenge: nur Bytes in base64url wandeln, Strings unverändert lassen
    challenge = pk.get("challenge")
    if isinstance(challenge, (bytes, bytearray)):
        pk["challenge"] = _b64url_encode(challenge)

    allow_credentials = []
    for cred in pk.get("allowCredentials", []):
        c = dict(cred)
        cid = c.get("id")
        if isinstance(cid, (bytes, bytearray)):
            c["id"] = _b64url_encode(cid)
        else:
            c["id"] = cid
        allow_credentials.append(c)
    pk["allowCredentials"] = allow_credentials

    return pk


def extract_attested_credential(auth_data) -> Tuple[str, str, int]:
    """
    Extrahiert CredentialID, PublicKey (base64url) und SignCount aus den Attestierungsdaten.
    """
    if not isinstance(auth_data.credential_data, AttestedCredentialData):
        raise ValueError("Ungültige Credential-Daten")

    cred_id = auth_data.credential_data.credential_id
    public_key = auth_data.credential_data.public_key  # CoseKey

    # Public Key als CBOR-codiertes COSE-Objekt speichern
    public_key_bytes = cbor.encode(public_key)

    cred_id_b64 = _b64url_encode(cred_id)
    public_key_b64 = _b64url_encode(public_key_bytes)
    # Neuere fido2-Version verwendet "counter" statt "sign_count"
    sign_count = getattr(auth_data, "sign_count", getattr(auth_data, "counter", 0))
    return cred_id_b64, public_key_b64, sign_count


def update_sign_count_row(row, new_sign_count: int) -> Dict[str, Any]:
    """Hilfsfunktion zum Aktualisieren des SignCount in einem Row-Dict (für Tests/Debug)."""
    data = dict(row)
    data["SignCount"] = new_sign_count
    return data


