# Release Checklist

Use this checklist against the packaged application (the CI build or the
draft release's files), not the source checkout. Test on copies of photos:
date changes make no backups.

A release rides on the pull request of the branch that bumps the version;
it never gets a branch or PR of its own. Test the branch's CI build before
the merge, then tag and publish right after it.

## Before Tagging

- [ ] Version bumped in `pyproject.toml`, `APP_VERSION` in
      `gui/main_window.py`, and the `PROJECT_CONTEXT.md` snapshot.
- [ ] Automated tests pass from source and in CI on Linux, Windows, and macOS.
- [ ] `docs/ROADMAP.md`: finished items removed, the order still right.

## Windows installer

- [ ] `fotofixer-windows-x86_64-setup.exe` installs without an admin
      prompt, to `%LOCALAPPDATA%\Programs\FotoFixer`.
- [ ] The Start menu shortcut opens the app; Settings > Apps lists it with
      the new version.
- [ ] Installing over the previous version keeps Edit > Settings and leaves
      no stale files (`_internal` holds only the new build).
- [ ] Uninstalling removes the folder and the shortcut and keeps the settings
      and the error log.

## Launch

- [ ] The app opens from the packaged build on a machine without Python or
      ExifTool installed.
- [ ] The window and taskbar/dock icon appear.
- [ ] Help > About shows the new version and the project link.
- [ ] No dependency or ExifTool error at startup.

## Add Photos Picker

- [ ] Add Photos opens the app's own picker in the last folder used.
- [ ] The folder tree shows user folders, drives, and network shares
      (Windows: mapped NAS drives; Linux: the mounted NAS share).
- [ ] Choosing photos adds them; choosing a folder adds its photos;
      "Add Photos in Subfolders" adds the subfolders' photos too.
- [ ] Select All Photos selects only photos; photos already in the Photo
      List show "In Photo List" and can't be chosen.

## Photo List

- [ ] JPG, HEIC (an iPhone photo), CR2, CR3, and DNG photos load with real
      thumbnails, and the other RAW formats are listed by the picker (portrait
      photos the right way up).
- [ ] Photos with GPS show the blue pin badge; the Show filter (All, Needs
      GPS, Has GPS) and Only Show Selected Photos work.
- [ ] Edit > Copy GPS Coordinates and the Copy location button copy a
      photo's coordinates.

## Location Tab

- [ ] Typed and pasted coordinates (decimal, DMS, DDM) validate.
- [ ] Apply writes the location to the selected photos; the overwrite
      warning appears for photos that already have GPS; photos are
      deselected after Apply.
- [ ] A selected photo's location, or another photo file's, can be the
      source. Apply leaves the source photo out, and is disabled when the
      source is the only photo selected.
- [ ] Clear GPS removes coordinates.
- [ ] Pick from a Map: Street and satellite imagery load; clicking or
      dragging the pin fills New Location; Back, Clear, Show All Photo
      Locations, and zoom from a photo preview work.
- [ ] Windows: the map, picker, and Settings windows have a visible slate
      border, clearly separate from the main window.

## Date & Time Tab

- [ ] The four steps open in order and the pane scrolls to each.
- [ ] Shift: correcting the reference photo moves every selected photo by
      the same amount; copying the time from a Photo List photo or the
      computer works.
- [ ] Set One Date and Time gives every selected photo that date.
- [ ] Change Time Zone: off, the moment stays (11:16 MDT → 12:16 CDT); with
      Keep the clock time on (after its pop-up), only the zone changes
      (11:16 MDT → 11:16 CDT). Step 2 folds up to the choice and opens again
      when clicked.
- [ ] GPS and date writes work on JPG, HEIC, CR3, CR2, and DNG; the photos open normally
      in another program afterwards and show the new date.
- [ ] Time zones: named zones with abbreviations; the default comes from the
      selected photos; changing the zone converts the time; the zone is red
      when the selected photos have mixed zones.
- [ ] The camera filter appears when the photos come from more than one
      camera.

## Undo, Backups, Settings

- [ ] Undo and Redo work for GPS and date changes, as one history across
      both tabs, and put the Photo List back the way it was.
- [ ] With Keep Backup Copies of Originals on, changing GPS on a photo that
      already had GPS makes `<name>_original.<ext>`, adds it to the Photo
      List, and Undo deletes it.
- [ ] Edit > Settings (backups, Esri key) and the last folder are remembered
      after reopening the app.
- [ ] After reopening the app, the changes are still in the files.

## Updates

Run the branch's CI build with the environment variable
`FOTOFIXER_PRETEND_VERSION=1.0.0`, so it thinks it is old and offers
the latest *published* release.

- [ ] About 5 s after the window opens, the orange bar offers the latest
      release; What's New shows its notes; Help > Check for Updates says the
      same, and says "up to date" without the variable.
- [ ] Windows, installed with Setup: Update downloads with progress, Setup
      runs silently, the app closes and reopens as that version with the
      settings kept (`update-log.txt` next to the error log).
- [ ] Linux AppImage and the tarball's folder: Update replaces the file or
      folder and reopens the app; in a folder that isn't writable the
      button reads Download and opens the release page.
- [ ] macOS: as Linux (when a Mac is available); run straight from
      Downloads, the button reads Download.
- [ ] Skip This Version hides the bar until a newer version; ✕ hides it for
      this session; the Settings checkbox turns the start-up check off.

## Web Version (the Container)

Run the branch's build locally (`docker/check_container.sh`, or
`docker compose -f docker/compose.yaml up -d` with a locally built image)
and open it on `http://127.0.0.1:8080`; for the folder picker and saving
in place, Chrome or Edge on that address. The version check and the
publishing workflow are tested by `tests/test_docker_publish.py`.

- [ ] Settings shows the new version (`web/app/version.js` matches
      `pyproject.toml`).
- [ ] Chrome or Edge: Open a Folder, GPS and date changes save in place,
      backups and Undo work. Firefox: changed photos download (one file, or
      a zip for several).
- [ ] Safari on a Mac or an iPad (download mode): the page loads (Pyodide
      and ExifTool), HEIC thumbnails show, photos can be added and changed,
      and the download works.
- [ ] The container checks pass (`docker/check_container.sh`): headers, the
      WebAssembly type, the password on and off.

## Publish

- [ ] Merge the branch's PR (the one with the version bump).
- [ ] Tag `vX.Y.Z` on `main`; CI attaches the four files to a draft release
      and checks that each has a SHA-256 digest (the update check verifies
      downloads against them).
- [ ] Release notes added; title "Version X.Y" (or "Version X.Y.Z").
- [ ] Publish the draft and mark it latest. Publishing is what ships it:
      the in-app update check only sees published releases, and the
      "Publish container image" workflow builds the image from the
      published release.
- [ ] The image: the workflow run is green and
      `ghcr.io/petruchio96/fotofixer` has the tags `X.Y.Z`, `X.Y`, and
      `latest`. The first time only: open the package on GitHub (Packages
      on the profile page) and set its visibility to public, and link it
      to the repository, so `docker pull` works without a login.
- [ ] Pull the new image on the NAS (`docs/SELF_HOSTING.md`, "Updating on
      Synology") and open the shared address once.
