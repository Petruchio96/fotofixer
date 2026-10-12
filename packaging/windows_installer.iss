; Inno Setup script for the Windows installer (see packaging/README.md).
;
; Compile from the repository root, after the PyInstaller build:
;   ISCC /DAppVersion=1.7.0 "/DSourceDir=dist\Photo GPS Editor" /Orelease-files packaging\windows_installer.iss
; CI does the same (.github/workflows/build.yml). The version comes from
; pyproject.toml through /DAppVersion, so it lives in one place.
;
; What it does: installs per user (no admin prompt) to
; %LOCALAPPDATA%\Programs\Photo GPS Editor, adds a Start menu shortcut and an
; optional desktop shortcut, lists an uninstaller in Settings > Apps, and
; upgrades in place: a newer setup replaces the old files (the fixed AppId
; below tells Windows it is the same program, so keep it even if the app is
; renamed). Settings (HKCU\Software\Photo GPS Editor) and the error log
; (%LOCALAPPDATA%\Photo GPS Editor) are outside the install folder, so an
; uninstall leaves them alone.

#define MyAppName "Photo GPS Editor"
#define MyAppExe "Photo GPS Editor.exe"
#define MyAppUrl "https://github.com/Petruchio96/photo-gps-editor"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Photo GPS Editor"
#endif

[Setup]
AppId={{7EC91185-EFCC-4AE6-871A-A65A162C396E}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher=Petruchio96
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}/issues
AppUpdatesURL={#MyAppUrl}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
; Per-user install: no UAC prompt, and the shortcuts go to this user's menus.
PrivilegesRequired=lowest
; The PyInstaller build is 64-bit only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; PySide6 needs Windows 10 or newer.
MinVersion=10.0
; The update checker downloads this exact file name.
OutputBaseFilename=photo-gps-editor-windows-x86_64-setup
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

[UninstallDelete]
; Anything the app itself added inside the install folder.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; A normal install: the "Launch Photo GPS Editor" checkbox on the last page.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; A silent install (the in-app updater): reopen the app once it is done.
Filename: "{app}\{#MyAppExe}"; Flags: nowait skipifnotsilent
