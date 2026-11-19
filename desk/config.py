from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DESK_", env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://exception_desk@127.0.0.1:5432/exception_desk"
    )
    carrier_url: HttpUrl = HttpUrl("http://127.0.0.1:8091")
    carrier_timeout_seconds: float = Field(default=3, gt=0, le=30)
    cookie_secure: bool = True
    session_hours: int = Field(default=8, ge=1, le=168)
    as_of_date: date | None = None
    demo_password: SecretStr | None = None
    web_dist: Path = Path("frontend/dist")

    def business_date(self) -> date:
        return self.as_of_date or datetime.now(UTC).date()
