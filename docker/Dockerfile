# FotoFixer – When & Where, the web version: a static site served by nginx.
# Nothing runs on the server; ExifTool runs as WebAssembly in each visitor's
# browser and photos never leave their computer. See docs/ROADMAP.md, Part 3.
#
# Build (from the repository root):
#   docker build -f docker/Dockerfile -t fotofixer .
# Run:
#   docker compose -f docker/compose.yaml up -d
#
# The first stage downloads the pinned browser-side ExifTool (24 MB of
# WebAssembly, too big for git) with packaging/fetch_web_vendor.py, exactly as
# a developer does locally. The second stage is the image that ships.

FROM python:3.12-alpine AS vendor
WORKDIR /src
COPY packaging/fetch_web_vendor.py packaging/
RUN python packaging/fetch_web_vendor.py --out /vendor \
    # Pre-compressed copies, served by nginx's gzip_static (24 MB -> 7 MB
    # on the wire with no CPU spent per visitor).
    && gzip -9 -k /vendor/zeroperl.wasm /vendor/zeroperl.js /vendor/exiftool.js

FROM nginxinc/nginx-unprivileged:1.27-alpine

LABEL org.opencontainers.image.title="FotoFixer – When & Where" \
      org.opencontainers.image.description="Edit the GPS location and dates of photos in your browser; photos never leave your computer." \
      org.opencontainers.image.source="https://github.com/Petruchio96/fotofixer" \
      org.opencontainers.image.licenses="MIT"

USER root
# htpasswd (apache2-utils) makes the bcrypt hash for the optional password.
RUN apk add --no-cache apache2-utils \
    && rm -f /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/fotofixer.conf
COPY --chmod=755 docker/entrypoint/40-fotofixer-password.sh /docker-entrypoint.d/40-fotofixer-password.sh
COPY web/ /usr/share/nginx/html/
COPY --from=vendor /vendor/ /usr/share/nginx/html/vendor/
USER nginx

EXPOSE 8080

# /healthz answers without a password, so the check works either way.
HEALTHCHECK --interval=60s --timeout=5s --start-period=5s \
    CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
