from datetime import datetime, timezone

from .. import __version__
from ..identity.device_identity import collect_identity
from .shared import probe
from .windows_management import collect_management
from .windows_network import collect_network
from .windows_security import collect_security
from .windows_software import collect_software
from .windows_system import collect_system


def collect_full_inventory(observed_user: dict | None = None) -> dict:
    diagnostics = []
    identity, event = probe("identity", collect_identity, None); diagnostics.append(event)
    if identity is None:
        raise RuntimeError("Stable device identity could not be collected")
    system, event = probe("system", collect_system, {}); diagnostics.append(event)
    security, event = probe("security", collect_security, {}); diagnostics.append(event)
    management, event = probe("management", collect_management, {}); diagnostics.append(event)
    network, event = probe("network", collect_network, {"adapters": []}); diagnostics.append(event)
    software, event = probe("software", collect_software, []); diagnostics.append(event)
    unknowns = [item["probe"] for item in diagnostics if item["status"] != "Completed"]
    return {
        "schema_version": 1, "device_id": identity.pop("device_id"), "agent_version": __version__,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "observed_user": observed_user or {},
        "observed_user_email": (observed_user or {}).get("email"),
        "device": identity, "os": system.get("os", {}), "cpu": system.get("cpu", {}),
        "memory": system.get("memory", {}), "storage": system.get("storage", {}),
        "gpu": system.get("gpu", []), "bios": system.get("bios", {}), "security": security,
        "management": management, "network": network, "battery": system.get("battery", {}),
        "peripherals": {}, "software": software,
        "health": {"status": "Healthy with Unknowns" if unknowns else "Healthy", "unknown_count": len(unknowns),
                   "unknown_checks": unknowns, "attention_reasons": []},
        "diagnostics": diagnostics,
    }
