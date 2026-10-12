# Roadmap

The one place for what's next: the order of upcoming work and the plans for
each piece. `PROJECT_CONTEXT.md` describes what exists today; this file
describes what doesn't exist yet. Update it as work lands or decisions change,
and remove finished items.

## Order

1. **Rename the app** (below), one branch. "Photo GPS Editor" no longer fits:
   it edits dates and times too. The update checker (1.8.0) finds each
   download by name, so the rename must also change the names in
   `core/updates.py` (`RELEASE_ASSETS`), `.github/workflows/build.yml`, and
   the installer (`packaging/windows_installer.iss`: install folder,
   shortcuts, setup file name; its fixed `AppId` keeps upgrades working).
   Copies already out there look for the old names, so keep those for one
   release (or teach the checker both) so they can still update themselves.
2. **Docker/web version** (Part 3), 4–5 branches, once the desktop features
   have settled. Part 4 checks that the DS920+ can run it. When it's done,
   the app is feature complete: **version 2.0**.

Not scheduled:

- **Drag-and-drop loading** of photos into the Photo List. The Add Photos
  picker (folders and photos) covers most of the need; the web version
  wouldn't share it.
- **Macs.** No release has been tested on a real Mac yet; test when one is
  available.

## Versions

- 1.7.0 (2026-10-12) is the latest release. 1.8.0 (branch `update-checker`,
  the in-app update checker) releases when it merges.
- Until the Docker/web version is done, versions stay 1.x: **1.8.x** for
  fixes and small improvements, **1.9.0** for the rename.
  The usual rules in `CLAUDE.md` still decide whether a branch gets a bump
  at all.
- A release is never its own branch or PR. The branch that bumps the version
  is the release: merge its PR, tag, notes, publish (`RELEASE_CHECKLIST.md`).
- **2.0** marks the Docker/web version: the desktop app plus the browser
  version on the NAS, feature complete.

---

## Rename the app

"Photo GPS Editor" describes only half of what the app does now that it
edits dates and times as well as GPS. Pick a new name first (the user's
choice), then change it everywhere in one branch, with a version bump.

What the name touches (about 50 places outside the tests):

- **Window titles and menus:** the main window, map, picker, Settings, About.
- **App identity:** `setApplicationName`/`setOrganizationName` in `app.py`.
  These decide where settings and the error log live (registry
  `HKCU\Software\Photo GPS Editor`, `%LOCALAPPDATA%\Photo GPS Editor`,
  `~/.config/Photo GPS Editor`). Changing them would lose the saved
  settings (backups option, Esri key, last folder, map size). So either
  copy the old settings across once at startup, or keep the old internal
  identity and change only what users see.
- **Builds:** `photo_gps_editor.spec` (exe and `.app` names), the AppImage
  (`packaging/build_appimage.sh`, its `.desktop` file), and the download
  file names in `.github/workflows/build.yml`.
- **Project:** `pyproject.toml` name, the README, `PROJECT_CONTEXT.md`,
  `CLAUDE.md`, the map tile User-Agent (OpenStreetMap asks apps to identify
  themselves), and optionally the GitHub repository (GitHub redirects the
  old address).
- **Release notes** for the version that renames it: say what the app used
  to be called, so people find it.

---

## Part 3: Web version in a Docker container

### Approach

The new web version lives in **the same repo**. It adds a `web/` package and a
FastAPI backend that calls the existing `services/workflow_facade.py`
(`PhotoWorkflowFacade`) and `core/`. A plain HTML/JS front end in the browser
is served by the same container.

`core/` and `services/` already have no Qt dependency, and a test enforces
that. This plan relies on that boundary. Most of the hard logic is reused
unchanged:

- ExifTool reading and writing: `core/exiftool_wrapper.py`
- Coordinate parsing: `core/coordinates.py`, `services/coordinate_service.py`
- Apply, clear, and restore: `services/workflow_controller.py`
- Undo/redo: `services/gps_edit_history.py`
- Date & Time: `services/date_time_service.py`, `core/photo_dates.py`
- Folder listing: `core/places.py` (`list_subfolders`, `list_photos`,
  `photos_in_folders`)
