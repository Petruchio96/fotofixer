# Linux Handoff for Claude

**To Claude on Linux Mint:** read this whole file first, then
`PROJECT_CONTEXT.md` and `docs/ROADMAP.md` as `CLAUDE.md` says. It was
written on 2026-10-12 by Claude on the Windows side of the same dual-boot
PC. The user is moving back to Linux to **build the Docker/web version
first**; renaming the app comes later. Your own Linux memory notes are from
before the Windows work (they stop around 1.6.2) and are out of date
wherever they disagree with this file. **Once you've read this, update your
memory notes from it** (release status, the web design in section 5, the
roadmap order), so the next Linux session isn't stale too.

The Linux disk is encrypted and Windows can't read it, so GitHub is the only
bridge. Everything below is in the repo. This file and the new roadmap were
pushed on the branch `linux-handoff`.

---

## 1. First thing: bring the Linux copy up to date

The Linux checkout is probably several merges behind (PRs #16, #17, #18).

```bash
git fetch --prune
git status
git checkout main && git pull
```

If `docs/ROADMAP.md` on `main` still describes a server that mounts the NAS
photo share (FastAPI, a `/photos` volume, ExifTool in the container), the
`linux-handoff` PR hasn't been merged yet. Ask the user to merge it, or work
from that branch (`git checkout linux-handoff`) and branch the web work off
it. Never build from the old NAS-mount text.

If the Linux copy has an old branch with uncommitted or unpushed work,
stop and show the user before switching. Then refresh the environment
(no new dependencies since 1.6, but check):

```bash
.venv/bin/python -m pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
```

About 605 tests should pass. Three in `tests/test_updates.py`
(`RunScriptTests`) run the update script for real and only run on Linux and
macOS; they pass in CI.

---

## 2. Where things stand

- **Latest release: 1.8.0** (published 2026-10-12, "Version 1.8"). It
  added the in-app update checker. 1.7.0 (also 2026-10-12) added the Windows
  installer, Change Time Zone, and background writes with progress.
- `main` is at the merge of PR #18. The only open branch is
  `linux-handoff` (this file and the new roadmap).
- Work done on Windows since you last saw it is all described in
  `PROJECT_CONTEXT.md`. The big pieces:
  - **Windows installer** (`packaging/windows_installer.iss`, Inno Setup;
    the Windows download is now `photo-gps-editor-windows-x86_64-setup.exe`,
    no zip).
  - **Update checker** (`core/updates.py`, `gui/update_checker.py`,
    `gui/window_mixins/update_check.py`, banner and dialog widgets).
    Help > Check for Updates, a once-a-day check after start-up, an orange
    "Version X is available" bar, and one-click updates: installed Windows
    copies run Setup silently; the Linux AppImage and tarball folder and the
    macOS app are swapped by a `/bin/sh` script after the app quits.
  - CI's release job now fails if any release file lacks a SHA-256 digest.

---

## 3. Rules the user set on Windows (also in `CLAUDE.md`)

- **A release is never its own branch or PR.** The branch that bumps the
  version is the release: merge its PR, tag `vX.Y.Z` on main (signed), add
  notes to CI's draft, publish as latest. The user wants this in one go.
- Never commit or push until the user says so. No AI attribution lines
  in commits or PRs. Commits are GPG-signed.
- **A sentence ending in "?" is a question:** answer it, don't do it.
- Mockups go in a Design-type Artifact, never inline widgets.

---

## 4. Test the Linux updater (optional, any time)

The steps are in `RELEASE_CHECKLIST.md` ("Updates") and
`packaging/README.md` ("Updates"). In short: download the 1.8.0 AppImage
from the release into a folder the user can write to (for example
`~/Apps`), make it executable, and run it pretending to be old:

```bash
PHOTO_GPS_EDITOR_PRETEND_VERSION=1.0.0 ./Photo_GPS_Editor-x86_64.AppImage
```

The orange bar offers 1.8.0. **Update** should download, verify, close,
replace the AppImage, and reopen it. Repeat with the tarball's folder. In a
folder that isn't writable the button should read **Download** instead.
What the script did is logged to `update-log.txt` next to `error-log.txt`
(`~/.local/share/Photo GPS Editor/Photo GPS Editor/`). This has never been
tried by hand on Linux; only the CI tests have run the script.

---

## 5. Next: the Docker/web version (read carefully)

The plan is **`docs/ROADMAP.md` Part 3** (rewritten on 2026-10-12). It
replaces the first design, a server that mounted the NAS photo share and
ran ExifTool on it, which the user rejected. In short:

- BentoPDF-style. Someone hosts a static nginx container; friends and family
  open its address and edit photos **on their own computer**. ExifTool runs
  in the visitor's browser as WebAssembly (`@uswriting/exiftool`); the pure
  `core/`/`services/` modules run there through Pyodide. No NAS mount, and
  the server stores nothing.
- Chrome/Edge open a folder and save into the files; Safari, Firefox, and
  iPads get the changed photos as a download. Drag and drop everywhere.
- Optional shared password (nginx basic auth, off by default); each visitor
  enters their own Esri key in their browser.
- `linux/amd64` + `linux/arm64` on GHCR, MIT license, **2.0.0** when done.
  HEIC from the start (and a separate HEIC branch for the desktop app).
- Mockups (current for this design): Design artifact
  https://claude.ai/artifact/7vLiemwRBdyC351wLkS3SD

Where to start:

1. **The app's new name.** The image, the page title, and the address the
   user will share all carry it, so ask the user for the name before the
   first image is published. The desktop rename itself waits (section 6).
2. **Phase 0, the trial.** Before writing it, ask the user for test files:
   R8 CR3s and DNGs from `/mnt/synology_photos`, a JPG, **an iPhone HEIC**,
   and **a CR2** (the R8 shoots only CR3). If CR3 or HEIC writes fail in the
   browser, stop and plan again with the user; the rejected NAS-mount design
   is not the fallback.
3. The roadmap's open questions: the name, and whether the page may ask
   GitHub for updates (it would need `https://api.github.com` in the
   Content-Security-Policy's `connect-src`; the mockups assume yes).

---

## 6. Later: rename the app

`docs/ROADMAP.md` > "Rename the app" lists everything the name touches. The
user picks the new name first. Two things that are easy to miss:

- **The updater finds downloads by file name.** Copies of 1.8.0 look for
  `photo-gps-editor-windows-x86_64-setup.exe`,
  `photo-gps-editor-macos-arm64.zip`, `photo-gps-editor-linux-x86_64.tar.gz`
  and `Photo_GPS_Editor-x86_64.AppImage` (`RELEASE_ASSETS` in
  `core/updates.py`). If the rename changes them, 1.8.0 copies can't update
  themselves. Either keep the old names for one release (upload both), or
  keep them forever. `tests/test_windows_installer.py` ties the names in
  `core/updates.py`, `build.yml`, and the `.iss` together.
- **The update script also knows the names inside the downloads:**
  `FOLDER_NAME`, `BUNDLE_NAME`, `POSIX_EXE_NAME` in `core/updates.py` (the
  tarball's top folder, the `.app`, the exe). An old copy runs its own old
  script against the new download, so if those names change, the Linux
  folder and macOS updates stop before the swap: the old copy is left as it
  was, but it doesn't reopen by itself. (The AppImage swap doesn't depend
  on them.) Plan for it: keep those names for one release, or accept that
  1.8.0 folder and Mac users update by hand once.
- **Settings and the error log** live under the app/organization name
  (`app.py`). Changing it loses saved settings unless they are copied once.
  The Windows installer's fixed `AppId` keeps upgrades working.
- The rename gets a version bump in the same PR (2.1.0 per the roadmap,
  since 2.0.0 is the web version) and is released with it. The web version
  already uses the new name (section 5), so the rename finishes what it
  started.

---

## 7. Linux specifics

- Run the app: `.venv/bin/python app.py`. Tests:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`.
- The user's photos on Linux are on the NAS SMB share at
  `/mnt/synology_photos` (mostly Canon EOS R8 CR3, DNG, JPG).
- Windows-only styling stays behind `sys.platform == "win32"`
  (`WINDOWS_STYLESHEET` in `gui/styles.py`, `gui/window_frame.py`). Don't
  change shared values to fix Windows, and check that Linux still looks
  right.
- `WINDOWS_CLAUDE_HANDOFF.md` is the old note for the move to Windows; it's
  done. Delete it, and this file once its content is in your memory, on
  the first web branch, with the user's OK.
