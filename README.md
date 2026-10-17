This project was written almost entirely by AI, with human direction, testing, and design feedback throughout.

# FotoFixer – When & Where

FotoFixer fixes where and when your photos were taken: the GPS location and the date, time, and time zone stored in photo files. (It was called Photo GPS Editor until version 1.9.0.) It is designed for workflows where you have photos without coordinates and want to copy GPS data from another photo or enter coordinates manually.

The app supports the photos cameras and phones make (JPG, iPhone HEIC, and RAW files from Canon, Nikon, Sony, Fujifilm, Olympus, Panasonic, Pentax, Samsung, and DNG), grouped browsing of photos with and without GPS data, GPS badges on already-tagged photos, overwrite warnings, and single-step undo/redo for GPS edits made during the current session.

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
- Geotag photos from a GPS track (File > Geotag from GPS Track): load the
  GPX file your phone, watch, or logger recorded, and every photo taken
  while it was recording gets the position (and altitude) the track holds
  for that moment, shown on a map before anything is written.
- Fix photo dates on the Date & Time tab: shift every selected photo by the
  same amount (correct one reference photo's date, or copy the time from a
  photo known to be right, such as one from your phone), or give them all
  one date and time. The Photo List groups photos by camera there.
- Undo or redo the most recent GPS or date change while the app is open (undo
  also puts the photo list back the way it was).
- Optionally keep a backup copy of each original file (Edit > Settings > Keep backup copies of originals); Settings also chooses feet or metres for the track's altitudes.

## In the Browser (the Docker Version)

The same app also runs in a browser, served by one small container that
anyone can host: open its address, add photos from your computer, and fix
their location and dates. ExifTool runs as WebAssembly inside the browser,
so **photos never leave your computer**; the server only serves the page
and stores nothing. Chrome and Edge save the changed photos back into the
folder you opened; Safari and Firefox (and an iPad) download them instead.

To host it, see [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md): the image is
`ghcr.io/petruchio96/fotofixer`, and the guide covers a Synology NAS,
Docker with Caddy, Traefik, and the optional shared password. To run it on
your own machine:

```bash
docker run -d --rm -p 127.0.0.1:8080:8080 ghcr.io/petruchio96/fotofixer
```

Then open http://127.0.0.1:8080.

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
[Releases page](https://github.com/Petruchio96/fotofixer/releases/latest).
ExifTool is included, so nothing else needs to be installed.

### Linux

`FotoFixer-x86_64.AppImage` is a single file. Make it executable and run it:

```bash
chmod +x FotoFixer-x86_64.AppImage
./FotoFixer-x86_64.AppImage
```

You can also double-click it in your file manager after making it executable.
If you see a FUSE error, run it with `APPIMAGE_EXTRACT_AND_RUN=1` in front of
the command, or install your distribution's FUSE package.

`fotofixer-linux-x86_64.tar.gz` contains the same app as a folder.
Extract it and run `FotoFixer` inside the folder.

The Linux build uses the system Perl to run ExifTool. Perl is installed by
default on most Linux distributions.

### Windows

Download `fotofixer-windows-x86_64-setup.exe` and run it. It installs
for your user only (no administrator prompt) and adds a Start menu shortcut.
To update, run the newer setup; it replaces the old version in place and
keeps your settings. Uninstall from Settings > Apps.

If Windows SmartScreen warns about an unrecognized app, choose
**More info → Run anyway**. The app is not code-signed yet.

### macOS

Download `fotofixer-macos-arm64.zip` and unzip it to get
**FotoFixer**. This build is for Apple Silicon Macs (M1 and later).

The first time you open it, macOS blocks it because it is not from an
identified developer. Open **System Settings → Privacy & Security** and click
**Open Anyway**, then open the app again.
