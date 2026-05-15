; Inno Setup script for SignClip.
; Build with: ISCC.exe build\installer.iss
; Download Inno Setup: https://jrsoftware.org/isinfo.php
;
; Produces dist\SignClip-Setup.exe — a one-click installer that places
; SignClip in %LOCALAPPDATA%\Programs\SignClip (no admin required),
; adds a Start Menu shortcut, and writes an uninstaller.

#define MyAppName "SignClip"
#define MyAppVersion "1.0.0"
#define MyAppExeName "SignClip.exe"
#define MyAppPublisher "SignClip"
#define MyAppURL "https://github.com/yourname/signclip"

[Setup]
AppId={{B9F1B4F0-7C7C-4F3B-9F8C-2D2D2D2D2D2D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=SignClip-Setup
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start SignClip when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\SignClip.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
