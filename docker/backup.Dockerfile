# BIS � Backup-Service
# Alpine-basierter Container mit BusyBox-crond, sqlite und 7zip fuer naechtliche Backups.
# Build-Kontext: Projektroot (docker-compose: context: .)
FROM alpine:3.20

# Hinweis: bewusst KEIN 'dcron'. dcron's crond ruft beim Fork setpgid() auf,
# was als PID 1 unter Docker (insb. Docker Desktop / WSL2) mit
# "setpgid: Operation not permitted" abbricht und den Container in eine
# Restart-Schleife schickt. BusyBox liefert ein crond, das genau dies nicht tut.
RUN apk add --no-cache \
        bash \
        sqlite \
        7zip \
        tzdata \
        findutils \
        coreutils \
    && mkdir -p /usr/local/bin /var/log /backup-plain /backup-encrypted /etc/crontabs

COPY docker/backup/bis_backup.sh       /usr/local/bin/bis_backup.sh
COPY docker/backup/notify_admins.sh    /usr/local/bin/notify_admins.sh

# Falls die Shell-Skripte unter Windows mit CRLF gespeichert wurden: Line-Endings normalisieren,
# sonst schlaegt /bin/bash im Linux-Container fehl (Shebang wird nicht gefunden).
RUN sed -i 's/\r$//' /usr/local/bin/bis_backup.sh /usr/local/bin/notify_admins.sh \
    && chmod +x /usr/local/bin/bis_backup.sh /usr/local/bin/notify_admins.sh \
    && touch /var/log/backup.log \
    && echo '0 2 * * * /usr/local/bin/bis_backup.sh >> /var/log/backup.log 2>&1' > /etc/crontabs/root

# Logs in den Container-Stdout mirrorn, damit `docker logs` funktioniert.
# BusyBox-crond:
#   -f  Foreground (sonst startet er sich als Daemon weg und PID 1 endet)
#   -d 8 ausfuehrliches Logging nach stderr (-> docker logs)
#   -c  Crontab-Verzeichnis explizit setzen
CMD ["/bin/sh", "-c", "tail -F /var/log/backup.log & exec crond -f -d 8 -c /etc/crontabs"]
