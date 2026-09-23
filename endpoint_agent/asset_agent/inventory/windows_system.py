from .shared import as_list, powershell_json


def collect_system() -> dict:
    raw = powershell_json("""
      $os=Get-CimInstance Win32_OperatingSystem; $cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;
      $cs=Get-CimInstance Win32_ComputerSystem;
      $mem=Get-CimInstance Win32_PhysicalMemory | ForEach-Object {[pscustomobject]@{slot=$_.DeviceLocator;capacity_bytes=[int64]$_.Capacity;speed_mhz=$_.Speed;manufacturer=$_.Manufacturer;part_number=($_.PartNumber -as [string]).Trim()}};
      $vol=Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {[pscustomobject]@{drive=$_.DeviceID;label=$_.VolumeName;filesystem=$_.FileSystem;total_bytes=[int64]$_.Size;free_bytes=[int64]$_.FreeSpace}};
      $disk=Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {[pscustomobject]@{model=$_.FriendlyName;size_bytes=[int64]$_.Size;media_type=$_.MediaType.ToString();bus_type=$_.BusType.ToString();health=$_.HealthStatus.ToString();serial_number=$_.SerialNumber}};
      $gpu=Get-CimInstance Win32_VideoController | ForEach-Object {[pscustomobject]@{name=$_.Name;driver_version=$_.DriverVersion;adapter_ram_bytes=[int64]$_.AdapterRAM}};
      $bios=Get-CimInstance Win32_BIOS;
      $battery=Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1;
      [pscustomobject]@{
        os=[pscustomobject]@{edition=$os.Caption;version=$os.Version;build=$os.BuildNumber;architecture=$os.OSArchitecture;install_date=$os.InstallDate;last_boot=$os.LastBootUpTime};
        cpu=[pscustomobject]@{model=$cpu.Name;manufacturer=$cpu.Manufacturer;physical_cores=$cpu.NumberOfCores;logical_processors=$cpu.NumberOfLogicalProcessors;max_clock_mhz=$cpu.MaxClockSpeed;utilization_percent=$cpu.LoadPercentage};
        memory=[pscustomobject]@{total_bytes=[int64]$cs.TotalPhysicalMemory;available_bytes=([int64]$os.FreePhysicalMemory*1KB);modules=@($mem)};
        storage=[pscustomobject]@{volumes=@($vol);physical_disks=@($disk)};gpu=@($gpu);
        bios=[pscustomobject]@{vendor=$bios.Manufacturer;version=$bios.SMBIOSBIOSVersion;release_date=$bios.ReleaseDate};
        battery=if($battery){[pscustomobject]@{present=$true;percentage=$battery.EstimatedChargeRemaining;status=$battery.Status}}else{[pscustomobject]@{present=$false;status='Not Present'}}
      }
    """, timeout=30)
    memory = raw.get("memory") or {}
    total, available = int(memory.get("total_bytes") or 0), int(memory.get("available_bytes") or 0)
    used = max(0, total-available)
    memory.update({"used_bytes": used, "percent_used": round((used/total)*100, 1) if total else None,
                   "modules": as_list(memory.get("modules"))})
    storage = raw.get("storage") or {}
    storage["volumes"] = as_list(storage.get("volumes"))
    storage["physical_disks"] = as_list(storage.get("physical_disks"))
    for volume in storage["volumes"]:
        size, free = int(volume.get("total_bytes") or 0), int(volume.get("free_bytes") or 0)
        volume["percent_free"] = round((free/size)*100, 1) if size else None
    return {"os": raw.get("os") or {}, "cpu": raw.get("cpu") or {}, "memory": memory,
            "storage": storage, "gpu": as_list(raw.get("gpu")), "bios": raw.get("bios") or {},
            "battery": raw.get("battery") or {"present": False, "status": "Unknown"}}