- Map math: `core/map_tiles.py`

The desktop app keeps working as it does now. Both share the backend.

### Architecture

```
Browser (PC, Mac, or iPad on LAN)
  └─ static HTML/JS + Leaflet map
       │ JSON over HTTP
  FastAPI (uvicorn, 1 worker)  ── web/
       ├─ PhotoWorkflowFacade (services/)
       ├─ one ExifToolWrapper (persistent Perl process; calls serialized by a lock)
       ├─ thumbnail endpoint (embedded JPEG previews; Pillow only for rotate/resize)
       └─ settings.json + thumbnail cache in /config volume
  Volumes:  /photos  ← Synology shared folder (read-write)
            /config  ← settings, cache, error log
```

### Key design decisions

- **Single user, single worker.** `ExifToolWrapper` keeps one ExifTool process
  running and is not thread-safe. Use one uvicorn worker and an
  `asyncio.Lock`/thread lock around ExifTool calls. Undo/redo history lives in
  server memory. That is fine for one person, and the history is lost when the
  container restarts.
- **Photos root.** The picker can only browse inside `/photos`. Every path the
  browser sends is resolved and checked to stay under that root, so a path
  can't escape it.
- **Thumbnails.** These use the existing `read_small_previews` and
  `read_embedded_previews`. They return the JPEG already inside each
  CR3/DNG/JPG, so the NAS never decodes RAW data. Pillow fixes orientation and
  resizes, and the result is cached on disk in `/config/thumbs` (keyed by path
  + mtime + size). Pillow is allowed in `web/`, but not in `core/` or
  `services/`.
- **Map.** Leaflet runs in the browser. It was rejected for the desktop
  because of QtWebEngine's size, but in a browser it costs nothing. Tiles go
  straight from the browser to OpenStreetMap, USGS, or Esri, reusing the URLs
  from `core/map_tiles.py` `TileSource`. The NAS does no tile work.
- **Long jobs** (load a folder of 1,000 photos, apply to 300) run as
  background jobs with a job id. The browser shows progress by polling or SSE,
  so requests never time out.
- **Settings.** A JSON file in `/config` replaces QSettings (backups option,
  Esri key, last folder).
- **Front end.** Plain HTML/JS modules with no build step, so the Dockerfile
  stays simple. It copies the desktop's layout and colors (`gui/styles.py`):
  - Photo List on the left, Photos to Change on the right
  - Location and Date & Time tabs
  - the blue/orange/navy theme

  Mockups go first, as a Design-type Artifact (per CLAUDE.md).
- **Target devices.** PCs, Macs, and tablets such as iPads, in Chrome, Edge,
  Firefox, and Safari. Phones are out of scope, so there is no phone layout.
  The smallest layout to support is about 1024 px wide (iPad landscape); iPad
  portrait at 768 px is a nice-to-have, with the two panes stacked or
  narrowed. For tablets:
  - Everything works with tap as well as mouse, and nothing needs right-click
    or a keyboard shortcut.
  - Buttons and grid cells are big enough to tap (about 40 px).
  - Selection works by tapping, not by shift/ctrl-click.
  - Leaflet already handles pinch-to-zoom and dragging on the map.
  - Hover hints stay (as `title` tooltips), but iPads don't show hover, so
    button labels must make sense without them.
- **Security.** The app has no login, and it can rewrite every photo. Use it on
  the LAN only, through Synology's reverse proxy (DSM > Login Portal > Reverse
  Proxy) or Tailscale. Never port-forward it to the internet. Basic auth or
  DSM's reverse-proxy auth can be added in a later phase.

### Container

- **New `docker/Dockerfile`:** `python:3.12-slim` + `perl`, plus ExifTool from
  `packaging/fetch_exiftool.py linux`. That is the same pinned 13.59 as the
  desktop builds, checksum-verified.
- Install `requirements-web.txt` (fastapi, uvicorn, Pillow; no PySide6).
- Run as a non-root user, with the UID/GID set by `PUID`/`PGID` to match the
  Synology user that owns the photo share.
