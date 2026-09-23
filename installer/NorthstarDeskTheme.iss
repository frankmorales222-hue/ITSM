; Northstar Desk appearance-only update payload.
; This installer intentionally copies only compiled browser assets. It never
; reads or writes the database, .env, Caddyfile, certificates, ports, services,
; endpoint agent, or application executable.

#define MyAppName "Northstar Desk Appearance"
#define MyAppVersion "0.4.88"

[Setup]
AppId={{74C1E059-46FA-421B-9D36-7F2E7F6F510A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Northstar
DefaultDirName={autopf}\Northstar Desk
DisableDirPage=yes
DisableProgramGroupPage=yes
CreateAppDir=no
Uninstallable=no
CreateUninstallRegKey=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts
OutputBaseFilename=NorthstarDesk-Appearance-Update-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Browser-only assets from the independently verified 0.4.88 appearance build.
Source: "..\frontend\dist\*"; DestDir: "{autopf}\Northstar Desk\_internal\frontend\dist"; Flags: ignoreversion recursesubdirs createallsubdirs
