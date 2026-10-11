# Photo GPS Editor - Project Context

## Snapshot

Last updated: 2026-10-10
Version: 1.6.0 (not released yet; bumped on branch `date-time-editing`; 1.5.0 was merged in PR #11 and never released on its own). 1.4.1 is the latest release (Linux, Windows, macOS). 1.4: the app's own Add Photos picker, the map (Pick from a Map, street map and satellite imagery), Edit > Settings, and the same pinned ExifTool on every system. 1.4.1: the blue pin GPS badge, the blue = existing / orange = new color theme, the map's Clear button, and no blocking dialogs. 1.5 (unreleased): the Add Photos picker shows folders with the photos and folders can be chosen to add their photos (branch `picker-folders`), plus PR #10, merged earlier: deselect after Apply, the map's Back button and zoom from a photo's preview, backups named `<name>_original.<ext>` (only for photos that had GPS), tighter window spacing, and a clearer window edge on Windows 11. 1.6 (unreleased, branch `date-time-editing`): Date & Time editing (shift the selected photos' dates or set one date; the Photo List groups photos by camera on that tab)
Status: Two-pane layout (Photo List and Photos to Change, with Location and Date & Time tabs; Date & Time shifts or sets photo dates), the app's own photo picker (folder tree; folders and photos, either can be chosen), a pop-out map for picking a location (OpenStreetMap, USGS, or Esri with the user's key), fast thumbnails (shared Linux thumbnail cache, embedded JPEG thumbnails), background loading, failure-tolerant writes, undo/redo that restores the photo list, optional backups, an error log, and CI builds for Linux, Windows, and macOS.

Repository: https://github.com/Petruchio96/photo-gps-editor

## Goal

Desktop application for viewing and editing GPS metadata in photo files.

Key objectives:
- Select one or many photos, or whole folders, with the app's own picker (folder tree on the left, folders and photos on the right)
- Display thumbnails in a grid, including real thumbnails for RAW files
- View and copy GPS metadata
- Apply GPS metadata to the photos selected in the grid, from typed, pasted, photo-sourced, or map-picked coordinates
- Clear GPS metadata from selected photos
- Support JPG and selected RAW formats: CR2, CR3, DNG
- Run on Linux Mint, Windows 11, and macOS (Apple Silicon)

## Architecture

### Core

