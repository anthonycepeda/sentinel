from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    prometheus_url: str = Field(description="Prometheus HTTP API base URL")
    loki_url: str = Field(description="Loki HTTP API base URL")
    target_service: str = Field(description="Name of the microservice being monitored")

    collection_interval_minutes: int = Field(
        default=5, description="How often to pull telemetry from Prometheus and Loki"
    )
    anomaly_window_minutes: int = Field(
        default=30, description="Rolling window size for Z-score anomaly detection"
    )
    anomaly_z_threshold: float = Field(
        default=2.5, description="abs(z) above this flags an anomaly"
    )
    log_spike_multiplier: float = Field(
        default=2.0,
        description="Error count above rolling mean by this factor flags a log spike",
    )
    db_path: str = Field(default="./sentinel.db", description="SQLite database file path")


@lru_cache
def get_settings() -> Settings:
    return Settings()
