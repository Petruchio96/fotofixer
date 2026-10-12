# Roadmap

The one place for what's next: the order of upcoming work and the plans for
each piece. `PROJECT_CONTEXT.md` describes what exists today; this file
describes what doesn't exist yet. Update it as work lands or decisions change,
and remove finished items.

## Order

1. **Improvements and fixes** (now, below). Small branches, released as
   1.6.x or 1.7.x.
2. **Rename the app** (below), one branch. "Photo GPS Editor" no longer fits:
   it edits dates and times too. Do it before the update checker, which
   builds the download file names into the app. The Windows installer
   (`packaging/windows_installer.iss`, shipped in 1.7.0) also carries the
   name (install folder, shortcuts, setup file name); its fixed `AppId`
   keeps upgrades working across the rename.
3. **In-app update checker** (Part 2), one branch. The installer it needs
   for one-click Windows updates exists.
4. **Docker/web version** (Part 3), 4–5 branches, once the desktop features
   have settled. Part 4 checks that the DS920+ can run it. When it's done,
   the app is feature complete: **version 2.0**.

Not scheduled:

- **Drag-and-drop loading** of photos into the Photo List. The Add Photos
  picker (folders and photos) covers most of the need; the web version
  wouldn't share it.
- **Macs.** No release has been tested on a real Mac yet; test when one is
  available.

## Versions

- 1.6.1 (2026-10-11) is the latest release. 1.6.2 (merged, unreleased)
  is skipped as a release: the next release is 1.7.0.
- Until the Docker/web version is done, versions stay 1.x: **1.6.x** for
  fixes and small improvements, **1.7.x** when a branch adds something
  bigger (for example the rename or the update checker).
  The usual rules in `CLAUDE.md` still decide whether a branch gets a bump
  at all.
- **2.0** marks the Docker/web version: the desktop app plus the browser
  version on the NAS, feature complete.

---

## Now: improvements and fixes

1.6.1 is released. Merged since, not released: **Change Time Zone** (PR #15,
bumped to 1.6.2) and the first **Windows polish** fixes (PR #16). 1.6.2 will
not be released on its own: branch `windows-polish-2` (Windows polish part 2,
the safer zone fallback, the CI release download fix, the Windows installer,
version **1.7.0**)
releases everything since 1.6.1 once it is merged and tagged (see
`RELEASE_CHECKLIST.md`). Nothing else is queued before the rename.

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

## Part 2: In-app update checker

**Goal:** the app tells you when a newer release is on GitHub.

- **Windows installed copy:** one click downloads the new `Setup.exe`, checks
  it, installs it silently, and reopens the app.
- **Everything else** (macOS, Linux, the Windows zip, running from source):
  the app shows what's new and opens the download page.

This is to-do item #3. One-click updating depends on the Windows installer,
which exists (`packaging/windows_installer.iss`): it installs per user to
`%LOCALAPPDATA%\Programs\Photo GPS Editor`, puts `unins000.exe` next to the
exe, is named `photo-gps-editor-windows-x86_64-setup.exe` on every release,
and after a silent install reopens the app (a `[Run]` entry with
`skipifnotsilent`; `RestartApplications` is off, so nothing starts it twice).

### How the check works

- It calls GitHub's public API:
  `GET https://api.github.com/repos/Petruchio96/photo-gps-editor/releases/latest`
  - The repo is public, so no token is needed. Unauthenticated calls are
    limited to 60 an hour per IP, which is far more than needed.
  - This endpoint skips **drafts and pre-releases**. CI's draft releases stay
    invisible until you press Publish, so publishing a release is what
    "ships" it to users. Add that to `RELEASE_CHECKLIST.md`.
  - Today's response contains `tag_name` (`v1.4.1`), `name`, `body` (the
    release notes, in Markdown), `html_url`, and `assets[]`. Each asset has a
    `name`, `browser_download_url`, `size`, and `digest` (`sha256:…`).