- `core/models.py`: shared data models such as `PhotoInfo` and `GpsCoordinates`
- `core/coordinates.py`: latitude/longitude validation
- `core/file_types.py`: supported extension checks
- `core/map_tiles.py`: map tile math (Web Mercator, visible tiles, zoom to fit) and the tile sources (OpenStreetMap street map, USGS satellite imagery); no Qt
- `core/places.py`: the picker's places and folder listings (bookmarks from the Linux file manager, network share names, system mounts to skip, hidden files per system); no Qt
- `core/exiftool_wrapper.py`: ExifTool read/write/clear integration through one long-running `-stay_open` process; reads embedded RAW previews (small thumbnails are captured during the bulk GPS read to avoid reopening files); optional `keep_backups`
- `core/process_guard.py`: starts helper processes (ExifTool) so they cannot outlive the app after a crash (shell watchdog on Linux/macOS, job object on Windows)
- `core/photo_loader.py`: converts paths into `PhotoInfo` using single-file and bulk metadata reads (GPS, the date tags, and the camera's Make/Model in the same ExifTool read)
- `core/time_zones.py`: the time zone list (one named zone per distinct offset/daylight-saving pattern, east at the top to west at the bottom), offsets per date via `zoneinfo` (the `tzdata` package supplies the rules on Windows), matching a photo's offset to a zone (US zones first), and the default zone; no Qt
- `core/photo_dates.py`: EXIF date parsing and formatting (the app shows dates as `10/03/2026 9:14:02am`), date taken (`DateTimeOriginal`, else `CreateDate`), and camera names from Make/Model (`Canon EOS R6`, `Apple iPhone 15 Pro`); no Qt

### Services

- Reusable workflow logic outside the PySide frontend
- Handles source resolution, target-file rules, session refresh, overwrite detection, coordinate parsing, and GPS apply orchestration
- `services/workflow_facade.py`: single backend workflow entry point used by the desktop frontend
- `services/photo_metadata_cache.py`: backend-owned in-memory metadata cache for unchanged selected photos
- `services/gps_edit_history.py`: single-step undo/redo memory, including a snapshot of the photo list and selection; one history for GPS and date edits (each edit has a kind), so Undo undoes the last change from either tab
- `services/date_time_service.py`: what a date Shift or Set changes (`DatePlan`), the tag values written, and camera groups for the Photo List; no Qt
- Apply, clear, and undo/redo attempt every file and report failures instead of stopping at the first one
- Intended to remain reusable for possible future desktop, API, web, or container workflows

### Desktop GUI

- `gui/main_window.py`: shell window, menus, status row messages, selection bar state, undo/redo actions
- `gui/background.py`: one background thread for loading GPS data and thumbnails; results go back to the GUI thread through a plain Python queue (a data-free signal only wakes the GUI thread; passing Python objects through queued signals crashed on Windows); waits for the running job before the app exits
- `gui/thumbnail_loader.py`: thumbnail generation, cheapest source first: the shared Linux thumbnail cache, embedded previews (RAW previews; the small EXIF thumbnail near the start of JPEGs), then the whole JPEG; cropped and rotated upright; fallback icons, the GPS badge (a teardrop pin in the app's blue, `#1f6feb`, with a white border and dot, drawn in code by `gui/widgets/icons.py`; the map's New Location pin is the same pin in orange), and icon caching
- `gui/system_thumbnails.py`: reads and writes the freedesktop.org thumbnail cache (`~/.cache/thumbnails`) shared with Nemo/Nautilus; PNG labels are read directly because Qt can't read `Thumb::MTime`
- `gui/error_log.py`: `error-log.txt` in the app's data folder (Windows: `%LOCALAPPDATA%\Photo GPS Editor\Photo GPS Editor`); unexpected errors (with a pop-up), Qt warnings/fatals, hard-crash call stacks (faulthandler), and low-level stderr in windowed builds
- `gui/gc_guard.py`: automatic garbage collection is off; a timer collects on the GUI thread between events
- `gui/window_frame.py`: on Windows 11, a visible slate border (DWM border color) for the map, the picker, and Settings, which Windows otherwise draws too faint to tell apart from the main window; no-op elsewhere
- `gui/widgets/`: browser panel (Photo List pane: header, Show filter, selection bar, grid with click-to-add selection), editor panel (Photos to Change pane with tabs), `photo_picker.py` (the Add Photos picker), `map_view.py` (the map widget: tiles drawn with QPainter, downloaded by QNetworkAccessManager on the GUI thread into a disk cache; pin and photo dots), `map_window.py` (the pop-out map window and photo preview), `settings_dialog.py` (Edit > Settings: backups and the ArcGIS key), loading indicator, thumbnail delegate (shimmer placeholders, SOURCE marker, "No GPS" dimming, faded deselected photos), `icons.py` (line icons drawn in code)
- `gui/presenters/`: UI-facing view-state builders; `inspector_state.py` holds the inspector logic and `date_time_state.py` the Date & Time tab's, with no Qt code
- `gui/widgets/date_time_picker.py`: the compact date and time picker (date box with a calendar, hour/minute/second drop-downs, am/pm label; arrows drawn in code)
- `gui/window_mixins/`: focused behavior for the photo list, inspector, New Location / pick mode, the map (`map_picker.py`), apply/remove workflows, and the Date & Time tab (`date_time_editor.py`)

## Current UI

The photos selected in the Photo List are the photos being edited. Color has
one meaning each, where possible: blue = what exists (the location source,
photos that have GPS: the Has GPS view, its heading, the GPS badge pin on
thumbnails, and the photo dots on the map), orange = what is new or will change
(the selection, the Apply action, the Needs GPS view and heading, and the New
Location pin), navy = Photo List (and the All view). The window title
is the OS title bar (no in-app title bar). Every button has a hover hint (a
test enforces this). No dialog or menu blocks with `exec()` (a test enforces
this): message boxes use `MainWindow.show_message` (modal, `show()` plus a
callback) and the right-click menu uses `popup()`; the blocking `QMessageBox.warning()`-style shortcuts aren't used either (also tested), including in the error log's pop-up.

### Left: Photo List

- Navy `PHOTO LIST` header with `+ Add Photos` (opens the picker, below; adds to the list, skipping photos already in it; GPS data and thumbnails load in the background) and `Clear List` (files are never deleted)
- A list that was empty opens on `Needs GPS` (or `All` if none need GPS); adding to a list keeps the current view
- `Show` filter: `All`, `Needs GPS`, `Has GPS`, with counts; then, after a gap, the `Only Show Selected Photos` toggle (enabled with a selection; shows the selection, fades photos deselected there in place, and turns off when a view button is clicked)
- The selection is the same in every view; photos hidden by the view stay selected and are still acted on
- Selection bar inside the grid: `N selected | Select All | Deselect All | Remove from List`; white with nothing selected, orange with a selection
- Groups photos without GPS first, then photos with GPS, with colored headings; the divider shows only between two groups shown
- Shows a GPS badge (a blue pin) on thumbnails that already have GPS
- Selection: click or Ctrl+click adds/removes a photo; Shift+click adds a range; empty clicks and drags do nothing; Ctrl+A and `Select All` add the photos shown; arrow keys move focus without changing the selection; Space toggles; Delete removes the selected photos from the list
- Right-click: `Copy GPS Coordinates`, `Use This Location`, `Remove from List` (does not change the selection)
- Status row under the grid appears only for action results (with an `Undo` link), errors, and loading progress

### Photo List in Date & Time mode

- The tab shown is filled orange (white text and icon), so the mode is clear
- The Photo List follows the active tab. On `Date & Time`: no GPS badges and no GPS groups; one group per camera (`Canon EOS R6 (42)`, sorted by name, `Unknown Camera` last; navy), photos in date order with photos without a date last, and each tile shows its date under the name
- In the All view each camera heading has a checkbox that selects (or deselects) every photo from that camera
- The Show filter is replaced by a camera filter (`All`, then one button per camera) when the list has more than one camera, and hidden otherwise; `Only Show Selected Photos` is not offered
- Switching tabs keeps the selection; thumbnails of photos with GPS are kept with and without the badge, so switching doesn't read the photos again

### Right: Photos to Change

- Brown `PHOTOS TO CHANGE` header, then (on the Location tab) `N Photos Selected` and `X without GPS · Y with GPS` (one photo: its name and GPS), `Copy` for a single photo with GPS
- `Location` tab:
- `New Location`: `Copy location` with `From a Photo in the Photo List` and `From a Photo on Your Computer`; latitude/longitude fields (decimal, DMS, DDM; a pasted pair auto-splits); `Paste`, `Clear`
- `From a Photo in the Photo List` enters pick mode: the button becomes `Cancel`, a blue banner explains the mode, the grid switches to `Has GPS` (view buttons locked), and everything except `Add Photos`, `Clear List`, and `Cancel` is disabled; afterwards the previous view (and Only Show Selected Photos) returns, and the selection is kept. Disabled, with a hover hint, when no photo in the list has GPS
- `Pick from a Map` opens the map window (below)
- The location source shows on a blue card and as a blue `SOURCE` outline in the grid; editing the fields by hand drops it
- `Apply Location to N Photos` (orange); a note warns when existing GPS will be replaced; the confirmation offers `Skip Photos with GPS`, `Replace`, or `Cancel`
- After Apply or Remove GPS, the photos are deselected except ones that failed (to retry); changed photos can move to a group the view hides and would otherwise be included in the next Apply. Undo brings the old selection back
- `Remove GPS from Selected N Photos` (red outline, counts the selected photos that have GPS), with confirmation
- `Date & Time` tab (modeled on Synology Photos' Edit date and time), laid out as four numbered steps that open one after another: the step to do now is orange, finished ones show a navy ✓, later ones are grey and closed (`After step N`); the pane scrolls to each step as it opens. Deselect All, or applying a change, goes back to step 1
- 1 `Select the photos to change` (`N photos selected` when done; with an empty Photo List a blue `+ Add Photos` button and a hint). 2 `Choose the kind of change`: two cards, `Shift Date and Time` ("The time was off. Correct one photo; the rest move by the same amount.") or `Set a Single Date and Time`; nothing is chosen at first. 3 `Correct the date and time` (`Enter the date and time` for Set). 4 `Check the changes and apply`: hints, the changes list, and the orange button
- Shift (the camera's clock was off; the gaps between photos are right): a blue reference card (name · camera, `Current Date: …`, `The earliest selected`, `‹ 1 of 12 ›` arrows to choose another selected photo by date), `Correct date and time for this photo` (date box with a calendar, then hour : minute : second drop-downs; the hour list reads `9 am`, the box shows `9`, and am/pm sits after the seconds); every selected photo with a date moves by the same amount
- `Or copy the time from a photo taken at the same moment`: `From a Photo in the Photo List` (pick mode like Location's: banner, lock, Esc; photos being changed and photos without a date show `Being Changed` / `No Date`) and `From a Photo on Your Computer` (the picker in one-photo mode; pop-ups for a photo with no date or an unreadable one). The photo shows on a blue source card (✕ to stop using it) and, in the list, as a blue `SOURCE` outline; it is never changed itself, even when selected; editing the date or time by hand drops it
- Set: `New date and time`; every selected photo gets it, including photos with no date
- Time zone drop-down under the date and time (both modes): named zones with their abbreviation on that date (`Mountain Time (Denver) — MDT`, `MST` in winter; zones without one show their offset, `Gulf (Dubai) — UTC+4`), east at the top. Blank and off until a photo is selected. Default, from the selected photos: their zone if they share one, else the most common (a tie goes to the earliest photo's zone); `No time zone` when none has one (then it is offered as an entry); never further east than US Eastern (picking one by hand still works). In red, with a warning hover hint, when the selected photos have more than one zone
- Left alone, each photo keeps its own zone (offset tags untouched). Choosing a zone converts the times shown to it (the same moment) and every photo changed gets it (`OffsetTimeOriginal`, `OffsetTimeDigitized`, `OffsetTime`), with daylight saving worked out per photo; a photo without a zone keeps its clock time and just gets the zone. Typed times are in the chosen zone. Copying the time from a photo compares the real moments when both photos have a zone
- Zones show on the reference card (`Current Date: 10/03/2026 9:14:02am MDT`) and in the changes list (`9:14:02am MDT → 11:14:02am EDT`); the steps scroll on short windows rather than squeezing
- The changes list (step 4) shows every selected photo with its current date and, only where it changes, `→` and the new date in orange; `Source, not changed`; `Skipped` (Shift, no date)
- Hints: the photos come from more than one camera (Shift only), photos without a date are skipped. The orange button reads `Shift N Photos` or `Set Date on N Photos`; no confirmation (Undo covers it)
- What is written: `DateTimeOriginal`, `CreateDate`, `ModifyDate`, and the file's `FileModifyDate`, all set to each photo's new value (the file date as plain clock time), plus the offset tags only when a zone was chosen; sub-seconds are left alone. Date changes never make backup copies; undo writes back the exact tags read before (removing ones that weren't there)
- After a change the photos are deselected (failures stay selected), the status row offers Undo, and the shift/source start over
- The summary above the tabs shows dates on this tab (`1 Photo Selected · IMG_4101.CR3 · Taken 10/03/2026 9:14:02am`; for several, the range and the cameras); `Copy` (GPS) is hidden
- Pop-ups for a browsed photo with no GPS and for an unreadable photo

### Map window

- Opened with `Pick from a Map` in New Location; a separate window that blocks the main window while open (application-modal, shown with `show()` like the picker, not a blocking `exec()`); `Back` steps back through the New Locations set on the map while it is open (clicks, drops, Clear, Use This Location; Ctrl+Z too; emptied when the map opens) and `Clear` empties New Location and removes the pin to start over, both next to Done; `Done` (orange) or Esc closes it, then Apply in the main window writes the location
- The map is another source for New Location, not a separate workflow: a quick click on the map (released within 0.30 s, moving under 2 px; a longer hold or any wiggle pans instead, so a sloppy click-and-hold doesn't move the pin; the click that brings the map window back from another program only activates it: Linux window managers activate the window just before delivering the click, so a click within 0.3 s of the window getting focus, from Qt's app-wide focus-window signal, is ignored) moves the orange pin there and fills the latitude/longitude fields (as typing would, so a location source photo is dropped); dragging the pin fills them when it is dropped. Apply writes them as usual
- The pin follows New Location (typed, pasted, copied from a photo); the map moves to it only when it changed and is out of view; empty fields remove the pin
- Photos in the Photo List with GPS show as blue dots (the app's `#1f6feb`) with a white outline, orange when selected (green blended into the map, and purple was tried and dropped). Hovering a dot shows the file name(s); clicking one shows a small preview (thumbnail, name, `Use This Location`; clicking the thumbnail zooms the map to that photo, at least zoom 15, and keeps the preview beside its dot; and `< 1 of 2 >` arrows beside the count when several photos' dots land on the same spot, within 2 px, so they look like one dot; nearby but separate dots each open their own preview; `Use This Location` uses the photo shown) and does not move the pin
- While another program is active, the map shows the normal arrow and no photo-name hints (a click there only brings the window back); otherwise the pointer is a crosshair (drawn in code at the screen's scale, dark with a white halo; its hot spot is its center), a pointing hand over a photo dot, an open hand over the pin, and a closed hand as soon as the button is pressed (except on a dot); a readout under the map shows the coordinates under the mouse as it moves
- Drag to pan, wheel or `+`/`-` to zoom (whole levels; opening may use an in-between level, drawn from the nearest level's tiles scaled); toolbar: `Street` and one satellite button (`Satellite` = Esri when a key is set in Edit > Settings, `US Satellite` = USGS when not), `Show All Photo Locations`, `Go to Selected Location`, zoom buttons. If Esri's imagery doesn't load (key refused, offline), an amber banner says to check the key in Edit > Settings and offers `Use US Satellite Instead` (the button then reads `US Satellite` until the map is opened again)
- Street map: OpenStreetMap's tile server (identifying User-Agent, cache headers honored, no bulk downloads, credit shown). US Satellite: USGS The National Map orthoimagery (no key; no use constraints; United States only, detailed to zoom 16 and enlarged beyond; a note says so elsewhere). Esri Satellite: Esri World Imagery from the image tile service for API keys (`ibasemaps-api.arcgis.com`; worldwide, street-level detail to zoom 19 and beyond, 256-pixel tiles). The Static Basemap Tiles service has no imagery style (only imagery labels), and this service accepts the key only as `?token=` in the address, not in a header, so the key also appears in the tile cache's records. It needs the user's own API key from a free ArcGIS Location Platform account (an open-source app can't keep its own key secret; a Public application key with only the Static basemap tiles privilege works): the key is entered in Edit > Settings and saved in plain text in the app's settings. Without a key Esri answers 200 with a JSON "Token Required" error and the map shows a note; as of 2026-10-09 it serves imagery for any non-empty token, so a wrong key is not detected (usage shows in the ArcGIS dashboard a day later)
- Tiles are kept in a 200 MB disk cache in the app's cache folder, so places viewed before show offline; a note appears when tiles can't be downloaded, and failed tiles are retried after 15 seconds
- Each time it opens it shows the street map, centered on the photos in the Photo List with GPS, zoomed to fit them with a 12% margin on every side (zoom 15 at most, for one photo); with none, it shows the lower 48 states with the same margin. It does not jump to New Location when opening (`Go to Selected Location` does). The window size and position are remembered
- Off while picking from the Photo List
- QtWebEngine + Leaflet was rejected (about 200 MB more per build) and QtLocation/QML too (a second UI language, untested offscreen); dragging photos onto the map was considered and rejected

### Menus

- File:
- `Add Photos...` (Ctrl+O)
- `Clear List`
- `Exit` with standard OS shortcut

- Edit:
- `Undo` with standard OS shortcut
- `Redo` with standard OS shortcut
- `Select All Photos`
- `Copy GPS Coordinates`
- `Paste Coordinates`
- `Settings...` (Ctrl+, / Cmd+,; Qt's standard Preferences key is the "Settings" media key on Linux; on macOS in the app menu): a modal window (shown with `show()`) with Backups (`Keep Backup Copies of Originals`, saved between sessions: before a photo's first GPS change the app copies it to `<name>_original.<ext>`, e.g. `IMG_0995_original.jpg`, next to it, if it had GPS (adding GPS to a photo without any loses nothing); an existing backup is kept and a backup is never backed up; new backups are added to the Photo List, not selected, and the action's message says so; undo deletes the backups the undone change made (only those) and redo makes them again; ExifTool's own `IMG_0995.jpg_original` naming isn't used, as no photo list shows it) and the Esri Satellite key (instructions and links, Paste, Remove Key); Save applies, Cancel changes nothing

- Help:
- `About` includes the GitHub repository link

## GPS and Date Edit Undo / Redo

- Single-step in-memory undo/redo for GPS and date write actions (one history: Undo undoes the last change from either tab)
- Applies to:
- `Apply Location to N Photos`
- `Remove GPS from Selected N Photos`
- `Shift N Photos` / `Set Date on N Photos` (restores the exact date tags read before; no backups)
- Stores prior GPS state for each successfully changed photo
- Restores prior coordinates or blank/no-GPS state on undo
- Also puts the photo list and selection back as they were at the edit (photos added since disappear, removed ones come back; files that no longer exist are left out)
- Deletes the backup files (`<name>_original.<ext>`) the undone change created; redo creates them again (the edit remembers which backups it made)
- Redo reapplies the undone GPS action
- Undo/redo memory is replaced by the next apply/clear action; adding, removing, or clearing photos does not clear it
- Memory is not written to disk and is cleared on program exit

### Add Photos picker

- The app's own picker replaces the system file dialogs (they mix folders and photos; on Linux choosing both silently does nothing). Used by `+ Add Photos` and, in one-photo mode, by `From a Photo on Your Computer`
- Opened modal but non-blocking (`open()` plus a callback): a blocking `exec()` ran a nested event loop that crashed the Windows build when background results arrived
- Left: folder tree with My Computer (user folders), Bookmarks (Linux file manager bookmarks, without repeats of user folders), Devices/Drives (mounted drives), Network (mounted shares, named like `photo on nas.local`). Folders expand on demand; an arrow shows only for folders with subfolders; hidden folders are left out like each system's file manager. The current folder is highlighted (navy) and the tree opens down to it. Folder icons come from Qt's style, not the system shell
- Top: Back, Forward, Up, and a path box (type or paste a folder; UNC paths like `\\server\share` work on Windows)
- Right: the folder's subfolders (large folder tiles with "5 photos, 2 folders" under the name), then its photos as thumbnails with GPS badges; same click/Shift-click rules and selection bar as the Photo List, for folders and photos alike (`Select All Photos` and Ctrl+A select only the photos; folders are clicked one by one); double-click a folder to open it (the tree follows). Photos already in the Photo List are marked "In Photo List" and can't be selected. Tiles appear at once as placeholders; thumbnails fill in batch by batch, then folder contents, then GPS badges
- The selection stays while moving between folders ("3 photos and 1 folder selected"; Deselect All clears every folder), and an orange dot in the tree marks folders that hold selected photos: the deepest folder showing in the tree for each photo, so a folder gets the dot for photos directly inside it, and for photos in a subfolder only while that subfolder is collapsed out of sight (selected folders don't count; likewise a place such as Home isn't marked for what is inside another place in the tree, such as Pictures). The tree and tiles use a yellow folder drawn in code, the same on every system
- `Add Photos in Subfolders` appears while a folder is selected: off at start, kept until the app closes (not saved). Off, a folder adds only the photos directly inside it; on, also those in every folder inside it (hidden and linked folders skipped). After Add, the main window finds the folders' photos in the background ("Reading folders…", `core/places.py` `photos_in_folders`), then adds them after the photos chosen one by one; duplicates and photos already in the list are skipped as usual
- One-photo mode: a click selects one photo, double-click chooses it, button `Use This Photo's Location`; folders can be opened but not chosen
- Opens in the last folder used (also after cancelling)
- Windows: unmapped network shares don't appear in the tree (File Explorer's Network lists discovered computers); mapped drives appear under Drives. macOS: no Bookmarks section. Neither has a shared thumbnail cache, so only embedded previews speed things up there

## Known Issue

- Qt icon mode loses track of photo positions when a hidden photo's thumbnail changes; the grid is re-laid out after that (see `_relayout_after_hidden_icon_change`).

## Future Ideas

Next up, in order:

1. Check on Windows (and macOS when possible) the changes merged in PR #10, from the latest `main` CI build or the next release: the slate border on the map, picker, and Settings windows; spacing; Back/zoom on the map; backups added to the list and deleted by Undo. Also the Date & Time tab (date writes to CR3/CR2/DNG were only tested with JPEGs)
2. In-app update check: look for a newer version on GitHub Releases (at startup or from Help) and link to the download

Later:

- Windows installer for releases (instead of only the zip): compare options such as an MSI (WiX), Inno Setup, or MSIX, including Start menu shortcut, uninstall, upgrades over an older version, and signing/SmartScreen
- Add drag-and-drop support for loading photos
- Explore a future API/web/container layer (Docker on a Synology NAS) on top of the reusable `services/` backend

## Development Notes

- Use the project virtual environment when running the app or tests
- Run the app with `.venv/bin/python app.py`
- Run tests with `.venv/bin/python -m unittest discover -s tests` (add `QT_QPA_PLATFORM=offscreen` to run without a display)
- GitHub Actions (`.github/workflows/build.yml`) runs the tests and builds Linux, Windows, and macOS apps on every push; pushing a `v*` tag attaches the builds to that release
- On Linux, `app.py` sets `XCURSOR_SIZE`/`XCURSOR_THEME` from the desktop's gsettings (Cinnamon, then GNOME) before Qt starts, unless already set: otherwise Qt sizes the pointer from the font DPI and it looks a little smaller inside the app
- All three builds bundle the same pinned ExifTool (`packaging/fetch_exiftool.py`, currently 13.59); Linux and macOS use ExifTool's Perl distribution with the system Perl
- Pull requests are merged with GitHub's merge button (merge commit)
- GUI uses PySide6
- Metadata reading/writing uses ExifTool
- Thumbnail/icon processing uses Qt and Pillow
- Current coverage includes backend helpers, GUI presenters, workflow services, main-window behavior (real mouse/keyboard events), background loading, and process cleanup


## Completed Refactor Summary

Status: Completed on the `refactor-backend-split-and-performance` branch.

Purpose:
- Separate reusable backend logic from the PySide desktop frontend.
- Improve large photo selection performance, especially metadata loading for the left browser pane.
- Keep behavior stable while simplifying ownership and avoiding unnecessary framework or threading complexity.

Outcome:
- Desktop-specific rendering now lives in `gui/`.
- Shared backend code in `core/` and `services/` has no PySide6, Pillow, or GUI imports.
- The desktop GUI uses `PhotoWorkflowFacade` as its main backend workflow entry point.
- Metadata loading is faster through backend caching and bulk ExifTool reads.
- Manual testing showed large photo batches load at about half the previous time.
- Automated coverage increased to include backend boundary, cache, bulk read, facade, and restore workflow behavior.

Phase outcomes:
1. Moved thumbnail/icon rendering from `core` to `gui/thumbnail_loader.py`, preserving JPEG thumbnails, fallback icons, GPS badges, and icon caching.
2. Added `services/workflow_facade.py` and routed desktop load/source/apply/refresh workflows through `PhotoWorkflowFacade`.
3. Added `services/photo_metadata_cache.py` for backend-owned in-memory metadata caching keyed by path, modified time, and file size.
4. Added bulk GPS metadata reads with `ExifToolWrapper.read_gps_many()` and `PhotoLoader.load_photo_infos()`, while preserving unsupported-file handling and single-file fallback paths.
5. Moved undo/redo GPS restore execution behind `PhotoWorkflowFacade.restore_gps_states_workflow()`.
6. Reduced browser refresh overhead by separating session refresh, thumbnail item creation, and list rendering, and removed a duplicate refresh after clearing target coordinates.
7. Evaluated background loading and intentionally deferred it because caching/bulk reads already improved load time and thumbnail rendering still depends on Qt GUI objects.
8. Prepared backend reuse by documenting desktop-only dependencies as optional extras and adding tests that prevent `core`/`services` from importing PySide6, Pillow, or GUI modules.

Current verification:
- Full test suite passes with `.venv/bin/python -m unittest discover -s tests`.
- Desktop launch flow remains `.venv/bin/python app.py`.
- Future Docker/API work can reuse the shared backend layer but has not been implemented yet.
