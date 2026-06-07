from functools import lru_cache
from pathlib import Path
from typing import Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    APP_NAME: str = Field(...)
    DEBUG: bool = Field(...)

    DATABASE_URL: str = Field(...)
    CORS_ORIGINS: list[str] = Field(...)

    JWT_SECRET: str = Field(...)
    JWT_ALGORITHM: str = Field(...)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(...)

    RED_AI_AFTER_DAYS: int = Field(...)

    # ── Mail automation toggles (safe defaults: everything OFF) ───────────
    SCHEDULER_ENABLED: bool = Field(...)
    MAIL_INBOX_ENABLED: bool = Field(...)
    SMTP_ENABLED: bool = Field(...)
    AUTO_PO_FOLLOWUP_ENABLED: bool = Field(default=False)
    MAIL_FETCH_PROTOCOL: str = Field(...)
    MAIL_INBOX_USE_SSL: bool = Field(...)

    # Inbound mailbox credentials (used for IMAP or POP3 mode)
    IMAP_HOST: str = Field(...)
    IMAP_PORT: int = Field(...)
    IMAP_USER: str = Field(...)
    IMAP_PASSWORD: str = Field(...)
    IMAP_FOLDER: str = Field(...)

    # SMTP (outgoing)
    SMTP_HOST: str = Field(...)
    SMTP_PORT: int = Field(...)
    SMTP_USER: str = Field(...)
    SMTP_PASSWORD: str = Field(...)
    SMTP_FROM: str = Field(...)

    # Cron intervals (minutes)
    MAIL_FETCH_INTERVAL_MINUTES: int = Field(...)
    STATUS_CHANGE_INTERVAL_MINUTES: int = Field(...)
    AUTO_REPLY_INTERVAL_MINUTES: int = Field(...)
    MAIL_SEND_INTERVAL_MINUTES: int = Field(...)

    @field_validator("MAIL_FETCH_PROTOCOL", mode="before")
    @classmethod
    def parse_mail_fetch_protocol(cls, value: Any) -> Any:
        normalized = str(value).strip().upper()
        if normalized not in {"IMAP", "POP3"}:
            raise ValueError("MAIL_FETCH_PROTOCOL must be IMAP or POP3")
        return normalized

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
