# Self-hosting FotoFixer – When & Where

FotoFixer's web version is one small container. People open its address in
a browser and fix the GPS location and dates of photos **on their own
computer**: the container only serves the app's files. ExifTool runs as
WebAssembly inside each visitor's browser, so photos never leave their
computer, nothing is uploaded, and the server stores nothing. There are no
accounts and no database.

This guide covers a Synology NAS (Container Manager), plain Docker with
Caddy, and Traefik. Everything here uses the published image
`ghcr.io/petruchio96/fotofixer` (built for `linux/amd64` and `linux/arm64`;
about 60 MB on disk, a few MB of RAM at rest, no CPU work per visitor).

## What visitors need

- **A desktop browser, or an iPad.** Chrome and Edge save changed photos
  back in place in the folder the visitor opened. Safari and Firefox (and
  an iPad) can't write to the visitor's folders, so changed photos download
  instead: one file, or a zip for several. Phones are too small for the
  layout.
- **HTTPS.** Browsers only allow the folder picker and saving in place on a
  secure page (HTTPS, or `localhost`). Over plain HTTP the app still works,
  but every browser falls back to downloads. That is why the setups below
  all put a reverse proxy with a certificate in front of the container.
- **A first visit downloads about 20 MB** (ExifTool and Python as
  WebAssembly), then the browser caches it. Later visits are quick.
- Map tiles come from OpenStreetMap, the USGS, or Esri (with the visitor's
  own free key, kept in their browser). These are the only third-party
  requests the page makes, and only when the map is opened.

## Quick start (any Docker host)

Save [`docker/compose.yaml`](../docker/compose.yaml) from this repository
(or copy it below), then:

```bash
docker compose up -d
```

The app answers on `http://127.0.0.1:8080` on that host only. Put a reverse
proxy with HTTPS in front to share it (next sections).

The compose file's defaults are already hardened: the container's file
system is read-only, it runs as an unprivileged user with every Linux
capability dropped, memory is capped at 128 MB, and the port is bound to
`127.0.0.1` so only the reverse proxy on the same host can reach it.

### Settings (environment variables)

All optional. Set them in the compose file's `environment:` section or in a
`.env` file next to it.