- Expected image size: about 150–200 MB.
- **New `docker/compose.yaml`:** for Synology Container Manager > Project:
  - port `8080`
  - volumes `/volume1/photo:/photos` and
    `/volume1/docker/photo-gps-editor:/config`
  - `mem_limit: 512m`
  - `restart: unless-stopped`
- **CI:** a new workflow (`.github/workflows/docker.yml`) builds
  `linux/amd64` (the J4125 is x86-64, so no ARM build is needed) and pushes
  it to GHCR as `ghcr.io/petruchio96/photo-gps-editor` with the tags
  `latest`, `X.Y`, and `X.Y.Z`. It runs when a GitHub release is
  **published** (`on: release: types: [published]`, pre-releases skipped;
  plus `workflow_dispatch` with a tag input), not on the `v*` tag: the tag
  build makes the draft, and publishing the release is the one act that
  ships the desktop files (which the update checker sees) and the image at
  the same time. Steps: checkout at the release tag, `docker/login-action`
  to ghcr.io with `GITHUB_TOKEN` (`permissions: packages: write`),
  `docker/metadata-action` for the tags, `docker/build-push-action` with
  `file: docker/Dockerfile`. The Dockerfile sets
  `PHOTO_GPS_EDITOR_CONTAINER=1`, which `core/updates.py` reads as the
  install kind `CONTAINER`.

### Updates for the container

Containers don't update themselves; this one follows the usual practice:

- **The image carries the versions.** Each published release pushes
  `latest`, `X.Y`, and `X.Y.Z` to GHCR (above). Synology Container Manager
  checks downloaded images against the registry and shows its own "update
  available" badge and notification; the update is then Project > Action >
  Stop, pull the image, Build/Start (or `docker compose pull && docker
  compose up -d` from a shell).
- **The web page says so too.** Once a day the server asks GitHub for the
  latest release with `core/updates.py` (`parse_release`, `is_newer`;
  `urllib`, cached a day) and the page shows the same orange notice as the
  desktop app, with "How to update" opening those steps. The install kind is
  `CONTAINER`, so there is no Update button, only the notice.
- **Automatic pulls, if wanted.** `compose.yaml` ships a commented-out
  Watchtower sidecar, scoped by label so turning it on updates only this
  container and never Vaultwarden or anything else on the NAS:

  ```yaml
  services:
    photo-gps-editor:
      image: ghcr.io/petruchio96/photo-gps-editor:latest
      labels:
        - com.centurylinklabs.watchtower.enable=true
    # Uncomment to pull new versions automatically (checks once a day).
    # watchtower:
    #   image: containrrr/watchtower
    #   volumes:
    #     - /var/run/docker.sock:/var/run/docker.sock
    #   command: --label-enable --cleanup --interval 86400
    #   restart: unless-stopped
  ```

### Phases (one branch/PR each)

1. **Web skeleton, read-only.**
   - `web/app.py` (FastAPI), the folder-browse API, photo-list API,
     thumbnails, and GPS display
   - Dockerfile, compose, and the `docker.yml` workflow that publishes the
     image (above), so Container Manager can pull it from GHCR
   - **Deploy to the NAS at this point** and measure speed and memory on real
     CR3 folders before building more.
2. **Editing.**
   - Apply/Clear GPS from typed or pasted coordinates, or from a source photo
   - the backups option
   - undo/redo
   - a job/progress endpoint
3. **Map.** Leaflet: pick a location, show all photo dots, street/satellite,
   and the Esri key in Settings.
4. **Date & Time tab.** Reuses `services/date_time_service.py` once the
   desktop feature is merged.
5. **Polish.**
   - auth option
   - iPad touch pass (test in Safari on an iPad)
   - error log viewer
   - README section for installing on Synology

### Small prep refactors (only if the web layer needs them)

Some workflow logic may still live in `gui/presenters` or `gui/window_mixins`,
for example selection rules, the Show filter, or the backup-list bookkeeping.
Move whatever the web needs down into `services/`, with tests, rather than
duplicating it. Phase 1 starts with an audit of `gui/presenters/` to find
these.

### Tests

- `tests/test_web_*.py` uses FastAPI's `TestClient` against a temp photo
  folder. It runs in the existing unittest suite and CI.
