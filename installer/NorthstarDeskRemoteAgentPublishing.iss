; Remote agent publishing release.
; This payload replaces only the Northstar Desk server executable. It adds the
; administrator-only agent-release publishing endpoint and interface. It never
; writes the database, .env, Caddyfile, HTTPS certificates, ports, task
; definitions, endpoint enrollment records, or other existing configuration.

#define MyAppName "Northstar Desk Remote Agent Publishing"
#define MyAppVersion "0.4.76"

[Setup]
AppId={{B6200B42-6D7B-4F24-84A4-FBEDE96D7276}
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
OutputBaseFilename=NorthstarDesk-Remote-Agent-Publishing-Update-{#MyAppVersion}
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

[Run]
; Existing scheduled tasks are started without changing their definitions,
; server ports, certificate bindings, or persistent configuration.
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar HTTPS"""; Flags: runhidden waituntilterminated
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar Desk"""; Flags: runhidden waituntilterminated
