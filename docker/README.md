# docker/

The web version of FotoFixer – When & Where as a container: nginx serving
`web/` as static files. Nothing runs on the server; ExifTool runs as
WebAssembly in each visitor's browser and photos never leave their
computer.

- `Dockerfile`: downloads the browser-side ExifTool
  (`packaging/fetch_web_vendor.py`), then the `nginx-unprivileged` image with
  the app, the security headers, and the optional password.
- `nginx.conf`: the server block (headers, gzip, the `/healthz` check).
- `entrypoint/40-fotofixer-password.sh`: turns the password on when
  `APP_PASSWORD` (or `APP_PASSWORD_FILE`) is set, and the access log off
  when `ACCESS_LOG=off`.
- `compose.yaml`: the published image with the hardened defaults (read-only,
  no capabilities, 128 MB, port on 127.0.0.1 only) and the optional
  Watchtower sidecar.
- `check_container.sh`: builds and tests the container like CI does.

The image is `ghcr.io/petruchio96/fotofixer` (`latest`, `X.Y`, `X.Y.Z`,
and `edge` from `main`), built for `linux/amd64` and `linux/arm64` by
`.github/workflows/docker.yml` whenever a GitHub release is published. Run
it from the repository root:

```bash
docker compose -f docker/compose.yaml up -d
```

To run a build of your own checkout instead, build it under the same name
first; `up -d` then uses the local image and pulls nothing:

```bash
docker build -f docker/Dockerfile -t ghcr.io/petruchio96/fotofixer:latest .
```

Then open http://127.0.0.1:8080. To share it, put a reverse proxy with
HTTPS in front (the folder picker and saving in place need HTTPS or
localhost); `docs/SELF_HOSTING.md` covers Synology, Caddy, and Traefik.
