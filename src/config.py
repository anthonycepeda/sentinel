from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    prometheus_url: str
    loki_url: str
    target_service: str

    collection_interval_minutes: int = 5
    anomaly_window_minutes: int = 30
    anomaly_z_threshold: float = 2.5
    log_spike_multiplier: float = 2.0
    db_path: str = "./sentinel.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