- It compares `tag_name` with `APP_VERSION` (`gui/main_window.py`). The comparison is numeric, (1, 10, 0) > (1, 9, 2),
  never a text comparison.
- **When it checks:**
  - Automatically, about 5 s after startup, so it doesn't compete with
    loading photos. At most **once a day**: a QSettings timestamp records the
    last check.
  - On demand from the new **Help > Check for Updates…**, which always checks.
  - Turning off the automatic check: an **"Check for updates when the app
    starts"** checkbox in Edit > Settings, new "Updates" group, on by
    default. The menu item always works.
- **Network:** `QNetworkAccessManager` on the GUI thread, the same pattern as
  the map's `NetworkTileFetcher` (`gui/widgets/map_view.py`). There is no
  background thread, so the Windows queued-signal crash can't happen.
  - Send a `User-Agent` (GitHub requires one) and
    `Accept: application/vnd.github+json`.
  - Use a 10 s transfer timeout.
- **Failures:**
  - The automatic check stays silent on any failure (offline, rate limited,
    or 404 because there are no releases yet). It writes one line to the
    error log.
  - A manual check says "Couldn't reach GitHub. Check your connection and
    try again."

### What you see

- **Update found by the automatic check:** an orange notice bar at the top of
  the main window. Orange because something new is available. It doesn't
  block anything:
  > **Version 1.7.0 is available** (you have 1.6.1) · `What's New` ·
  > `Update` (or `Download` off Windows) · `Skip This Version` · `✕`

  - `Skip This Version` stores the tag. The bar stays hidden until an even
    newer version appears.
  - `✕` hides it until the next day's check.
- **Help > Check for Updates…:** a small window, opened with `open()` rather
  than `exec()`. It shows either:
  - "You're up to date (1.6.1)", or
  - the new version, its release notes (`QLabel` with Markdown, scrollable),
    and the same buttons.
- **New buttons get hover hints**, which the existing test enforces. Example:
  "Download version 1.7.0, install it, and restart the app."

### What "Update" does on each system

| Running from | How detected | Button | Action |
|---|---|---|---|
| Windows, installed | frozen + `unins000.exe` next to the exe | **Update** | download setup → verify → run silently → app quits → setup reopens it |
| Windows, zip | frozen, no `unins000.exe` | **Download** | open the release page. The window also suggests switching to the installer, which updates itself |
| macOS `.app` | frozen + darwin | **Download** | open the release page. Replacing an unsigned `.app` in place causes quarantine problems, so it isn't worth it |
| Linux AppImage / tarball | frozen + linux | **Download** | open the release page |
| Source (`python app.py`) | not frozen | — | notice only ("pull the latest code") |

### Windows one-click update in detail

