from .shared import as_list, powershell_json


def collect_security() -> dict:
    return powershell_json("""
      function TryValue([scriptblock]$Action){try{& $Action}catch{'Unavailable'}};
      $tpm=TryValue { $v=Get-Tpm; [pscustomobject]@{present=$v.TpmPresent;ready=$v.TpmReady;enabled=$v.TpmEnabled;activated=$v.TpmActivated} };
      $secure=TryValue { if(Confirm-SecureBootUEFI){'Enabled'}else{'Disabled'} };
      $bitlocker=TryValue { @(Get-BitLockerVolume | ForEach-Object {[pscustomobject]@{mount_point=$_.MountPoint;volume_status=$_.VolumeStatus.ToString();protection_status=$_.ProtectionStatus.ToString();encryption_method=$_.EncryptionMethod.ToString();encryption_percentage=$_.EncryptionPercentage}}) };
      $defender=TryValue { $v=Get-MpComputerStatus; [pscustomobject]@{antivirus_enabled=$v.AntivirusEnabled;real_time_protection=$v.RealTimeProtectionEnabled;signatures_last_updated=$v.AntivirusSignatureLastUpdated} };
      $firewall=TryValue { @(Get-NetFirewallProfile | ForEach-Object {[pscustomobject]@{profile=$_.Name;enabled=$_.Enabled}}) };
      $pending=(Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') -or (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired');
      [pscustomobject]@{tpm=$tpm;secure_boot=$secure;encryption=$bitlocker;defender=$defender;firewall=$firewall;pending_reboot=if($pending){'Yes'}else{'No'}}
    """, timeout=30)
