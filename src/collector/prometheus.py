from datetime import UTC, datetime
from typing import Any

import httpx

from schema.models import MetricRecord


class PrometheusError(Exception):
    """Raised when a Prometheus query fails or returns a non-success status."""


def query_range(
    client: httpx.Client,
    *,
    query: str,
    start: datetime,
    end: datetime,
    step: str,
    service: str,
) -> list[MetricRecord]:
    """Run a Prometheus `query_range` and normalize the response into MetricRecord list.

    `step` is a Prometheus duration string (e.g. "60s", "5m"). `start` and `end` must
    be timezone-aware UTC datetimes. Raises PrometheusError on HTTP failure or
    non-success Prometheus status (including HTTP 400 with an error body).
    """
    _require_utc("start", start)
    _require_utc("end", end)

    params = {
        "query": query,
        "start": start.timestamp(),
        "end": end.timestamp(),
        "step": step,
    }
    try:
        response = client.get("/api/v1/query_range", params=params)
    except httpx.HTTPError as e:
        raise PrometheusError(f"Prometheus request failed: {e}") from e

    # Prometheus returns a JSON error body (with status=error) for HTTP 400/422 on bad
    # queries. Parse first, fall back to HTTP status if body isn't JSON.
    try:
        payload = response.json()
    except ValueError:
        raise PrometheusError(f"Prometheus request failed: HTTP {response.status_code}") from None

    if payload.get("status") != "success":
        raise PrometheusError(
            f"Prometheus returned {payload.get('status')}: {payload.get('error', 'unknown error')}"
        )

    return _normalize_matrix(payload["data"], service)


def _require_utc(name: str, ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() != UTC.utcoffset(ts):
        raise PrometheusError(f"{name} must be a timezone-aware UTC datetime")


def _normalize_matrix(data: dict[str, Any], service: str) -> list[MetricRecord]:
    if data.get("resultType") != "matrix":
        raise PrometheusError(f"expected matrix result, got {data.get('resultType')}")

    records: list[MetricRecord] = []
    for series in data.get("result", []):
        metric = series.get("metric", {})
        metric_name = metric.get("__name__")
        if not metric_name:
            raise PrometheusError("series missing __name__ label")

        base_labels = {k: v for k, v in metric.items() if k != "__name__"}
        for ts, value in series.get("values", []):
            records.append(
                MetricRecord(
                    timestamp=datetime.fromtimestamp(float(ts), tz=UTC),
                    service=service,
                    metric_name=metric_name,
                    value=float(value),
                    labels=dict(base_labels),
                )
            )
    return records
