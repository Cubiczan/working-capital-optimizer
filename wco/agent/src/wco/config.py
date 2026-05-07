"""Application configuration loaded from environment variables.

Uses Pydantic Settings for validated, typed configuration with
automatic .env file loading.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All fields are loaded from environment variables with sensible defaults
    where appropriate.  Secrets are stored as ``SecretStr`` to prevent
    accidental leakage in logs and __repr__.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Gemini ────────────────────────────────────────────────────────────
    gemini_api_key: str = Field(
        ...,
        description="Google Gemini API key (required). Set GEMINI_API_KEY env var.",
    )

    # ── Arize Phoenix Cloud ──────────────────────────────────────────────
    phoenix_api_key: str | None = Field(
        default=None,
        description="Optional Arize Phoenix Cloud API key for trace export.",
    )
    phoenix_project_name: str = Field(
        default="wco-agent",
        description="Phoenix project name under which traces are grouped.",
    )
    phoenix_base_url: str = Field(
        default="https://app.phoenix.arize.com",
        description="Base URL of the Phoenix Cloud instance.",
    )

    # ── CockroachDB ─────────────────────────────────────────────────────
    cockroachdb_username: str = Field(
        default="cubiczan",
        description="CockroachDB username.",
    )
    cockroachdb_password: str | None = Field(
        default=None,
        description="CockroachDB password. Set COCKROACHDB_PASSWORD env var.",
    )
    cockroachdb_host: str = Field(
        default="localhost",
        description="CockroachDB host.",
    )
    cockroachdb_port: int = Field(
        default=26257,
        description="CockroachDB port.",
    )
    cockroachdb_database: str = Field(
        default="wco",
        description="CockroachDB database name.",
    )

    # ── Server ───────────────────────────────────────────────────────────
    port: int = Field(
        default=8000,
        description="Port for the FastAPI server.",
    )

    # ── Computed helpers ─────────────────────────────────────────────────

    @property
    def cockroachdb_connection_string(self) -> str:
        """Return the SQLAlchemy connection URL for CockroachDB."""
        user = self.cockroachdb_username
        password = self.cockroachdb_password or ""
        host = self.cockroachdb_host
        port = self.cockroachdb_port
        database = self.cockroachdb_database
        if password:
            return f"cockroachdb://{user}:{password}@{host}:{port}/{database}?sslmode=require"
        return f"cockroachdb://{user}@{host}:{port}/{database}?sslmode=require"

    @property
    def phoenix_available(self) -> bool:
        """Return ``True`` when a Phoenix API key has been configured."""
        return bool(self.phoenix_api_key)


# Singleton — re-imported throughout the codebase
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached ``Settings`` singleton.

    Creates the singleton on first call.  Subsequent calls return the
    same instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
