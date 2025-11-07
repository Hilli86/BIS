#!/bin/bash

#########################################
# BIS - Make Scripts Executable
# Macht alle Deployment-Scripts ausführbar
# Als beliebiger Benutzer ausführbar
#########################################

echo "Setze Ausführungsrechte für alle Deployment-Scripts..."

# Zum Deployment-Verzeichnis wechseln
cd "$(dirname "$0")" || exit 1

# Alle .sh-Dateien ausführbar machen
chmod +x *.sh

echo "✓ Folgende Scripts sind jetzt ausführbar:"
ls -lh *.sh

echo ""
echo "Fertig! Sie können nun die Scripts nutzen:"
echo "  - install_server.sh (als root)"
echo "  - deploy_app.sh (als bis-Benutzer)"
echo "  - update_app.sh (als root)"
echo "  - backup_bis.sh (als root)"
echo "  - healthcheck.sh (als root)"



