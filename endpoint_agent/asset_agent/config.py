import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .storage.credential_store import protect, unprotect


def default_data_dir() -> Path:
    root = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "NorthstarEndpointAgent"


@dataclass
class AgentConfig:
    server_url: str
    tls_certificate_sha256: str = ""
    protected_credential: str = ""
    user_email_override: str = ""
    full_interval_seconds: int = 21600
    heartbeat_interval_seconds: int = 60
    credential_scope: str = "user"

    @property
    def credential(self) -> str:
        return unprotect(self.protected_credential) if self.protected_credential else ""

    def set_credential(self, value: str) -> None:
        self.protected_credential = protect(value, machine_scope=self.credential_scope == "machine")

    @classmethod
    def load(cls, path: Path) -> "AgentConfig":
        config = cls(**json.loads(path.read_text(encoding="utf-8")))
        # Existing devices used a fifteen-minute status interval.  Keep the
        # request very small, but check often enough for support messages and
        # high-visibility announcements to feel immediate.
        config.heartbeat_interval_seconds = min(max(15, int(config.heartbeat_interval_seconds)), 30)
        return config

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
