; Combined 0.4.77 identity correction and appearance release.
; Replaces only the packaged server executable, endpoint-agent installer, and browser assets.
; It does not write the database, .env, Caddyfile, HTTPS certificates, ports,
; task definitions, or any existing configuration.

#define MyAppName "Northstar Desk Identity and Appearance Update"
#define MyAppVersion "0.4.79"

[Setup]
AppId={{6AF19C8B-0D79-421C-A234-5C2B30F2A5D7}
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
OutputBaseFilename=NorthstarDesk-Identity-Theme-Update-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\NorthstarDeskServer\NorthstarDeskServer.exe"; DestDir: "{autopf}\Northstar Desk"; Flags: ignoreversion
Source: "..\endpoint_agent\artifacts\NorthstarEndpointAgent-Setup-0.1.26.exe"; DestDir: "{autopf}\Northstar Desk\_internal\agent_installer"; Flags: ignoreversion
Source: "..\frontend\dist\*"; DestDir: "{autopf}\Northstar Desk\_internal\frontend\dist"; Flags: ignoreversion recursesubdirs createallsubdirs

[Run]
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar HTTPS"""; Flags: runhidden waituntilterminated
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar Desk"""; Flags: runhidden waituntilterminated
