from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ITSM_", extra="ignore")
    database_url: str = "sqlite:///./data/itsm.db"
    secret_key: str = "development-only-change-this-secret-key"
    session_minutes: int = 480
    cookie_secure: bool = False
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    app_version: str = "0.1.0"
    reopen_days: int = 7
    login_attempts: int = 5
    lockout_minutes: int = 15

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]


settings = Settings()
Path("data").mkdir(exist_ok=True)

