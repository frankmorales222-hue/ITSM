; Updater lifecycle repair release.
; This installer replaces only the packaged Northstar server executable. It does
; not write the database, .env, Caddyfile, certificates, ports, endpoint agent,
; task definitions, or any existing configuration.

#define MyAppName "Northstar Desk Updater Repair"
#define MyAppVersion "0.4.86"

[Setup]
AppId={{14F6A014-6051-4C17-954B-52B7300768B1}
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
OutputBaseFilename=NorthstarDesk-Updater-Repair-{#MyAppVersion}
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
; The update supervisor has stopped these existing tasks. Starting them here
; does not alter their command, account, trigger, HTTPS certificate, or ports.
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar HTTPS"""; Flags: runhidden waituntilterminated
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar Desk"""; Flags: runhidden waituntilterminated
