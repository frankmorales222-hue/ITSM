; Ticket-layout and endpoint-agent refresh update.
; This payload copies only the compiled browser interface and the new endpoint
; installer. It deliberately does not read or change the database, .env,
; Caddy configuration, HTTPS certificates, ports, authentication, routing, or
; server executable.

#define MyAppName "Northstar Desk Ticket and Agent Update"
#define MyAppVersion "0.4.73"

[Setup]
AppId={{A7C4D5E8-6F29-4D9C-94B6-2B5E4B7A9F73}
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
OutputBaseFilename=NorthstarDesk-Ticket-Agent-Update-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\frontend\dist\*"; DestDir: "{autopf}\Northstar Desk\_internal\frontend\dist"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\endpoint_agent\artifacts\NorthstarEndpointAgent-Setup-0.1.23.exe"; DestDir: "{autopf}\Northstar Desk\_internal\agent_installer"; Flags: ignoreversion

[Run]
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar HTTPS"""; Flags: runhidden waituntilterminated
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar Desk"""; Flags: runhidden waituntilterminated
