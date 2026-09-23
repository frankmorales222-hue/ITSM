; Endpoint-agent refresh release.
; It replaces only the installer distributed from the Help Desk portal. It
; does not modify Northstar Desk application files, its database, Caddy,
; HTTPS certificates, ports, services, or any existing configuration.

#define MyAppName "Northstar Desk Endpoint Agent Refresh"
#define MyAppVersion "0.4.83"

[Setup]
AppId={{EDB93490-5A90-4D53-AEE3-C828C6490340}
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
OutputBaseFilename=NorthstarDesk-Agent-Refresh-Update-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\endpoint_agent\artifacts\NorthstarEndpointAgent-Setup-0.1.31.exe"; DestDir: "{autopf}\Northstar Desk\_internal\agent_installer"; Flags: ignoreversion
