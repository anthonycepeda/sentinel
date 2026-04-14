from datetime import UTC, datetime
from typing import Any, get_args

import httpx

from schema.models import LogLevel, LogRecord

_VALID_LEVELS = set(get_args(LogLevel))


class LokiError(Exception):
    """Raised when a Loki query fails or returns a non-success status."""


def query_range(
    client: httpx.Client,
    *,
    query: str,
    start: datetime,
    end: datetime,
    service: str,
    limit: int = 5000,
) -> list[LogRecord]:
    """Run a Loki `query_range` and normalize the response into LogRecord list.

    `start` and `end` must be timezone-aware UTC datetimes. Results are returned in
    ascending timestamp order regardless of Loki's response direction. Each stream
    must carry `level` and `event_type` labels — normalization happens here, so
    downstream layers never see raw Loki streams.

    Raises LokiError on HTTP failure or non-success Loki status (including HTTP
    400 with an error body).
    """
    _require_utc("start", start)
    _require_utc("end", end)

    params = {
        "query": query,
        "start": _to_nanoseconds(start),
        "end": _to_nanoseconds(end),
        "limit": limit,
        "direction": "forward",
    }
    try:
        response = client.get("/loki/api/v1/query_range", params=params)
    except httpx.HTTPError as e:
        raise LokiError(f"Loki request failed: {e}") from e

    try:
        payload = response.json()
    except ValueError:
        raise LokiError(f"Loki request failed: HTTP {response.status_code}") from None

    if payload.get("status") != "success":
        raise LokiError(
            f"Loki returned {payload.get('status')}: {payload.get('error', 'unknown error')}"
        )

    return _normalize_streams(payload["data"], service)


def _require_utc(name: str, ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() != UTC.utcoffset(ts):
        raise LokiError(f"{name} must be a timezone-aware UTC datetime")


def _to_nanoseconds(ts: datetime) -> str:
    return str(int(ts.timestamp() * 1_000_000_000))


def _normalize_streams(data: dict[str, Any], service: str) -> list[LogRecord]:
    if data.get("resultType") != "streams":
        raise LokiError(f"expected streams result, got {data.get('resultType')}")

    records: list[LogRecord] = []
    for stream in data.get("result", []):
        labels = stream.get("stream", {})
        level = _normalize_level(labels.get("level"))
        event_type = labels.get("event_type")
        if not event_type:
            raise LokiError("stream missing required 'event_type' label")

        for ts_ns, message in stream.get("values", []):
            records.append(
                LogRecord(
                    timestamp=datetime.fromtimestamp(int(ts_ns) / 1_000_000_000, tz=UTC),
                    service=service,
                    level=level,
                    event_type=event_type,
                    message=message,
                )
            )

    records.sort(key=lambda r: r.timestamp)
    return records


def _normalize_level(raw: str | None) -> LogLevel:
    if raw is None:
        raise LokiError("stream missing required 'level' label")
    upper = raw.upper()
    if upper not in _VALID_LEVELS:
        raise LokiError(f"unknown log level {raw!r}")
    return upper  # type: ignore[return-value]
