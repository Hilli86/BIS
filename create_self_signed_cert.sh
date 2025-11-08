#!/bin/bash
# Script zum Erstellen eines Self-Signed SSL-Zertifikats für BIS

# Verzeichnis für Zertifikate erstellen
CERT_DIR="/etc/nginx/ssl/bis"
mkdir -p $CERT_DIR

# Server-IP oder Hostname (anpassen!)
SERVER_NAME="${1:-bis-server.local}"  # Standard: bis-server.local, kann auch IP sein

echo "Erstelle Self-Signed Certificate für: $SERVER_NAME"
echo "Verzeichnis: $CERT_DIR"

# Zertifikat erstellen (gültig für 10 Jahre)
openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
  -keyout $CERT_DIR/bis.key \
  -out $CERT_DIR/bis.crt \
  -subj "/C=DE/ST=State/L=City/O=BIS/CN=$SERVER_NAME" \
  -addext "subjectAltName=DNS:$SERVER_NAME,DNS:*.$SERVER_NAME,IP:127.0.0.1"

# Berechtigungen setzen
chmod 600 $CERT_DIR/bis.key
chmod 644 $CERT_DIR/bis.crt
chown root:root $CERT_DIR/bis.key $CERT_DIR/bis.crt

echo ""
echo "✓ Zertifikat erstellt!"
echo "  Key: $CERT_DIR/bis.key"
echo "  Cert: $CERT_DIR/bis.crt"
echo ""
echo "Sie können das Zertifikat jetzt in der Nginx-Konfiguration verwenden."

