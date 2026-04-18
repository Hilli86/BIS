# BIS � Backup-Service
# Alpine-basierter Container mit dcron, sqlite und 7zip fuer naechtliche Backups.
# Build-Kontext: Projektroot (docker-compose: context: .)
FROM alpine:3.20

RUN apk add --no-cache \
        bash \
        sqlite \
        7zip \
        tzdata \
        dcron \
        findutils \
        coreutils \
    && mkdir -p /usr/local/bin /var/log /backup-plain /backup-encrypted

COPY docker/backup/bis_backup.sh       /usr/local/bin/bis_backup.sh
COPY docker/backup/notify_admins.sh    /usr/local/bin/notify_admins.sh

# Falls die Shell-Skripte unter Windows mit CRLF gespeichert wurden: Line-Endings normalisieren,
# sonst schlaegt /bin/bash im Linux-Container fehl (Shebang wird nicht gefunden).
RUN sed -i 's/\r$//' /usr/local/bin/bis_backup.sh /usr/local/bin/notify_admins.sh \
    && chmod +x /usr/local/bin/bis_backup.sh /usr/local/bin/notify_admins.sh \
    && touch /var/log/backup.log \
    && echo '0 2 * * * /usr/local/bin/bis_backup.sh >> /var/log/backup.log 2>&1' > /etc/crontabs/root

# Logs in den Container-Stdout mirrorn, damit `docker logs` funktioniert
CMD ["/bin/sh", "-c", "tail -F /var/log/backup.log & exec crond -f -l 2"]
