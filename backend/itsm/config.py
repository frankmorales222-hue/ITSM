import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.environ.get("ITSM_CONFIG_FILE", ".env"), env_prefix="ITSM_", extra="ignore")
    database_url: str = "sqlite:///./data/itsm.db"
    environment: str = "development"
    secret_key: str = "development-only-change-this-secret-key"
    session_minutes: int = 480
    cookie_secure: bool = False
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_url: str = "http://127.0.0.1:8000"
    trusted_hosts: str = "127.0.0.1,localhost,testserver"
    forwarded_allow_ips: str = "127.0.0.1"
    bind_host: str = "127.0.0.1"
    backup_directory: str = "data/backups"
    data_directory: str = "data"
    static_directory: str = ""
    site_name: str = "Northstar Desk"
    port: int = 8000
    https_port: int = 443
    app_version: str = "0.4.67"
    outbound_email_enabled: bool = True
    reopen_days: int = 7
    login_attempts: int = 5
    lockout_minutes: int = 15
    assetpilot_url: str = "http://127.0.0.1:5080"
    assetpilot_port: int = 5080
    assetpilot_internal_url: str = "http://127.0.0.1:5080"
    assetpilot_executable: str = ""
    assetpilot_database_path: str = ""
    assetpilot_sync_minutes: int = 5
    # Inventory is an optional integration. Core authentication, ticketing,
    # email, and reporting must remain operational when it is unavailable.
    assetpilot_enabled: bool = False
    agent_assignment_observations: int = 2
    agent_snapshot_retention: int = 30
    agent_enrollment_hours: int = 24
    agent_allow_account_name_match: bool = True
    # Provider application registrations are deployment-level credentials.
    # Tenant administrators connect their own organizations through browser
    # consent and never enter these values in the normal administration UI.
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    ringcentral_client_id: str = ""
    ringcentral_client_secret: str = ""
    ringcentral_environment: str = "production"
    # The Ed25519 public key is safe to distribute with the server. The
    # corresponding private signing key must remain on the release workstation.
    update_public_key: str = ""
    update_staging_directory: str = ""
    update_max_package_mb: int = 512

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]

    @property
    def hosts(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]

    @property
    def production(self) -> bool:
        return self.environment.strip().lower() == "production"


settings = Settings()
Path(settings.data_directory).mkdir(parents=True, exist_ok=True)
Path(settings.backup_directory).mkdir(parents=True, exist_ok=True)