- Path-escape tests for the `/photos` root.
- The existing "core/services don't import PySide6/Pillow" test stays as is.
- Add a check that `web/` doesn't import PySide6 or `gui/`.

### Synology notes

- **Backups option.** Leave it off on NAS shares and rely on Btrfs snapshots
  (Snapshot Replication) instead. Snapshots cost almost nothing on Btrfs, and
  `_original` copies double the storage and Synology Drive sync traffic.
- **Permissions.** The container's `PUID`/`PGID` must have write access to the
  photo shared folder. Otherwise ExifTool writes fail, though the existing
  failure-tolerant writes would report them.
- **One place at a time.** On Windows the photos live on a local drive that
  Synology Drive syncs to the NAS. If the desktop app and the web version
  change the same photos before a sync finishes, Synology Drive makes
  conflict copies. Edit a folder from one place at a time.

---

## Part 4: Can a DS920+ handle it?

**Short answer: yes, easily. A single-user web app over ExifTool is a light
container. Vaultwarden is lighter still.**

*Assumption: "8mb" means 8 GB of RAM. The DS920+ ships with 4 GB and is
commonly upgraded to 8 GB, the official maximum.*

### Hardware

- CPU: Intel Celeron J4125, 4 cores / 4 threads, 2.0 GHz (2.7 GHz burst), x86-64
- Hardware JPEG/video acceleration is not usable from this app
- RAM: 8 GB (as assumed above)

### Estimated memory (steady state)

| Process | RAM |
|---|---|
| DSM itself + file services | ~1–1.5 GB |
| Vaultwarden (SQLite) | ~20–60 MB |
| Photo GPS Editor: Python + FastAPI + uvicorn | ~60–100 MB |
| Its persistent ExifTool (Perl) process | ~30–60 MB |
| Its thumbnail work (Pillow, one image at a time) | +20–80 MB peak |
| **This app total** | **~150–250 MB, cap at 512 MB** |

That leaves well over 5 GB free with 8 GB installed, most of which DSM uses as
file cache. Even on the stock 4 GB this app would fit.

Two things keep it light:

- Thumbnails come from previews already embedded in the files, so there is no
  RAW decoding.
- Pillow's JPEG draft mode (`img.draft()`) decodes the large preview at a
  quarter or eighth of its size.

### CPU and speed (estimates, to be measured in Phase 1)

- **Reading GPS/dates.** ExifTool on a J4125 should read roughly 20–60
  files/sec in batch mode (`read_gps_many`). A 500-photo folder takes about
  10–25 s on the first load. It is faster than the desktop over SMB because
  the files are on local disk.
- **Thumbnails.** Embedded preview extraction plus resize takes roughly
  20–60 ms per photo. They are cached after the first view, so reopening a
  folder is near-instant.
- **Writing GPS.** ExifTool rewrites each file. A 30 MB CR3 takes about
  0.2–0.5 s on HDDs, so a batch of 300 is a minute or two. It is
  disk-bound, not CPU-bound.
- **Map.** No NAS load: the browser fetches tiles directly.

### Where it could feel slow

- **Cold HDD reads of big folders.** The first load and first thumbnails can
  be slow. Fixes:
  - show progress (Phase 2's job endpoint)
  - cache thumbnails
  - optional: pre-warm the cache for a folder
- **Hibernation.** If DSM's HDD hibernation is on, the first request waits for
  the disks to spin up (~10 s).
- **Other jobs.** Synology Photos indexing or face recognition running at the
  same time will compete for CPU. It's worth pausing or scheduling those if
  they overlap.

### Verdict

Fine to run with Vaultwarden and a few other light containers. Set
`mem_limit: 512m` so it can never squeeze Vaultwarden. Real numbers come from
Phase 1 on the NAS: `docker stats` while loading a large CR3 folder.

---

## Open questions

1. Is the RAM 8 GB, as assumed? (It affects nothing here, but the memory file
   says 4 GB.)
2. Web access: LAN only, or also from outside the house (Tailscale vs. Synology
   reverse proxy with login)?
3. Which Synology shared folder(s) hold the photos (for `/photos` mounts)?
