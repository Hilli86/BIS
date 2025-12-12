#!/usr/bin/env python3
"""Erstellt ein Self-Signed SSL-Zertifikat für BIS auf Windows"""
import os
import subprocess
import sys
import re

# Windows-Pfade
CERT_DIR = r"C:\nginx\conf\ssl\bis"
SERVER_NAME = sys.argv[1] if len(sys.argv) > 1 else "localhost"

# Verzeichnis erstellen
os.makedirs(CERT_DIR, exist_ok=True)

print(f"Erstelle Self-Signed Certificate für: {SERVER_NAME}")
print(f"Verzeichnis: {CERT_DIR}")

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

# Pfade für Zertifikat-Dateien
key_path = os.path.join(CERT_DIR, "bis.key")
cert_path = os.path.join(CERT_DIR, "bis.crt")

# Alte Zertifikate sichern (falls vorhanden)
if os.path.exists(key_path):
    import shutil
    from datetime import datetime
    backup_key = f"{key_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(key_path, backup_key)
    print(f"Alter Key gesichert: {backup_key}")

if os.path.exists(cert_path):
    import shutil
    from datetime import datetime
    backup_cert = f"{cert_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(cert_path, backup_cert)
    print(f"Altes Zertifikat gesichert: {backup_cert}")

# Zertifikat erstellen mit SANs
print("\nErstelle Zertifikat...")
cmd = [
    "openssl", "req", "-x509", "-nodes", "-days", "3650",
    "-newkey", "rsa:4096",
    "-keyout", key_path,
    "-out", cert_path,
    "-subj", f"/C=DE/ST=State/L=City/O=BIS/CN={SERVER_NAME}",
    "-addext", f"subjectAltName={san_string}"
]

try:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    print("\n✓ Zertifikat erfolgreich erstellt!")
    print(f"  Key: {key_path}")
    print(f"  Cert: {cert_path}")
    print(f"  SANs: {san_string}")
    print("\nSie können das Zertifikat jetzt in der Nginx-Konfiguration verwenden.")
    
    # Zertifikat-Details anzeigen
    print("\nZertifikat-Details:")
    detail_cmd = ["openssl", "x509", "-in", cert_path, "-text", "-noout"]
    detail_result = subprocess.run(detail_cmd, capture_output=True, text=True)
    if detail_result.returncode == 0:
        lines = detail_result.stdout.split('\n')
        for i, line in enumerate(lines):
            if 'Subject:' in line or 'Issuer:' in line or 'Subject Alternative Name' in line:
                print(line)
                # Zeige auch die nächsten 2 Zeilen für Kontext
                for j in range(1, 3):
                    if i + j < len(lines):
                        print(lines[i + j])
    
except FileNotFoundError:
    print("\nFEHLER: OpenSSL ist nicht installiert oder nicht im PATH!", file=sys.stderr)
    print("\nBitte installieren Sie OpenSSL für Windows:")
    print("  - Download: https://slproweb.com/products/Win32OpenSSL.html")
    print("  - Oder via Chocolatey: choco install openssl")
    sys.exit(1)
except subprocess.CalledProcessError as e:
    print(f"\nFEHLER: OpenSSL-Befehl fehlgeschlagen!", file=sys.stderr)
    print(f"Fehler: {e.stderr}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"\nFEHLER beim Erstellen des Zertifikats: {e}", file=sys.stderr)
    sys.exit(1)

print("\nFertig!")

