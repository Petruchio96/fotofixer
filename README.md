This project was written almost entirely by AI, with human direction, testing, and design feedback throughout.

# Photo GPS Editor

Photo GPS Editor is a desktop application for viewing, copying, applying, and clearing GPS metadata in photo files, and for fixing their dates and times. It is designed for workflows where you have photos without coordinates and want to copy GPS data from another photo or enter coordinates manually.

The app supports JPG thumbnails, selected RAW formats, grouped browsing of photos with and without GPS data, GPS badges on already-tagged photos, overwrite warnings, and single-step undo/redo for GPS edits made during the current session.

## What It Does

- Add photos to the Photo List, grouped by whether they have GPS.
- Show only the photos that need GPS, only those that have it, or only the
  photos you have selected.
- Select the photos to change; the Photos to Change pane shows how many are
  selected and how many already have GPS.
- Set a new location by typing or pasting coordinates (decimal, DMS, or DDM),
  using a selected photo's location, reading it from any photo file, or
  clicking a map (street map, US satellite imagery, or Esri's worldwide
  satellite imagery with your own free ArcGIS key). The map also shows the
  photos in the list that have GPS.
- Apply the new location to the selected photos, with a warning before
  replacing existing GPS.
- Remove GPS coordinates from selected photos.
- Fix photo dates on the Date & Time tab: shift every selected photo by the
  same amount (correct one reference photo's date, or copy the time from a
  photo known to be right, such as one from your phone), or give them all
  one date and time. The Photo List groups photos by camera there.
- Undo or redo the most recent GPS or date change while the app is open (undo
  also puts the photo list back the way it was).
- Optionally keep a backup copy of each original file (Edit > Settings > Keep Backup Copies of Originals).

## Local Development Instructions

Requirements:

- Python 3
- ExifTool
- Project dependencies from `requirements.txt`

Set up and run:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

## Download and Use

Download the latest version from the
[Releases page](https://github.com/Petruchio96/photo-gps-editor/releases/latest).
ExifTool is included, so nothing else needs to be installed.

### Linux

`Photo_GPS_Editor-x86_64.AppImage` is a single file. Make it executable and run it:

```bash
chmod +x Photo_GPS_Editor-x86_64.AppImage
./Photo_GPS_Editor-x86_64.AppImage
```

You can also double-click it in your file manager after making it executable.
If you see a FUSE error, run it with `APPIMAGE_EXTRACT_AND_RUN=1` in front of
the command, or install your distribution's FUSE package.

`photo-gps-editor-linux-x86_64.tar.gz` contains the same app as a folder.
Extract it and run `Photo GPS Editor` inside the folder.

The Linux build uses the system Perl to run ExifTool. Perl is installed by
default on most Linux distributions.

### Windows

Download `photo-gps-editor-windows-x86_64.zip`, unzip it, and run
`Photo GPS Editor.exe` inside the folder. Keep the files together: the app
needs the `_internal` folder next to it.

If Windows SmartScreen warns about an unrecognized app, choose
**More info → Run anyway**. The app is not code-signed yet.

### macOS

Download `photo-gps-editor-macos-arm64.zip` and unzip it to get
**Photo GPS Editor**. This build is for Apple Silicon Macs (M1 and later).

The first time you open it, macOS blocks it because it is not from an
identified developer. Open **System Settings → Privacy & Security** and click
**Open Anyway**, then open the app again.
