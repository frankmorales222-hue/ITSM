import hashlib
import re

from ..inventory.shared import powershell_json

INVALID_UUIDS = {"00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff"}


def _clean(value) -> str:
    return str(value or "").strip()


def stable_device_id(smbios_uuid: str, serial: str, manufacturer: str, model: str, machine_guid: str) -> tuple[str, str]:
    uuid = _clean(smbios_uuid).lower()
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", uuid) and uuid not in INVALID_UUIDS:
        source, material = "smbios_uuid", uuid
    elif _clean(serial).lower() not in {"", "unknown", "none", "to be filled by o.e.m."}:
        source = "hardware_composite"
        material = "|".join((_clean(serial), _clean(manufacturer), _clean(model))).lower()
    elif _clean(machine_guid):
        source, material = "machine_guid", _clean(machine_guid).lower()
    else:
        raise RuntimeError("Windows did not provide usable device identity material")
    return hashlib.sha256(f"northstar-device-v1|{source}|{material}".encode()).hexdigest(), source


def collect_identity() -> dict:
    raw = powershell_json("""
      $product=Get-CimInstance Win32_ComputerSystemProduct;
      $bios=Get-CimInstance Win32_BIOS;
      $system=Get-CimInstance Win32_ComputerSystem;
      [pscustomobject]@{smbios_uuid=$product.UUID;serial_number=$bios.SerialNumber;
        manufacturer=$system.Manufacturer;model=$system.Model;hostname=$env:COMPUTERNAME;
        machine_guid=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography').MachineGuid;
        chassis_type=((Get-CimInstance Win32_SystemEnclosure).ChassisTypes -join ',')}
    """)
    device_id, identity_source = stable_device_id(raw.get("smbios_uuid"), raw.get("serial_number"),
                                                   raw.get("manufacturer"), raw.get("model"), raw.get("machine_guid"))
    return {"device_id": device_id, "identity_source": identity_source,
            "hostname": _clean(raw.get("hostname")), "manufacturer": _clean(raw.get("manufacturer")) or "Unknown",
            "model": _clean(raw.get("model")) or "Unknown", "serial_number": _clean(raw.get("serial_number")) or "Unknown",
            "chassis_type": _clean(raw.get("chassis_type")) or "Unknown"}
