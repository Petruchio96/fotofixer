; Inno Setup script for the Windows installer (see packaging/README.md).
;
; Compile from the repository root, after the PyInstaller build:
;   ISCC /DAppVersion=1.7.0 "/DSourceDir=dist\FotoFixer" /Orelease-files packaging\windows_installer.iss
; CI does the same (.github/workflows/build.yml). The version comes from
; pyproject.toml through /DAppVersion, so it lives in one place.
;
; What it does: installs per user (no admin prompt) to
; %LOCALAPPDATA%\Programs\FotoFixer, adds a Start menu shortcut and an
; optional desktop shortcut, lists an uninstaller in Settings > Apps, and
; upgrades in place: a newer setup replaces the old files (the fixed AppId
; below tells Windows it is the same program, so keep it even though the app
; was renamed). Settings (HKCU\Software\FotoFixer) and the error log
; (%LOCALAPPDATA%\FotoFixer) are outside the install folder, so an
; uninstall leaves them alone.
;
; The app was called Photo GPS Editor until 1.9.0. Upgrading from it moves
; the install to the new folder and removes the old folder and shortcuts
; (UsePreviousAppDir and [InstallDelete] below); the app copies the old
; settings over itself (gui/settings_migration.py).

#define MyAppName "FotoFixer"
#define MyAppSubtitle "When & Where"
#define OldAppName "Photo GPS Editor"
#define MyAppExe "FotoFixer.exe"
#define MyAppUrl "https://github.com/Petruchio96/fotofixer"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\FotoFixer"
#endif

[Setup]
AppId={{7EC91185-EFCC-4AE6-871A-A65A162C396E}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} – {#MyAppSubtitle} {#AppVersion}
AppComments=Fixes where and when photos were taken: GPS location, date, time, and time zone
AppPublisher=Petruchio96
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}/issues
AppUpdatesURL={#MyAppUrl}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
; Always the folder above, even when upgrading a copy installed elsewhere (the
; Photo GPS Editor folder, which [InstallDelete] removes).
UsePreviousAppDir=no
DisableProgramGroupPage=yes
; Per-user install: no UAC prompt, and the shortcuts go to this user's menus.
PrivilegesRequired=lowest
; The PyInstaller build is 64-bit only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; PySide6 needs Windows 10 or newer.
MinVersion=10.0
; The update checker downloads this exact file name.
OutputBaseFilename=fotofixer-windows-x86_64-setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; An upgrade closes a running copy first (Setup asks; silent installs pass
; /CLOSEAPPLICATIONS). The [Run] entry below reopens it after a silent
; upgrade, so Windows's own restart (RestartApplications) is left off: it only
; works for programs that register for it, and could mean a second launch.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; The previous build's _internal folder goes first, so no stale DLLs or data
; files from an older PyInstaller build linger next to the new ones.
Type: filesandordirs; Name: "{app}\_internal"
; The app before its rename (Photo GPS Editor): its folder and shortcuts.
Type: filesandordirs; Name: "{localappdata}\Programs\{#OldAppName}"
Type: files; Name: "{autoprograms}\{#OldAppName}.lnk"
Type: files; Name: "{autodesktop}\{#OldAppName}.lnk"

[UninstallDelete]
; Anything the app itself added inside the install folder.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; A normal install: the "Launch FotoFixer" checkbox on the last page.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; A silent install (the in-app updater): reopen the app once it is done.
Filename: "{app}\{#MyAppExe}"; Flags: nowait skipifnotsilent
