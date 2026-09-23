#define MyAppName "Northstar Endpoint Agent"
#define MyAppVersion "0.1.37"

[Setup]
AppId={{6894E363-B668-4F80-9318-405974E3CE20}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Northstar
DefaultDirName={autopf}\Northstar Endpoint Agent
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts
OutputBaseFilename=NorthstarEndpointAgent-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\NorthstarEndpointTray\NorthstarEndpointTray.exe
CloseApplications=yes
RestartApplications=no

[Files]
Source: "artifacts\NorthstarEndpointAgent-enterprise\NorthstarEndpointAgent.exe"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "artifacts\NorthstarEndpointAgent-enterprise\NorthstarEndpointTray\*"; DestDir: "{app}\NorthstarEndpointTray"; Flags: ignoreversion recursesubdirs createallsubdirs restartreplace
Source: "assets\northstar.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\install-enterprise.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\uninstall-enterprise.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\install-self-service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\launch-tray.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "scripts\stop-agent-for-upgrade.ps1"; Flags: dontcopy

[Icons]
; Run the launcher in the interactive user's session at every sign-in.  The
; inventory service is still managed by the scheduled task; this shortcut is
; only the per-user notification-area companion and is deliberately guarded by
; the launcher's per-session mutex.
Name: "{commonstartup}\Northstar Endpoint Agent"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\launch-tray.ps1"""; WorkingDir: "{app}"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\launch-tray.ps1"" -Restart"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated runasoriginaluser

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall-enterprise.ps1"" -KeepInstallFiles"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveNorthstarAgentTasks"

[Code]
var
  EnrollmentPage: TInputQueryWizardPage;
  ConfigurationFailed: Boolean;
  InstallFinalized: Boolean;
  AutoUpdateMode: Boolean;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Parameters: String;
begin
  Result := '';
  ExtractTemporaryFile('stop-agent-for-upgrade.ps1');
  Parameters := '-NoProfile -ExecutionPolicy Bypass -File ' +
    AddQuotes(ExpandConstant('{tmp}\stop-agent-for-upgrade.ps1'));
  { Setup is already elevated because PrivilegesRequired=admin. Starting a
    second elevated process can lose the interactive session and fail to stop
    the tray. Run cleanup directly in Setup's administrator process. }
  if (not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Parameters, ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or
    (ResultCode <> 0) then
    Result := 'Northstar could not stop the existing agent. Diagnostic: ' +
      ExpandConstant('{commonappdata}\NorthstarEndpointAgent-stop-error.log');
end;

procedure InitializeWizard;
begin
  AutoUpdateMode := ExpandConstant('{param:AUTOUPDATE|0}') = '1';
  EnrollmentPage := CreateInputQueryPage(wpWelcome,
    'Connect this computer',
    'Paste the enrollment code from Northstar Desk',
    'Return to Northstar Desk, choose Install Windows Agent, copy the temporary enrollment code, and paste it below.');
  EnrollmentPage.Add('Enrollment code:', False);
  EnrollmentPage.Values[0] := ExpandConstant('{param:ENROLLMENTCODE|}');
end;

function ExistingAgentConfiguration(): Boolean;
begin
  Result := FileExists(ExpandConstant('{commonappdata}\NorthstarEndpointAgent\config.json'));
end;

function ExistingAgentTask(): Boolean;
var
  ResultCode: Integer;
begin
  { An enrolled computer normally already has this machine task. Its command
    points at the installed application directory, so retaining it is safer than regenerating enrollment or
    task XML during a binary-only update. }
  Result := Exec(ExpandConstant('{sys}\schtasks.exe'),
    '/Query /TN "Northstar Endpoint Agent"', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure StartExistingAgentTask;
var
  ResultCode: Integer;
begin
  { Older failed installers may have disabled this task while replacing
    binaries. Re-enable it before starting, so this repair restores a healthy
    enrollment without re-reading protected configuration. }
  Exec(ExpandConstant('{sys}\schtasks.exe'),
    '/Change /TN "Northstar Endpoint Agent" /Enable', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\schtasks.exe'),
    '/Run /TN "Northstar Endpoint Agent"', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = EnrollmentPage.ID) and
    (ExistingAgentConfiguration() or (Trim(EnrollmentPage.Values[0]) <> ''));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = EnrollmentPage.ID) and (not ExistingAgentConfiguration()) and
    (Pos('.', Trim(EnrollmentPage.Values[0])) = 0) then
  begin
    MsgBox('Paste a valid enrollment code from Northstar Desk.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Parameters: String;
  ErrorDetails: AnsiString;
  ErrorLog: String;
begin
  if CurStep = ssPostInstall then
  begin
    { A normal update must never read, recreate, or re-enroll the protected
      machine configuration.  Replace only the binaries and restart the task
      already associated with the enrolled endpoint. }
    if ExistingAgentConfiguration() and ExistingAgentTask() then
    begin
      WizardForm.StatusLabel.Caption := 'Updating the existing Northstar Endpoint Agent...';
      StartExistingAgentTask;
      InstallFinalized := True;
      exit;
    end;

    Parameters := '-NoProfile -ExecutionPolicy Bypass -File ' +
      AddQuotes(ExpandConstant('{app}\install-self-service.ps1')) + ' -EnrollmentCode ' +
      AddQuotes(Trim(EnrollmentPage.Values[0]));
    WizardForm.StatusLabel.Caption := 'Enrolling this computer and uploading its first inventory...';
    { Explicitly request the elevated token. Some browser-launched repair sessions
      reported an administrator setup process but started child PowerShell with a
      filtered token, which cannot read the machine-protected agent configuration. }
    if ((AutoUpdateMode and ((not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parameters,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0))) or
      ((not AutoUpdateMode) and ((not ShellExec('runas', ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parameters,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0)))) then
    begin
      ErrorLog := ExpandConstant('{commonappdata}\NorthstarEndpointAgent-install-error.log');
      ConfigurationFailed := True;
      { Do not raise an exception here. Inno rolls back every installed file
        when a Code event raises, which previously left an empty Program Files
        folder after a temporary network, TLS, or token failure. The launcher
        detects the diagnostic file and reports a nonzero result while keeping
        the repairable installation in place. }
      if not WizardSilent then
      begin
        if LoadStringFromFile(ErrorLog, ErrorDetails) then
          MsgBox('Northstar was installed, but connection setup failed. Diagnostic: ' + ErrorLog + #13#10 + String(ErrorDetails), mbError, MB_OK)
        else
          MsgBox('Northstar was installed, but connection setup failed. Diagnostic: ' + ErrorLog, mbError, MB_OK);
      end;
    end;
    InstallFinalized := True;
  end;
end;

procedure DeinitializeSetup;
var
  ResultCode: Integer;
  RepairScript: String;
  Parameters: String;
begin
  { PrepareToInstall stops the old scheduled tasks and tray before file
    replacement. If setup is cancelled or file replacement fails before the
    post-install repair runs, restore the existing enrolled installation. }
  RepairScript := ExpandConstant('{app}\install-self-service.ps1');
  if (not InstallFinalized) and ExistingAgentConfiguration() and FileExists(RepairScript) then
  begin
    { Cancellation after the update shutdown step must return the existing
      agent to service; it must not start a configuration repair. }
    if ExistingAgentTask() then
      StartExistingAgentTask
    else
    begin
      Parameters := '-NoProfile -ExecutionPolicy Bypass -File ' + AddQuotes(RepairScript);
      Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parameters,
        ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
