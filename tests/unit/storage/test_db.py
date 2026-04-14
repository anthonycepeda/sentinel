from datetime import UTC, datetime
from pathlib import Path

import pytest

from schema.models import LogRecord, MetricRecord
from storage.db import init_db, read_logs, read_metrics, write_logs, write_metrics


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    return path


def _ts(minute: int) -> datetime:
    return datetime(2026, 4, 14, 10, minute, 0, tzinfo=UTC)


class TestMetrics:
    def test_round_trip(self, db: Path):
        records = [
            MetricRecord(
                timestamp=_ts(0),
                service="payments-api",
                metric_name="cpu",
                value=0.42,
                labels={"region": "eu"},
            ),
            MetricRecord(
                timestamp=_ts(5),
                service="payments-api",
                metric_name="cpu",
                value=0.51,
            ),
        ]
        assert write_metrics(db, records) == 2
        got = read_metrics(db, _ts(0), _ts(10))
        assert got == records

    def test_filter_by_service(self, db: Path):
        write_metrics(
            db,
            [
                MetricRecord(timestamp=_ts(0), service="a", metric_name="cpu", value=1.0),
                MetricRecord(timestamp=_ts(1), service="b", metric_name="cpu", value=2.0),
            ],
        )
        got = read_metrics(db, _ts(0), _ts(10), service="b")
        assert len(got) == 1
        assert got[0].service == "b"

    def test_filter_by_time_range(self, db: Path):
        write_metrics(
            db,
            [
                MetricRecord(timestamp=_ts(0), service="a", metric_name="cpu", value=1.0),
                MetricRecord(timestamp=_ts(5), service="a", metric_name="cpu", value=2.0),
                MetricRecord(timestamp=_ts(20), service="a", metric_name="cpu", value=3.0),
            ],
        )
        got = read_metrics(db, _ts(1), _ts(10))
        assert [r.value for r in got] == [2.0]

    def test_results_ordered_by_timestamp(self, db: Path):
        write_metrics(
            db,
            [
                MetricRecord(timestamp=_ts(5), service="a", metric_name="cpu", value=2.0),
                MetricRecord(timestamp=_ts(0), service="a", metric_name="cpu", value=1.0),
                MetricRecord(timestamp=_ts(2), service="a", metric_name="cpu", value=1.5),
            ],
        )
        got = read_metrics(db, _ts(0), _ts(10))
        assert [r.value for r in got] == [1.0, 1.5, 2.0]

    def test_empty_write_returns_zero(self, db: Path):
        assert write_metrics(db, []) == 0

    def test_empty_db_returns_empty_list(self, db: Path):
        assert read_metrics(db, _ts(0), _ts(10)) == []


class TestLogs:
    def test_round_trip(self, db: Path):
        records = [
            LogRecord(
                timestamp=_ts(0),
                service="payments-api",
                level="ERROR",
                event_type="timeout",
                message="upstream timed out",
            ),
            LogRecord(
                timestamp=_ts(1),
                service="payments-api",
                level="INFO",
                event_type="request",
                message="ok",
            ),
        ]
        assert write_logs(db, records) == 2
        got = read_logs(db, _ts(0), _ts(10))
        assert got == records

    def test_filter_by_level(self, db: Path):
        write_logs(
            db,
            [
                LogRecord(
                    timestamp=_ts(0), service="a", level="ERROR", event_type="x", message="1"
                ),
                LogRecord(timestamp=_ts(1), service="a", level="INFO", event_type="x", message="2"),
                LogRecord(
                    timestamp=_ts(2), service="a", level="ERROR", event_type="x", message="3"
                ),
            ],
        )
        got = read_logs(db, _ts(0), _ts(10), level="ERROR")
        assert [r.message for r in got] == ["1", "3"]

    def test_filter_by_service_and_level(self, db: Path):
        write_logs(
            db,
            [
                LogRecord(
                    timestamp=_ts(0), service="a", level="ERROR", event_type="x", message="1"
                ),
                LogRecord(
                    timestamp=_ts(1), service="b", level="ERROR", event_type="x", message="2"
                ),
                LogRecord(timestamp=_ts(2), service="a", level="INFO", event_type="x", message="3"),
            ],
        )
        got = read_logs(db, _ts(0), _ts(10), service="a", level="ERROR")
        assert [r.message for r in got] == ["1"]

    def test_empty_write_returns_zero(self, db: Path):
        assert write_logs(db, []) == 0


class TestInitDb:
    def test_idempotent(self, tmp_path: Path):
        path = tmp_path / "x.db"
        init_db(path)
        init_db(path)  # second call must not raise
        write_metrics(
            path, [MetricRecord(timestamp=_ts(0), service="a", metric_name="c", value=1.0)]
        )
        assert len(read_metrics(path, _ts(0), _ts(10))) == 1
