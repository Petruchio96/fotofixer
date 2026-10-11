# Windows Build Steps

GitHub Actions builds the Windows app on every push (see
`packaging/README.md`), so these steps are only needed to build and debug on
a Windows machine by hand. They start after booting into Windows.

## 1. Install Required Tools

Install these first if they are not already installed:

- Python 3.12 from <https://www.python.org/downloads/>
- Git for Windows from <https://git-scm.com/download/win>

During Python installation, enable:

```text
Add python.exe to PATH
```

After installing, open PowerShell and verify:

```powershell
py -3.12 --version
git --version
```

## 2. Get The Project

Choose a folder where you keep programming projects. This example uses:

```powershell
mkdir "$HOME\Documents\Programming"
cd "$HOME\Documents\Programming"
```

Clone the repository:

```powershell
git clone https://github.com/Petruchio96/photo-gps-editor.git
cd photo-gps-editor
```

If the repository already exists on Windows, use this instead:

```powershell
cd "$HOME\Documents\Programming\photo-gps-editor"
git fetch
git checkout main
git pull
```

## 3. Create The Python Environment

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install PyInstaller
```

## 4. Add Windows ExifTool

The quickest way is the download script, which fetches a pinned ExifTool
version and verifies its checksum:

```powershell
.\.venv\Scripts\python packaging\fetch_exiftool.py windows
```

To do it by hand instead:

Download the Windows ExifTool zip (64-bit) from:

```text
https://exiftool.org/
```

Current Windows ExifTool zips contain two things, and both are needed:

```text
exiftool(-k).exe
exiftool_files\
```

`exiftool_files` holds the Perl runtime that the executable depends on.
The executable will not run without it.

Create the tools folder if needed:

```powershell
mkdir tools\windows -Force
```

Extract the zip, then copy both items into `tools\windows` and rename the
executable to `exiftool.exe`:

```text
tools\windows\exiftool.exe
tools\windows\exiftool_files\
```

These files are listed in `.gitignore`, so they will not be committed.

Verify it runs:

```powershell
.\tools\windows\exiftool.exe -ver
```

## 5. Run Tests

From the repository root:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

The expected result is:

```text
OK
```

## 6. Build The Windows App

From the repository root:

```powershell
.\.venv\Scripts\python -m PyInstaller photo_gps_editor.spec --noconfirm
```

The expected executable is:

```text
dist\Photo GPS Editor\Photo GPS Editor.exe
```

## 7. Launch The Built App

From the repository root:

```powershell
& "dist\Photo GPS Editor\Photo GPS Editor.exe"
```

If Windows SmartScreen warns about the app, choose the option to run anyway for
local testing. The app is not code-signed yet.

## 8. Manual Smoke Test

Use copied test photos, not original photos. Work through
`RELEASE_CHECKLIST.md`; the app's error log is at
`%LOCALAPPDATA%\Photo GPS Editor\Photo GPS Editor\error-log.txt`.

## 9. Test On Another Windows Machine

Copy this whole folder to another Windows machine:

```text
dist\Photo GPS Editor
```

Run:

```text
Photo GPS Editor.exe
```

Confirm it works on a machine without Python and without ExifTool installed.

## 10. Release Files

Releases don't use a hand-made zip: pushing a `v*` tag makes GitHub Actions
build all three systems and attach these files to a draft release:

```text
photo-gps-editor-windows-x86_64.zip
photo-gps-editor-macos-arm64.zip
photo-gps-editor-linux-x86_64.tar.gz
Photo_GPS_Editor-x86_64.AppImage
```

To zip a local build anyway (for example to copy it to another machine):

```powershell
Compress-Archive -Path "dist\Photo GPS Editor" -DestinationPath "dist\photo-gps-editor-windows-x86_64.zip" -Force
```
