import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from schema.models import LogRecord, MetricRecord

_METRICS_DDL = """
CREATE TABLE IF NOT EXISTS metrics (
    timestamp   TEXT NOT NULL,
    service     TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value       REAL NOT NULL,
    labels      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_service ON metrics(service);
"""

_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS logs (
    timestamp  TEXT NOT NULL,
    service    TEXT NOT NULL,
    level      TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_service ON logs(service);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
"""


@contextmanager
def _connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    with _connect(db_path) as conn:
        conn.executescript(_METRICS_DDL)
        conn.executescript(_LOGS_DDL)


def write_metrics(db_path: str | Path, records: Iterable[MetricRecord]) -> int:
    rows = [
        (r.timestamp.isoformat(), r.service, r.metric_name, r.value, json.dumps(r.labels))
        for r in records
    ]
    if not rows:
        return 0
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO metrics (timestamp, service, metric_name, value, labels) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def write_logs(db_path: str | Path, records: Iterable[LogRecord]) -> int:
    rows = [(r.timestamp.isoformat(), r.service, r.level, r.event_type, r.message) for r in records]
    if not rows:
        return 0
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO logs (timestamp, service, level, event_type, message) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def read_metrics(
    db_path: str | Path,
    from_ts: datetime,
    to_ts: datetime,
    service: str | None = None,
) -> list[MetricRecord]:
    sql = (
        "SELECT timestamp, service, metric_name, value, labels FROM metrics "
        "WHERE timestamp >= ? AND timestamp <= ?"
    )
    params: list[object] = [from_ts.isoformat(), to_ts.isoformat()]
    if service is not None:
        sql += " AND service = ?"
        params.append(service)
    sql += " ORDER BY timestamp ASC"

    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        MetricRecord(
            timestamp=ts,
            service=svc,
            metric_name=name,
            value=val,
            labels=json.loads(labels),
        )
        for ts, svc, name, val, labels in rows
    ]


def read_logs(
    db_path: str | Path,
    from_ts: datetime,
    to_ts: datetime,
    service: str | None = None,
    level: str | None = None,
) -> list[LogRecord]:
    sql = (
        "SELECT timestamp, service, level, event_type, message FROM logs "
        "WHERE timestamp >= ? AND timestamp <= ?"
    )
    params: list[object] = [from_ts.isoformat(), to_ts.isoformat()]
    if service is not None:
        sql += " AND service = ?"
        params.append(service)
    if level is not None:
        sql += " AND level = ?"
        params.append(level)
    sql += " ORDER BY timestamp ASC"

    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        LogRecord(
            timestamp=ts,
            service=svc,
            level=lvl,
            event_type=etype,
            message=msg,
        )
        for ts, svc, lvl, etype, msg in rows
    ]
