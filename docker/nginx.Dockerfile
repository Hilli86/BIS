# Nginx als TLS-Terminierung vor dem BIS-Container (selbstsigniertes Zertifikat beim Build)
# Build-Kontext: Projektroot (siehe docker-compose.yml)
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/ssl/bis \
    && openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/bis/bis.key \
        -out /etc/nginx/ssl/bis/bis.crt \
        -subj "/CN=m-0015" \
        -addext "subjectAltName=DNS:m-0015,IP:10.40.140.243,DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1,DNS:host.docker.internal"

COPY docker/nginx.docker.conf /etc/nginx/conf.d/default.conf
