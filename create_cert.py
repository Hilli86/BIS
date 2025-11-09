#!/usr/bin/env python3
"""Erstellt ein Self-Signed SSL-Zertifikat für BIS"""

import os
import subprocess
import sys
import re

CERT_DIR = "/etc/nginx/ssl/bis"
SERVER_NAME = sys.argv[1] if len(sys.argv) > 1 else "bis-server.local"

# Verzeichnis erstellen
os.makedirs(CERT_DIR, exist_ok=True)

# Prüfen ob es eine IP-Adresse ist (Format: xxx.xxx.xxx.xxx)
is_ip = re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', SERVER_NAME)

# Subject Alternative Names erstellen
# WICHTIG: Moderne Browser benötigen SANs, besonders bei IP-Adressen!
if is_ip:
    # Wenn IP-Adresse: IP in SANs hinzufügen (nicht DNS!)
    print(f"Erkenne IP-Adresse: {SERVER_NAME}")
    san_string = f"IP:{SERVER_NAME},IP:127.0.0.1,DNS:localhost"
else:
    # Wenn Hostname: DNS in SANs hinzufügen
    print(f"Erkenne Hostname: {SERVER_NAME}")
    san_string = f"DNS:{SERVER_NAME},DNS:*.{SERVER_NAME},IP:127.0.0.1"

# Zertifikat erstellen mit SANs
cmd = [
    "openssl", "req", "-x509", "-nodes", "-days", "3650",
    "-newkey", "rsa:4096",
    "-keyout", f"{CERT_DIR}/bis.key",
    "-out", f"{CERT_DIR}/bis.crt",
    "-subj", f"/C=DE/ST=State/L=City/O=BIS/CN={SERVER_NAME}",
    "-addext", f"subjectAltName={san_string}"
]

subprocess.run(cmd, check=True)

# Berechtigungen setzen
os.chmod(f"{CERT_DIR}/bis.key", 0o600)
os.chmod(f"{CERT_DIR}/bis.crt", 0o644)

print(f"✓ Zertifikat erstellt für: {SERVER_NAME}")
print(f"  Key: {CERT_DIR}/bis.key")
print(f"  Cert: {CERT_DIR}/bis.crt")
print(f"  SANs: {san_string}")

