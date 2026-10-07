from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "fastapi-boilerplate"
    app_mode: Literal["mock", "live"] = "mock"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    initialize_database: bool = False
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-haiku-4-5"
    anthropic_max_tokens: int = Field(default=8192, ge=1, le=64000)
    anthropic_timeout_seconds: float = Field(default=120, gt=0, le=600)
    enable_prompt_caching: bool = True
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_tracing_enabled: bool = True
    secret_key: SecretStr = SecretStr(DEFAULT_SECRET_KEY)

    @model_validator(mode="after")
    def _require_secret_in_live(self) -> Self:
        if self.is_live and self.secret_key.get_secret_value() in ("", DEFAULT_SECRET_KEY):
            raise ValueError("APP_MODE=live에서는 SECRET_KEY를 기본값이 아닌 값으로 설정해야 합니다")
        return self

    @property
    def is_live(self) -> bool:
        return self.app_mode == "live"


@lru_cache
def get_settings() -> Settings:
    return Settings()
