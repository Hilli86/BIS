#!/usr/bin/env python3
"""Erstellt ein Self-Signed SSL-Zertifikat für BIS"""

import os
import subprocess
import sys

CERT_DIR = "/etc/nginx/ssl/bis"
SERVER_NAME = sys.argv[1] if len(sys.argv) > 1 else "bis-server.local"

# Verzeichnis erstellen
os.makedirs(CERT_DIR, exist_ok=True)

# Zertifikat erstellen
cmd = [
    "openssl", "req", "-x509", "-nodes", "-days", "3650",
    "-newkey", "rsa:4096",
    "-keyout", f"{CERT_DIR}/bis.key",
    "-out", f"{CERT_DIR}/bis.crt",
    "-subj", f"/C=DE/ST=State/L=City/O=BIS/CN={SERVER_NAME}"
]

subprocess.run(cmd, check=True)

# Berechtigungen setzen
os.chmod(f"{CERT_DIR}/bis.key", 0o600)
os.chmod(f"{CERT_DIR}/bis.crt", 0o644)

print(f"✓ Zertifikat erstellt für: {SERVER_NAME}")
print(f"  Key: {CERT_DIR}/bis.key")
print(f"  Cert: {CERT_DIR}/bis.crt")

