# FotoFixer – When & Where

Python + PySide6 desktop app for viewing and editing GPS metadata and dates in
photos (JPG, HEIC, and camera RAW: CR2, CR3, DNG, NEF, ARW, RAF, ORF, RW2,
PEF, SRW) through ExifTool. Runs on Linux Mint, Windows 11, and macOS (Apple
Silicon). Called Photo GPS Editor until 1.9.0; the local checkout folder may
still be named `photo_gps_editor`.

Read `PROJECT_CONTEXT.md` before starting work. It is the source of truth for
status, architecture, and the current UI. Upcoming work, its order, and its
plans live only in `docs/ROADMAP.md`.

## Commands

- Run the app: `.venv/bin/python app.py`
- Run the tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests`
- On Windows (Git Bash): `.venv/Scripts/python` instead of `.venv/bin/python`
- Build locally: see `packaging/README.md` (PyInstaller one-folder build and
  the Windows installer)
- Web version: `python packaging/fetch_web_vendor.py` once, then serve the
  repository root (`python3 -m http.server 8765`) and open
  `http://127.0.0.1:8765/web/`; tests: `node --test web/tests/*.test.mjs`; container:
  `docker/check_container.sh` (needs Docker)
- CI: `.github/workflows/build.yml` tests and builds Linux, Windows, and macOS on
  every push; a `v*` tag attaches the builds to a draft release

## Layout

- `core/`: models, coordinates, ExifTool wrapper, photo loading, picker places
- `services/`: workflow logic; `services/workflow_facade.py` is the GUI's entry point
- `gui/`: main window, widgets, presenters, window mixins, background loading
- `tests/`: unittest suite, including real mouse/keyboard GUI tests
- `web/`: the web version (Docker version): static page, ES modules with no
  build step, ExifTool as WebAssembly in `web/worker/`, vendored files in
  `web/vendor/` (fetched, not in git), Node tests in `web/tests/`
- `docker/`: the container (nginx-unprivileged), compose file, and checks

## Rules

- `core/` and `services/` must not import PySide6, Pillow, or `gui/` (a test
  enforces this). Keep reusable logic there; a web version on a NAS may reuse it.
- Preserve the current architecture unless asked to refactor.
- Prioritize functionality and workflow correctness before visual polish.
- Prefer targeted edits over full-file rewrites; add helpful comments to new
  code, but leave existing comments alone unless they become wrong.
- Every button needs a hover hint (a test enforces this, in `web/` too:
  make buttons with `el()` from `web/app/dom.js`).
- `web/`: no inline styles or scripts (the container's Content-Security-Policy
  forbids them); styles go in `web/app/styles.css`, dynamic styling through
  classes. Only one ExifTool call at a time (the worker's queue); pass bytes,
  not `File` objects, to ExifTool.
- Color theme, wherever it fits (not forced): blue (`#1f6feb`) = what already
  exists (photos with GPS, Has GPS, the GPS badge, the location source, photo
  dots on the map); orange (`#d97706`) = what is new or about to change (the
  selection, Apply, Needs GPS, the map's New Location pin); navy = the Photo
  List (its header and the All view). Grey means disabled, so never use it to
  mark something as active.
- Background results reach the GUI thread through a plain Python queue, not
  queued signals carrying Python objects (that crashed on Windows). Don't open
  dialogs with blocking `exec()`; use `open()` plus a callback.
- When updating `PROJECT_CONTEXT.md`, change only the parts that changed.
- Mockups and trials of UI changes: build them as a Design-type Artifact
  (Artifact quickstart with intent "design", then a canvas of `.dc.html`
  artboards), which opens in the app's right-hand pane. Make it look like the
  real app (colors and sizes from `gui/styles.py`) and interactive where that
  helps. Don't use inline chat widgets or downloadable HTML files for mockups.

## Git

- Solo project using a PR flow: feature branch, push, `gh pr create`, CI, merge
  with GitHub's merge button (merge commit).
- Never commit or push until the user says to; they review changes in VS Code first.
- No AI attribution (Co-Authored-By) lines in commits or PRs.
- New versions only for major UI improvements, significant new features, or
  fixes for bugs that stopped a core feature from working. Branches of
  incremental improvements don't get a version bump; their changes ship with the
  next version. When a branch does qualify, suggest the bump and put it in the
  same PR.
- A release is never its own branch or PR (that wastes a CI run and a review).
  The branch that bumps the version is the release: merge its PR, tag `main`,
  add the notes to CI's draft, publish (`RELEASE_CHECKLIST.md`, Publish).
- Version bumps touch `pyproject.toml`, `APP_VERSION` in `gui/main_window.py`,
  and the `PROJECT_CONTEXT.md` snapshot (`README.md` has no version number).
