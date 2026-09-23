; Update-controller recovery release.
; Replaces only the packaged Northstar server executable and the endpoint-agent
; installer. It never writes the database, .env, Caddyfile, certificates, ports,
; task definitions, or any existing configuration.

#define MyAppName "Northstar Desk Update Controller"
#define MyAppVersion "0.4.75"

[Setup]
AppId={{C6E80BC8-1A9F-4DCE-9942-81276AF3E0D2}
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
OutputBaseFilename=NorthstarDesk-Update-Controller-{#MyAppVersion}
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
Source: "..\endpoint_agent\artifacts\NorthstarEndpointAgent-Setup-0.1.24.exe"; DestDir: "{autopf}\Northstar Desk\_internal\agent_installer"; Flags: ignoreversion

[Run]
; The update supervisor has stopped these existing tasks. Starting them here
; does not alter their command, account, trigger, HTTPS certificate, or ports.
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar HTTPS"""; Flags: runhidden waituntilterminated
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar Desk"""; Flags: runhidden waituntilterminated