1. **Download.**
   - Choose the asset named exactly
     `photo-gps-editor-windows-x86_64-setup.exe`.
   - Only accept a download URL that is `https://` on `github.com` or
     `objects.githubusercontent.com`, including redirects. GitHub redirects
     downloads to its CDN.
   - Download with `QNetworkAccessManager` into
     `%TEMP%\Photo GPS Editor update\`, showing progress in the window, with
     a Cancel button.
2. **Verify.**
   - The file's size must match the asset's `size`.
   - Its SHA-256 must match the asset's `digest`.
   - If either check fails, delete the file and show "The download was
     damaged. Try again."
   - This also stands in for code signing. The app downloads the file itself,
     so it gets no Mark-of-the-Web and SmartScreen doesn't block the silent
     install.
3. **Install.**
   - Start
     `setup.exe /SILENT /SP- /NOCANCEL /CLOSEAPPLICATIONS`
     as a detached process.
   - Then quit the app normally: close the ExifTool process and save
     settings.
   - Setup waits for the app to close, upgrades in place (the same `AppId`),
     and relaunches it through the `skipifnotsilent` `[Run]` entry.
4. **Unsaved work.** Before step 3, if a write is still running, the Update
   button waits or is disabled ("Finish the current change first"). The undo
   history is lost on restart, and the window says so.

### Code layout (follows the core/services/gui rules)

- **New `core/updates.py`:** pure Python, no Qt, so it is unit-testable and
  the web version can reuse it. It contains:
  - `parse_version("v1.6.1") -> (1, 6, 1)` and `is_newer(latest, current)`
  - `parse_release(json_dict) -> ReleaseInfo(version, tag, title, notes,
    page_url, assets)`
  - `pick_asset(release, platform, install_kind) -> Asset | None`
  - `is_trusted_download_url(url)`
  - `verify_file(path, size, digest)`
  - `INSTALLER_ASSET_NAME`, which CI and the `.iss` file also use
- **New `gui/update_checker.py`:**
  - `UpdateChecker(QObject)`: fetch, the once-a-day rule, skip-version, and
    the result callback
  - `UpdateDownloader`: download, progress, verify, launch the installer
  - `install_kind()`: installed / portable / mac / linux / source
  - A fetcher can be injected, like `TileFetcher`, so tests never use the
    network.
- **New `gui/widgets/update_dialog.py`:** the notice bar and the Check for
  Updates window.
- **`gui/main_window.py`:**
  - the Help menu item
  - start the delayed automatic check
  - QSettings keys: `updates/check_on_start`, `updates/last_check`,
    `updates/skipped_version`
- **`gui/widgets/settings_dialog.py`:** the "Updates" group with its
  checkbox.
- **Testing hook:** the environment variable
  `PHOTO_GPS_EDITOR_PRETEND_VERSION=1.0.0` overrides the version the checker
  compares against. You can then test against the real latest release
  without making a fake one.

### Tests

- `tests/test_updates.py` (`core`):
  - version parsing and ordering (1.10 > 1.9, a missing patch number, a
    leading `v`, bad tags ignored)
  - parsing a saved copy of today's real API response
  - asset choice for each platform and install kind
  - the URL allowlist
  - digest checks
- GUI tests with a fake fetcher:
  - the bar appears for a newer version and stays hidden for the same or an
    older one
  - Skip, and the once-a-day rule
  - a manual check while offline shows the message
  - the Update vs Download label for each install kind
  - hover hints are present
- The silent-install step is checked by hand in the Windows VM (below).

### Verification (end to end)

1. Release a version with the checker (the installer shipped in 1.7.0) and
   install it on Windows with Setup.
2. Run it with `PHOTO_GPS_EDITOR_PRETEND_VERSION=1.0.0`. The bar should offer
   1.7.0. Click Update: it downloads, verifies, closes, and reopens, with
   settings kept.
3. For the real test, publish the next version. The VM copy updates itself
   with one click.
4. On Linux, run the AppImage the same way: the bar offers Download, which
   opens the release page.

### Rollout notes

- **Old copies can't update themselves.** Copies older than the first version
  with the checker can't notice anything. Install that version by hand once,
  with Setup on Windows. After that, updates are one click.
- **Keep asset names stable.** The checker finds downloads by name. Add a
  test, or a comment in `build.yml`, that ties the names to `core/updates.py`.
- **Version bump.** This is a significant feature, so suggest a version bump
  in this PR.

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
- **CI:** a new job builds `linux/amd64` (the J4125 is x86-64, so no ARM build
  is needed). On `v*` tags it pushes to GHCR
  (`ghcr.io/petruchio96/photo-gps-editor`). Container Manager pulls it from
  there.

### Updates for the container

The desktop updater doesn't apply here. You update the container by pulling
the new image: Container Manager > Project > stop, pull, start. The web page
can reuse `core/updates.py` to show a "version X is available" notice and link
to these steps.

### Phases (one branch/PR each)

1. **Web skeleton, read-only.**
   - `web/app.py` (FastAPI), the folder-browse API, photo-list API,
     thumbnails, and GPS display
   - Dockerfile and compose
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
   - CI image publish
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
