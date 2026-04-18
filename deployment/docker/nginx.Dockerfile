# Nginx als TLS-Terminierung vor dem BIS-Container (selbstsigniertes Zertifikat beim Build)
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/ssl/bis \
    && openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/bis/bis.key \
        -out /etc/nginx/ssl/bis/bis.crt \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1,DNS:host.docker.internal"

COPY deployment/docker/nginx.docker.conf /etc/nginx/conf.d/default.conf
