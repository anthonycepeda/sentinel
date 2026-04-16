from datetime import UTC, datetime, timedelta

from schema.models import MetricRecord


def ts(minutes: int) -> datetime:
    return datetime(2026, 3, 25, 10, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def metric_record(
    minutes: int, value: float, metric: str = "cpu", service: str = "svc"
) -> MetricRecord:
    return MetricRecord(timestamp=ts(minutes), service=service, metric_name=metric, value=value)
