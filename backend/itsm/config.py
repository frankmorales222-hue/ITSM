from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ITSM_", extra="ignore")
    database_url: str = "sqlite:///./data/itsm.db"
    environment: str = "development"
    secret_key: str = "development-only-change-this-secret-key"
    session_minutes: int = 480
    cookie_secure: bool = False
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_url: str = "http://127.0.0.1:8000"
    trusted_hosts: str = "127.0.0.1,localhost,testserver"
    forwarded_allow_ips: str = "127.0.0.1"
    backup_directory: str = "data/backups"
    app_version: str = "0.1.0"
    reopen_days: int = 7
    login_attempts: int = 5
    lockout_minutes: int = 15
    assetpilot_url: str = "http://127.0.0.1:5080"
    assetpilot_executable: str = ""
    assetpilot_database_path: str = ""

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
Path("data").mkdir(exist_ok=True)
Path(settings.backup_directory).mkdir(parents=True, exist_ok=True)
