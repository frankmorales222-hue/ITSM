#define MyAppName "Northstar Desk"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Northstar"
#define MyAppExeName "NorthstarDeskServer.exe"

[Setup]
AppId={{B9890ED4-B32B-40E6-83D0-9A553FE65B4E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Northstar Desk
DefaultGroupName=Northstar Desk
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts
OutputBaseFilename=NorthstarDesk-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
ChangesEnvironment=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startserver"; Description: "Start Northstar Desk automatically with Windows"; GroupDescription: "Server startup:"; Flags: checkedonce

[Files]
Source: "dist\NorthstarDeskServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "open-northstar.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "run-northstar.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "run-assetpilot.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "vendor\AssetPilot\*"; DestDir: "{app}\AssetPilot"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; The local evaluation server runs in the signed-in user's session when the
; optional startup task is unavailable, so its SQLite database must be writable.
Name: "{commonappdata}\NorthstarDesk"; Permissions: users-modify
Name: "{commonappdata}\NorthstarDesk\AssetPilot\Data"; Permissions: admins-full system-full
Name: "{commonappdata}\NorthstarDesk\AssetPilot\Backups"; Permissions: admins-full system-full

[Icons]
Name: "{group}\Open Northstar Desk"; Filename: "{app}\open-northstar.cmd"; WorkingDir: "{app}"
Name: "{group}\Northstar Desk Data"; Filename: "{commonappdata}\NorthstarDesk"
Name: "{autodesktop}\Northstar Desk"; Filename: "{app}\open-northstar.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{sys}\schtasks.exe"; Parameters: "/Create /TN ""Northstar Desk"" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR """"{app}\run-northstar.cmd"""" /F"; Flags: runhidden waituntilterminated; Tasks: startserver
Filename: "{sys}\schtasks.exe"; Parameters: "/Create /TN ""Northstar AssetPilot"" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR """"{app}\run-assetpilot.cmd"""" /F"; Flags: runhidden waituntilterminated; Tasks: startserver
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar AssetPilot"""; Flags: runhidden waituntilterminated; Tasks: startserver
Filename: "{sys}\schtasks.exe"; Parameters: "/Run /TN ""Northstar Desk"""; Flags: runhidden waituntilterminated; Tasks: startserver
Filename: "{app}\open-northstar.cmd"; Description: "Open Northstar Desk"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""Northstar Desk"""; Flags: runhidden; RunOnceId: "StopNorthstar"
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""Northstar AssetPilot"""; Flags: runhidden; RunOnceId: "StopNorthstarAssetPilot"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Northstar Desk"" /F"; Flags: runhidden; RunOnceId: "DeleteNorthstarTask"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Northstar AssetPilot"" /F"; Flags: runhidden; RunOnceId: "DeleteNorthstarAssetPilotTask"

[Code]
var
  OrganizationPage: TInputQueryWizardPage;
  ServerPage: TInputQueryWizardPage;
  LocalInfoPage: TOutputMsgWizardPage;

procedure InitializeWizard;
begin
  LocalInfoPage := CreateOutputMsgPage(wpWelcome,
    'Local evaluation installation',
    'A safe first installation for this laptop',
    'This installer creates a separate Northstar Desk evaluation environment. ' +
    'It uses SQLite and listens only on this computer. Your source project and existing ITSM data are not changed. ' +
    'PostgreSQL, HTTPS, Microsoft Entra, and multi-tenant settings can be configured later for the shared server.');

  OrganizationPage := CreateInputQueryPage(LocalInfoPage.ID,
    'Organization and administrator',
    'Identify this evaluation installation',
    'Enter the organization name and administrator email used for this test.');
  OrganizationPage.Add('Organization name:', False);
  OrganizationPage.Add('Administrator email:', False);
  OrganizationPage.Values[0] := ExpandConstant('{param:ORG|Northstar}');
  OrganizationPage.Values[1] := ExpandConstant('{param:ADMINEMAIL|admin@example.test}');

  ServerPage := CreateInputQueryPage(OrganizationPage.ID,
    'Local server settings',
    'Choose the local listening port',
    'The application remains available only from this laptop during evaluation.');
  ServerPage.Add('HTTP port:', False);
  ServerPage.Values[0] := ExpandConstant('{param:PORT|8000}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  if CurPageID = OrganizationPage.ID then
  begin
    if Trim(OrganizationPage.Values[0]) = '' then
    begin
      MsgBox('Enter an organization name.', mbError, MB_OK);
      Result := False;
    end
    else if Pos('@', OrganizationPage.Values[1]) = 0 then
    begin
      MsgBox('Enter a valid administrator email address.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = ServerPage.ID then
  begin
    Port := StrToIntDef(ServerPage.Values[0], 0);
    if (Port < 1024) or (Port > 65535) then
    begin
      MsgBox('Enter an available port between 1024 and 65535.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function NeedsConfiguration: Boolean;
begin
  Result := not FileExists(ExpandConstant('{commonappdata}\NorthstarDesk\.env'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Parameters: String;
begin
  if (CurStep = ssPostInstall) and NeedsConfiguration then
  begin
    Parameters := 'configure-local --data-root ' + AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk')) +
      ' --organization ' + AddQuotes(OrganizationPage.Values[0]) +
      ' --admin-email ' + AddQuotes(OrganizationPage.Values[1]) +
      ' --port ' + ServerPage.Values[0];
    WizardForm.StatusLabel.Caption := 'Creating the database and preparing Northstar Desk...';
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('Northstar Desk configuration failed. Setup log error code: ' + IntToStr(ResultCode));
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    WizardForm.FinishedLabel.Caption :=
      'Northstar Desk has been installed.' + #13#10 + #13#10 +
      'Initial username: admin' + #13#10 +
      'Temporary password: ChangeMe!2026' + #13#10 + #13#10 +
      'You will be required to choose a new password after signing in.';
  end;
end;
