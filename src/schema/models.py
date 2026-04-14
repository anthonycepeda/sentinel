from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Severity = Literal["low", "medium", "high"]
HealthColor = Literal["green", "amber", "red"]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class MetricRecord(_FrozenModel):
    timestamp: datetime
    service: str
    metric_name: str
    value: float
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)


class LogRecord(_FrozenModel):
    timestamp: datetime
    service: str
    level: LogLevel
    event_type: str
    message: str

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)


class AnomalyEvent(_FrozenModel):
    timestamp: datetime
    service: str
    metric_name: str
    value: float
    z_score: float
    severity: Severity

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)


class LogSpikeEvent(_FrozenModel):
    timestamp: datetime
    service: str
    count: int
    baseline: float
    severity: Severity

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)


class HealthScore(_FrozenModel):
    window_start: datetime
    window_end: datetime
    score: HealthColor
    anomaly_count: int
    log_spike_count: int

    @field_validator("window_start", "window_end")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _ensure_utc(v)
