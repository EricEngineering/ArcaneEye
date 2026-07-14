; installer\arcaneeye.iss  (this file is copied here by the build script)
#define MyAppName    "Arcane Eye"
#define MyAppDirName "ArcaneEye"
; Version is the single source of truth in arcaneeye\__init__.py — build_installer.bat
; and CI extract it and pass it as /DMyAppVersion. This fallback only applies to a bare
; ISCC run and should be kept roughly in sync.
#ifndef MyAppVersion
  #define MyAppVersion "0.8.0"
#endif
#define MyPublisher  "Eric Hernandez"
#define MyAppExeName "ArcaneEye.exe"

[Setup]
CloseApplications=yes
RestartApplications=yes
PrivilegesRequired=admin
DefaultDirName={autopf}\{#MyAppDirName}
DefaultGroupName={#MyAppName}
AppId={{8D7F0B1B-6F83-48C5-A7A3-0A4E18A57E47}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
WizardStyle=modern
Compression=lzma
SolidCompression=yes
UsePreviousAppDir=yes
OutputDir=installer\output
OutputBaseFilename=ArcaneEye-Setup-{#MyAppVersion}

; These two files are staged by the build script right before ISCC runs
LicenseFile=installer\assets\AGPL_V3.txt
SetupIconFile=installer\assets\installer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Copy everything PyInstaller produced
Source: "dist\ArcaneEye\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
