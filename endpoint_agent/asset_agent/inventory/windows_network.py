from .shared import as_list, powershell_json


def collect_network() -> dict:
    raw = powershell_json("""
      @(Get-NetIPConfiguration | Where-Object {$_.NetAdapter.Status -eq 'Up'} | ForEach-Object {
        $name=$_.InterfaceAlias; $desc=$_.NetAdapter.InterfaceDescription;
        $type=if($name -match 'VPN|Tunnel'){'VPN'}elseif($name -match 'Wi-Fi|Wireless' -or $desc -match 'Wireless|Wi-Fi'){'Wi-Fi'}elseif($name -match 'Bluetooth'){'Bluetooth'}elseif($_.NetAdapter.Virtual){'Virtual'}else{'Ethernet'};
        [pscustomobject]@{name=$name;description=$desc;type=$type;mac_address=$_.NetAdapter.MacAddress;
          ipv4=@($_.IPv4Address.IPAddress);gateway=@($_.IPv4DefaultGateway.NextHop);state=$_.NetAdapter.Status}
      })
    """, default=[])
    return {"adapters": as_list(raw)}
