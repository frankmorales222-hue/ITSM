#define MyAppName "Northstar Desk Server"
#define MyAppVersion "0.4.89"
#define MyAppPublisher "Northstar"
#define MyAppExeName "NorthstarDeskServer.exe"

[Setup]
; Evaluation and server packages are editions of the same application. Sharing
; the product identity makes Windows perform a safe in-place conversion.
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
OutputBaseFilename=NorthstarDesk-Server-Setup-{#MyAppVersion}
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

[Files]
Source: "dist\NorthstarDeskServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "open-northstar.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "run-northstar.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "run-caddy.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "export-migration.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "import-migration.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "install-tasks.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "vendor\Caddy\*"; DestDir: "{app}\Caddy"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "signing\update-public-key.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{commonappdata}\NorthstarDesk"; Permissions: admins-full system-full
Name: "{commonappdata}\NorthstarDesk\data"; Permissions: admins-full system-full
Name: "{commonappdata}\NorthstarDesk\backups"; Permissions: admins-full system-full

[Icons]
Name: "{group}\Open Northstar Desk"; Filename: "{app}\open-northstar.cmd"; WorkingDir: "{app}"
Name: "{group}\Server data and HTTPS configuration"; Filename: "{commonappdata}\NorthstarDesk"
Name: "{group}\Export server migration package"; Filename: "{app}\export-migration.cmd"; WorkingDir: "{app}"
Name: "{group}\Import server migration package"; Filename: "{app}\import-migration.cmd"; WorkingDir: "{app}"

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""Northstar Desk"""; Flags: runhidden; RunOnceId: "StopNorthstar"
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""Northstar AssetPilot"""; Flags: runhidden; RunOnceId: "StopNorthstarAssetPilot"
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""Northstar HTTPS"""; Flags: runhidden; RunOnceId: "StopNorthstarHttps"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Northstar Desk"" /F"; Flags: runhidden; RunOnceId: "DeleteNorthstarTask"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Northstar AssetPilot"" /F"; Flags: runhidden; RunOnceId: "DeleteNorthstarAssetPilotTask"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Northstar HTTPS"" /F"; Flags: runhidden; RunOnceId: "DeleteNorthstarHttpsTask"

[Code]
var
  RequirementsPage: TOutputMsgWizardPage;
  OrganizationPage: TInputQueryWizardPage;
  AdminAccountPage: TInputQueryWizardPage;
  DnsPage: TInputQueryWizardPage;
  PortsPage: TInputQueryWizardPage;
  DatabasePage: TInputQueryWizardPage;
  DatabaseAdminPage: TInputQueryWizardPage;
  StoragePage: TInputDirWizardPage;
  HadConfiguration: Boolean;

function ConfigurationExists: Boolean;
var
  Lines: TStringList;
  I: Integer;
begin
  Result := False;
  if not FileExists(ExpandConstant('{commonappdata}\NorthstarDesk\.env')) then
    exit;
  Lines := TStringList.Create;
  try
    Lines.LoadFromFile(ExpandConstant('{commonappdata}\NorthstarDesk\.env'));
    for I := 0 to Lines.Count - 1 do
      if CompareText(Trim(Lines[I]), 'ITSM_ENVIRONMENT=production') = 0 then
      begin
        Result := True;
        exit;
      end;
  finally
    Lines.Free;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := HadConfiguration and
    ((PageID = RequirementsPage.ID) or (PageID = OrganizationPage.ID) or
     (PageID = AdminAccountPage.ID) or
     (PageID = DatabasePage.ID) or (PageID = DatabaseAdminPage.ID) or
     (PageID = StoragePage.ID));
end;

function UrlHostName(Value: String; DefaultValue: String): String;
var
  Separator: Integer;
begin
  Result := Trim(Value);
  Separator := Pos('://', Result);
  if Separator > 0 then
    Delete(Result, 1, Separator + 2);
  Separator := Pos('/', Result);
  if Separator > 0 then
    Result := Copy(Result, 1, Separator - 1);
  Separator := Pos(':', Result);
  if Separator > 0 then
    Result := Copy(Result, 1, Separator - 1);
  if (Result = '') or (CompareText(Result, 'localhost') = 0) or
     (CompareText(Result, '127.0.0.1') = 0) then
    Result := DefaultValue;
end;

function ReadEnvValue(KeyName: String; DefaultValue: String): String;
var
  Lines: TStringList;
  I: Integer;
  Prefix: String;
begin
  Result := DefaultValue;
  if not FileExists(ExpandConstant('{commonappdata}\NorthstarDesk\.env')) then
    exit;
  Lines := TStringList.Create;
  try
    Lines.LoadFromFile(ExpandConstant('{commonappdata}\NorthstarDesk\.env'));
    Prefix := KeyName + '=';
    for I := 0 to Lines.Count - 1 do
      if Pos(Prefix, Lines[I]) = 1 then
      begin
        Result := Copy(Lines[I], Length(Prefix) + 1, MaxInt);
        if (Length(Result) >= 2) and (Result[1] = '"') and
           (Result[Length(Result)] = '"') then
          Result := Copy(Result, 2, Length(Result) - 2);
        exit;
      end;
  finally
    Lines.Free;
  end;
end;

procedure InitializeWizard;
begin
  HadConfiguration := ConfigurationExists;
  RequirementsPage := CreateOutputMsgPage(wpWelcome,
    'Network server installation',
    'Prerequisites for the shared pilot',
    'Before continuing, install PostgreSQL and keep the PostgreSQL administrator password available. ' +
    'Setup creates the Northstar database and a dedicated least-privilege application account automatically. ' +
    'Setup includes the verified HTTPS proxy and starts it automatically. Only TCP 443 should be exposed to the network. ' +
    'Outbound email remains disabled during the pilot. Existing server data is preserved during upgrades and uninstall.');

  OrganizationPage := CreateInputQueryPage(RequirementsPage.ID,
    'Organization and administrator',
    'Identify this Northstar Desk installation',
    'Enter the organization name and initial administrator email.');
  OrganizationPage.Add('Organization name:', False);
  OrganizationPage.Add('Administrator email:', False);
  OrganizationPage.Values[0] := ExpandConstant('{param:ORG|MedReceivables}');
  OrganizationPage.Values[1] := ExpandConstant('{param:ADMINEMAIL|admin@medreceivables.com}');

  AdminAccountPage := CreateInputQueryPage(OrganizationPage.ID,
    'Initial local administrator',
    'Protect the first Northstar Desk account',
    'Choose a unique password for the initial local administrator. It is used during initialization and is never written to the installer log or retained in a setup file.');
  AdminAccountPage.Add('Administrator password:', True);
  AdminAccountPage.Add('Confirm administrator password:', True);

  DnsPage := CreateInputQueryPage(AdminAccountPage.ID,
    'Internal HTTPS name',
    'Confirm the DNS entry for Northstar Desk',
    'This name must resolve to this server. It remains editable after installation in the protected server configuration.');
  DnsPage.Add('Northstar Desk DNS name:', False);
  DnsPage.Values[0] := ExpandConstant('{param:DNS|' +
    UrlHostName(ReadEnvValue('ITSM_PUBLIC_URL', ''), 'helpdesk.medreceivables.com') + '}');

  PortsPage := CreateInputQueryPage(DnsPage.ID,
    'Network ports',
    'Choose ports that are available on this server',
    'HTTPS is exposed to the network. Northstar Desk remains bound to localhost behind the HTTPS proxy. The two ports must be different and can be changed during a later upgrade.');
  PortsPage.Add('HTTPS port:', False);
  PortsPage.Add('Northstar Desk internal port:', False);
  PortsPage.Values[0] := ExpandConstant('{param:HTTPSPORT|' + ReadEnvValue('ITSM_HTTPS_PORT', '443') + '}');
  PortsPage.Values[1] := ExpandConstant('{param:NORTHSTARPORT|' + ReadEnvValue('ITSM_PORT', '8000') + '}');

  DatabasePage := CreateInputQueryPage(PortsPage.ID,
    'PostgreSQL database',
    'Provision the production database',
    'Setup connects once as a PostgreSQL administrator, creates the database and service account, then discards the administrator password.');
  DatabasePage.Add('Server:', False);
  DatabasePage.Add('Port:', False);
  DatabasePage.Add('Database name:', False);
  DatabasePage.Add('Application service account:', False);
  DatabasePage.Values[0] := ExpandConstant('{param:DBHOST|127.0.0.1}');
  DatabasePage.Values[1] := ExpandConstant('{param:DBPORT|5432}');
  DatabasePage.Values[2] := ExpandConstant('{param:DBNAME|northstar_desk}');
  DatabasePage.Values[3] := ExpandConstant('{param:DBUSER|itsm_service}');

  DatabaseAdminPage := CreateInputQueryPage(DatabasePage.ID,
    'PostgreSQL administrator',
    'Authorize database provisioning',
    'Enter the PostgreSQL administrator account created during PostgreSQL setup. The password is used once and is not retained.');
  DatabaseAdminPage.Add('PostgreSQL administrator:', False);
  DatabaseAdminPage.Add('PostgreSQL administrator password:', True);
  DatabaseAdminPage.Values[0] := ExpandConstant('{param:DBADMIN|postgres}');

  StoragePage := CreateInputDirPage(DatabaseAdminPage.ID,
    'Verified database backups',
    'Choose a protected backup destination',
    'For the pilot, this can be a local folder. Before go-live, use a separate disk or protected network destination.', False, 'New folder');
  StoragePage.Add('Northstar Desk backups:');
  StoragePage.Values[0] := ExpandConstant('{commonappdata}\NorthstarDesk\backups');
end;

function LooksLikeHostName(Value: String): Boolean;
begin
  Result := (Pos('.', Value) > 1) and (Pos(' ', Value) = 0) and
    (Pos('/', Value) = 0) and (CompareText(Value, '127.0.0.1') <> 0) and
    (CompareText(Value, 'localhost') <> 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
  HttpsPort: Integer;
  NorthstarPort: Integer;
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
  if CurPageID = AdminAccountPage.ID then
  begin
    if Length(AdminAccountPage.Values[0]) < 12 then
    begin
      MsgBox('Use at least 12 characters for the administrator password.', mbError, MB_OK);
      Result := False;
    end
    else if AdminAccountPage.Values[0] <> AdminAccountPage.Values[1] then
    begin
      MsgBox('The administrator passwords do not match.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = DnsPage.ID then
  begin
    if not LooksLikeHostName(Trim(DnsPage.Values[0])) then
    begin
      MsgBox('Enter a valid Northstar Desk DNS name.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = DatabasePage.ID then
  begin
    Port := StrToIntDef(DatabasePage.Values[1], 0);
    if (Trim(DatabasePage.Values[0]) = '') or (Port < 1) or (Port > 65535) or
       (Trim(DatabasePage.Values[2]) = '') or (Trim(DatabasePage.Values[3]) = '') then
    begin
      MsgBox('Complete the server, port, database name, and application service account. The port must be a number from 1 through 65535.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = PortsPage.ID then
  begin
    HttpsPort := StrToIntDef(PortsPage.Values[0], 0);
    NorthstarPort := StrToIntDef(PortsPage.Values[1], 0);
    if (HttpsPort < 1) or (HttpsPort > 65535) or
       (NorthstarPort < 1) or (NorthstarPort > 65535) then
    begin
      MsgBox('Each port must be a number from 1 through 65535.', mbError, MB_OK);
      Result := False;
    end
    else if HttpsPort = NorthstarPort then
    begin
      MsgBox('HTTPS and Northstar Desk must use different ports.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = DatabaseAdminPage.ID then
  begin
    if Trim(DatabaseAdminPage.Values[0]) = '' then
    begin
      MsgBox('Enter the PostgreSQL administrator account. The default account is postgres.', mbError, MB_OK);
      Result := False;
    end
    else if DatabaseAdminPage.Values[1] = '' then
    begin
      MsgBox('Enter the PostgreSQL administrator password created when PostgreSQL was installed.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Northstar Desk"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Northstar AssetPilot"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Northstar HTTPS"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM NorthstarDeskServer.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM caddy.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Parameters: String;
  PasswordFile: String;
  InitialAdminPasswordFile: String;
  ErrorLogPath: String;
  ErrorDetail: String;
  RawErrorDetail: AnsiString;
begin
  if CurStep = ssPostInstall then
  begin
    ErrorLogPath := ExpandConstant('{commonappdata}\NorthstarDesk\setup-error.log');
    DeleteFile(ErrorLogPath);
    WizardForm.StatusLabel.Caption := 'Checking required network ports...';
    Parameters := 'check-ports --data-root ' + AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk')) +
      ' --https-port ' + PortsPage.Values[0] +
      ' --northstar-port ' + PortsPage.Values[1];
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('One or more selected ports (' + PortsPage.Values[0] + ', ' +
        PortsPage.Values[1] +
        ') are unavailable. Return to Network ports and choose unused values. Diagnostic: ' + ErrorLogPath);
  end;
  if (CurStep = ssPostInstall) and (not HadConfiguration) then
  begin
    PasswordFile := ExpandConstant('{tmp}\northstar-postgres-admin-password.txt');
    InitialAdminPasswordFile := ExpandConstant('{tmp}\northstar-initial-admin-password.txt');
    SaveStringToFile(PasswordFile, DatabaseAdminPage.Values[1], False);
    SaveStringToFile(InitialAdminPasswordFile, AdminAccountPage.Values[0], False);
    Exec(ExpandConstant('{sys}\icacls.exe'), AddQuotes(PasswordFile) + ' /inheritance:r /grant:r "Administrators:(F)" "SYSTEM:(F)"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{sys}\icacls.exe'), AddQuotes(InitialAdminPasswordFile) + ' /inheritance:r /grant:r "Administrators:(F)" "SYSTEM:(F)"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Parameters := 'configure-production --data-root ' + AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk')) +
      ' --organization ' + AddQuotes(OrganizationPage.Values[0]) +
      ' --admin-email ' + AddQuotes(OrganizationPage.Values[1]) +
      ' --dns-name ' + AddQuotes(DnsPage.Values[0]) +
      ' --https-port ' + PortsPage.Values[0] +
      ' --northstar-port ' + PortsPage.Values[1] +
      ' --database-host ' + AddQuotes(DatabasePage.Values[0]) +
      ' --database-port ' + DatabasePage.Values[1] +
      ' --database-name ' + AddQuotes(DatabasePage.Values[2]) +
      ' --database-user ' + AddQuotes(DatabasePage.Values[3]) +
      ' --database-admin-user ' + AddQuotes(DatabaseAdminPage.Values[0]) +
      ' --database-admin-password-file ' + AddQuotes(PasswordFile) +
      ' --initial-admin-password-file ' + AddQuotes(InitialAdminPasswordFile) +
      ' --backup-directory ' + AddQuotes(StoragePage.Values[0]);
    ErrorLogPath := ExpandConstant('{commonappdata}\NorthstarDesk\setup-error.log');
    DeleteFile(ErrorLogPath);
    WizardForm.StatusLabel.Caption := 'Validating PostgreSQL and preparing Northstar Desk...';
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      DeleteFile(PasswordFile);
      DeleteFile(InitialAdminPasswordFile);
      ErrorDetail := '';
      RawErrorDetail := '';
      if LoadStringFromFile(ErrorLogPath, RawErrorDetail) then
      begin
        ErrorDetail := RawErrorDetail;
        ErrorDetail := #13#10 + #13#10 + Copy(ErrorDetail, 1, 1800) + #13#10 +
          'Complete diagnostic: ' + ErrorLogPath;
      end;
      RaiseException('Server configuration failed. Setup error code: ' + IntToStr(ResultCode) + ErrorDetail);
    end;
    DeleteFile(PasswordFile);
    DeleteFile(InitialAdminPasswordFile);
  end;
  if (CurStep = ssPostInstall) and HadConfiguration then
  begin
    ErrorLogPath := ExpandConstant('{commonappdata}\NorthstarDesk\setup-error.log');
    DeleteFile(ErrorLogPath);
    WizardForm.StatusLabel.Caption := 'Applying the selected service ports...';
    Parameters := 'configure-ports --data-root ' +
      AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk')) +
      ' --dns-name ' + AddQuotes(DnsPage.Values[0]) +
      ' --https-port ' + PortsPage.Values[0] +
      ' --northstar-port ' + PortsPage.Values[1];
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('The selected service ports could not be saved. Diagnostic: ' + ErrorLogPath);

    ErrorLogPath := ExpandConstant('{commonappdata}\NorthstarDesk\setup-error.log');
    DeleteFile(ErrorLogPath);
    WizardForm.StatusLabel.Caption := 'Creating and verifying the pre-upgrade database backup...';
    Parameters := 'backup --data-root ' + AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk'));
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('The verified pre-upgrade database backup failed. Setup stopped before migration. Diagnostic: ' + ErrorLogPath);

    DeleteFile(ErrorLogPath);
    WizardForm.StatusLabel.Caption := 'Applying and validating database migrations...';
    Parameters := 'migrate --data-root ' + AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk'));
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('The database migration failed. The verified pre-upgrade backup is preserved. Diagnostic: ' + ErrorLogPath);
  end;
  if (CurStep = ssPostInstall) and FileExists(ExpandConstant('{app}\update-public-key.txt')) then
  begin
    Parameters := 'configure-update-trust --data-root ' + AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk')) +
      ' --public-key-file ' + AddQuotes(ExpandConstant('{app}\update-public-key.txt'));
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('The application files were installed, but update-signature trust could not be configured. Setup error code: ' + IntToStr(ResultCode));
  end;
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Installing and starting supervised server services...';
    Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' +
      AddQuotes(ExpandConstant('{app}\install-tasks.ps1'));
    if (not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parameters,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('Northstar services could not be installed or started. Setup error code: ' +
        IntToStr(ResultCode) + '. Review the setup log before retrying.');

    WizardForm.StatusLabel.Caption := 'Waiting for Northstar Desk and HTTPS...';
    Parameters := 'wait-ready --data-root ' +
      AddQuotes(ExpandConstant('{commonappdata}\NorthstarDesk')) + ' --timeout 120';
    if (not Exec(ExpandConstant('{app}\{#MyAppExeName}'), Parameters, ExpandConstant('{app}'),
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      RaiseException('One or more Northstar services did not become ready. Setup error code: ' +
        IntToStr(ResultCode) + '. Diagnostic: ' +
        ExpandConstant('{commonappdata}\NorthstarDesk\setup-error.log'));
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  PublicAddress: String;
begin
  if CurPageID = wpFinished then
  begin
    PublicAddress := ReadEnvValue('ITSM_PUBLIC_URL', 'https://' + DnsPage.Values[0]);
    WizardForm.FinishedLabel.Caption :=
      'Northstar Desk Server has been installed.' + #13#10 + #13#10 +
      'Initial local administrator: admin. Use the password selected during setup.' + #13#10 + #13#10 +
      'Next: trust the generated Northstar HTTPS root certificate through Group Policy for network computers.' + #13#10 +
      'Then open ' + PublicAddress + ' and complete the pilot checklist.' + #13#10 + #13#10 +
      'Outbound email is disabled for testing. Server databases are preserved during upgrades and uninstall.';
  end;
end;
