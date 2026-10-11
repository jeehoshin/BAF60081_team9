import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = ""
    cors_origins: str = (
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000"
    )
    use_memory: bool | None = None
    app_name: str = "같이 갈래? API"

    # 공공 API 수집 (POST /collect, scripts/collect_activities.py)
    kopis_api_key: str = ""
    tour_api_key: str = ""  # 공공데이터포털 'Decoding' 키 권장 (Encoding 키도 동작)
    collect_token: str = ""  # 비어 있으면 POST /collect를 막는다

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def memory_mode(self) -> bool:
        if self.use_memory is not None:
            return self.use_memory
        # DATABASE_URL이 있으면 DB 모드, 없으면 인메모리 시연 모드
        return not bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    # Allow USE_MEMORY=1/0 from environment explicitly
    raw = os.getenv("USE_MEMORY")
    settings = Settings()
    if raw is not None:
        settings.use_memory = raw.strip().lower() in {"1", "true", "yes", "on"}
    return settings
