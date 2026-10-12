# Release Checklist

Use this checklist against the packaged application (the CI build or the
draft release's files), not the source checkout. Test on copies of photos:
date changes make no backups.

## Before Tagging

- [ ] Version bumped in `pyproject.toml`, `APP_VERSION` in
      `gui/main_window.py`, and the `PROJECT_CONTEXT.md` snapshot.
- [ ] Automated tests pass from source and in CI on Linux, Windows, and macOS.
- [ ] `docs/ROADMAP.md`: finished items removed, the order still right.

## Windows installer

- [ ] `photo-gps-editor-windows-x86_64-setup.exe` installs without an admin
      prompt, to `%LOCALAPPDATA%\Programs\Photo GPS Editor`.
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

- [ ] JPG, CR2, CR3, and DNG photos load with real thumbnails (portrait
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
- [ ] Date writes work on JPG, CR3, CR2, and DNG; the photos open normally
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

## Publish

- [ ] Tag `vX.Y.Z` on `main`; CI attaches the five files to a draft release.
- [ ] Release notes added; title "Version X.Y" (or "Version X.Y.Z").
- [ ] Publish the draft and mark it latest.
