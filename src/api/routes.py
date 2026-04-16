from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from collector import loki, prometheus
from config import Settings, get_settings
from detector.anomaly import detect_anomalies
from detector.log_spikes import detect_log_spikes
from schema.models import AnomalyEvent, HealthScore, LogSpikeEvent
from scorer.health import score_health
from storage.db import init_db, read_logs, read_metrics, write_logs, write_metrics

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/anomalies")
def get_anomalies(
    settings: SettingsDep,
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
) -> list[AnomalyEvent]:
    metrics = read_metrics(settings.db_path, from_ts, to_ts, settings.target_service)
    return detect_anomalies(
        metrics,
        window_minutes=settings.anomaly_window_minutes,
        z_threshold=settings.anomaly_z_threshold,
    )


@router.get("/score")
def get_score(
    settings: SettingsDep,
    from_ts: Annotated[datetime, Query(alias="from")],
    to_ts: Annotated[datetime, Query(alias="to")],
) -> HealthScore:
    metrics = read_metrics(settings.db_path, from_ts, to_ts, settings.target_service)
    logs = read_logs(settings.db_path, from_ts, to_ts, settings.target_service)
    anomalies = detect_anomalies(
        metrics,
        window_minutes=settings.anomaly_window_minutes,
        z_threshold=settings.anomaly_z_threshold,
    )
    spikes: list[LogSpikeEvent] = detect_log_spikes(
        logs,
        multiplier=settings.log_spike_multiplier,
        window_minutes=settings.anomaly_window_minutes,
    )
    return score_health(from_ts, to_ts, anomalies, spikes)


@router.post("/collect")
def collect(settings: SettingsDep) -> dict[str, int]:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=settings.collection_interval_minutes)
    step = f"{settings.collection_interval_minutes}m"
    svc = settings.target_service

    # Prometheus and Loki use different base URLs — separate clients required
    with httpx.Client(base_url=settings.prometheus_url) as prom_client:
        metrics = prometheus.query_range(
            prom_client,
            query=f'{{job="{svc}"}}',
            start=start,
            end=now,
            step=step,
            service=svc,
        )

    with httpx.Client(base_url=settings.loki_url) as loki_client:
        logs = loki.query_range(
            loki_client,
            query=f'{{service="{svc}"}}',
            start=start,
            end=now,
            service=svc,
        )

    init_db(settings.db_path)
    return {
        "metrics_written": write_metrics(settings.db_path, metrics),
        "logs_written": write_logs(settings.db_path, logs),
    }