| Variable | Default | What it does |
|---|---|---|
| `APP_PASSWORD` | unset | Sets one shared password. Visitors get the browser's own sign-in box before the page loads. Without it, anyone who can reach the address can use the app. |
| `APP_USERNAME` | `fotofixer` | The user name that goes with the password. |
| `APP_PASSWORD_FILE` | unset | Read the password from a file instead (a Docker secret, or a bind-mounted file readable by the container's user). |
| `ACCESS_LOG` | `on` | `off` keeps no record of requests at all. |

A password is worth setting when the address is reachable from the
internet: it keeps strangers from using your bandwidth, and that is all it
protects, because a visitor can only ever change files on their own
computer. The password is checked by nginx (HTTP basic auth over HTTPS)
and stored as a bcrypt hash in memory; request rate limiting slows guessing.

`/healthz` answers `ok` without the password, for health checks.

## Synology NAS (Container Manager)

Tested on DSM 7 with Container Manager. The NAS is assumed to have a DDNS
address such as `yourname.synology.me` (Control Panel > External Access >
DDNS) and port 443 forwarded to it on the router; the app then lives at a
subdomain, for example `fotofixer.yourname.synology.me`.

1. **Create the project.** Container Manager > Project > Create. Name it
   `fotofixer`, choose a folder for it (for example `/docker/fotofixer`),
   and for Source pick *Create docker-compose.yml*, then paste the compose
   file. If you want a password, add it under `environment:` (or create a
   `.env` file in the project folder with `APP_PASSWORD=...`). Build and
   start the project. It pulls the image from GitHub, and
   `http://<nas-ip>:8080` isn't reachable from other machines, which is
   intended: the reverse proxy on the NAS is the only way in.
2. **Reverse proxy.** Control Panel > Login Portal > Advanced > Reverse
   Proxy > Create:
   - Source: protocol HTTPS, hostname `fotofixer.yourname.synology.me`,
     port 443. Tick *Enable HSTS*.
   - Destination: protocol HTTP, hostname `localhost`, port 8080.
3. **Certificate.** Control Panel > Security > Certificate. Add a Let's
   Encrypt certificate that covers the hostname (DSM can issue one for a
   subdomain of your DDNS address; a wildcard `*.yourname.synology.me`
   covers every subdomain at once). Then, under Settings on that page,
   assign the certificate to the new reverse-proxy entry.
4. **Open the address** from outside your network once to check the
   padlock and, if set, the password prompt. Then share it.

Nothing else to configure: no shared folder to mount, no user accounts.
Synology Photos and the rest of the NAS are untouched by the app.

### Updating on Synology

Container Manager compares downloaded images with the registry and shows
an update badge on the image. To update: Project > `fotofixer` > Action >
Stop, then Image > `ghcr.io/petruchio96/fotofixer` > Update, then Action >
Build (or Start). The compose file's `latest` tag follows every release;
pin `ghcr.io/petruchio96/fotofixer:1.10` to stay on one minor version.

For automatic updates, uncomment the Watchtower service at the bottom of
the compose file. It checks once a day and only touches containers with
the FotoFixer label.

## Plain Docker with Caddy

Caddy gets the certificate itself. With the app's compose project running
on the same host (port 8080 on `127.0.0.1`), a `Caddyfile` of three lines
is enough:

```text
fotofixer.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Caddy needs ports 80 and 443 reachable from the internet (for the
certificate) and the hostname pointing at the host. Run it from its own
compose file with `network_mode: host`, or publish the two ports and point
`reverse_proxy` at the app container by name on a shared network.

## Traefik

If Traefik already fronts other containers, add FotoFixer to its network
with labels instead of publishing a port. Replace the `ports:` section of
the compose file with:

```yaml
    networks:
      - traefik
    labels:
      - com.centurylinklabs.watchtower.enable=true
      - traefik.enable=true
      - traefik.http.routers.fotofixer.rule=Host(`fotofixer.example.com`)
      - traefik.http.routers.fotofixer.entrypoints=websecure
      - traefik.http.routers.fotofixer.tls.certresolver=letsencrypt
      - traefik.http.services.fotofixer.loadbalancer.server.port=8080

networks:
  traefik:
    external: true
```

Use the entrypoint and certificate resolver names from your Traefik
configuration. The container's own password (`APP_PASSWORD`) works behind
Traefik too, or use a Traefik basic-auth middleware instead.

## Versions and updates

The image is published from each GitHub release of FotoFixer with the tags
`latest`, `X.Y`, and `X.Y.Z` (the same version number as the desktop app
released at the same time). `edge` is the latest build of the `main`
branch, for trying a change before it is released. Each image carries its
version in its OCI labels; the page shows it under Settings. A new version
of the app is a new image: pull it and recreate the container (above). The
app itself never checks for updates or contacts GitHub.

## Security and privacy notes

- The container has nothing to steal or misuse: static files, no photos,
  no keys, no accounts, no server-side code. It has no write access to its
  own file system (`read_only: true`; the password hash goes to a tmpfs).
- Every response carries a strict Content-Security-Policy (scripts and
  styles from the page's own origin only, no inline code, images only from
  the page and the three map-tile hosts), plus `X-Content-Type-Options`,
  `Referrer-Policy`, and `Permissions-Policy` headers.
- No analytics and no cookies (the password uses the browser's basic-auth
  prompt, not a cookie). `ACCESS_LOG=off` keeps nginx from logging
  addresses.
- A visitor's Esri key and settings live in their own browser's local
  storage and are never sent to the server.
- Keep the port bound to `127.0.0.1` (the compose default) so the only way
  in is through the reverse proxy and its HTTPS.

## Building the image yourself

From a checkout of the repository:

```bash
docker build -f docker/Dockerfile -t ghcr.io/petruchio96/fotofixer:latest .
```

The build downloads the pinned ExifTool WebAssembly and Pyodide (checksum
verified) and zips the app's Python modules; the result is the same image
CI publishes. `docker/check_container.sh` runs the checks CI runs on it.

## Troubleshooting

- **"Open a Folder" is missing and everything downloads.** The page isn't
  on HTTPS (or the browser is Safari or Firefox, which download by design).
  Check the padlock in the address bar.
- **Browser asks for a user name and password.** `APP_PASSWORD` is set; the
  user name is `APP_USERNAME` (default `fotofixer`). Check the container's
  log: it says at start whether the password is on.
- **The container stops at once with "cannot read APP_PASSWORD_FILE".**
  The file must be readable by the container's user (uid 101): `chmod 644`
  it, or use `APP_PASSWORD`.
- **HEIC photos show a placeholder instead of a thumbnail.** Only Safari
  decodes HEIC; other browsers show the photo icon (with the GPS badge).
  Editing still works.
- **The map's Satellite button shows US imagery only.** Worldwide imagery
  needs the visitor's own free Esri key, entered under Settings.
- **Health check.** `curl http://127.0.0.1:8080/healthz` on the host
  prints `ok`.
