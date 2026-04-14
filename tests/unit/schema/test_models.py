from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from schema.models import (
    AnomalyEvent,
    HealthScore,
    LogRecord,
    LogSpikeEvent,
    MetricRecord,
)

TS = "2026-03-25T10:00:00Z"
TS_DT = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)


class TestMetricRecord:
    def test_happy_path(self):
        m = MetricRecord(
            timestamp=TS,
            service="payments-api",
            metric_name="http_request_duration_seconds",
            value=0.342,
            labels={"route": "/pay"},
        )
        assert m.timestamp == TS_DT
        assert m.labels == {"route": "/pay"}

    def test_round_trip(self):
        m = MetricRecord(timestamp=TS, service="s", metric_name="n", value=1.0)
        assert MetricRecord.model_validate(m.model_dump()) == m

    def test_labels_default_empty(self):
        m = MetricRecord(timestamp=TS, service="s", metric_name="n", value=1.0)
        assert m.labels == {}

    def test_naive_datetime_is_tagged_utc(self):
        m = MetricRecord(
            timestamp=datetime(2026, 3, 25, 10, 0, 0),
            service="s",
            metric_name="n",
            value=1.0,
        )
        assert m.timestamp.tzinfo is UTC

    def test_non_utc_tz_rejected(self):
        paris = timezone(timedelta(hours=1))
        with pytest.raises(ValidationError):
            MetricRecord(
                timestamp=datetime(2026, 3, 25, 10, 0, 0, tzinfo=paris),
                service="s",
                metric_name="n",
                value=1.0,
            )


class TestLogRecord:
    def test_happy_path(self):
        log = LogRecord(
            timestamp=TS, service="s", level="ERROR", event_type="timeout", message="..."
        )
        assert log.level == "ERROR"

    def test_round_trip(self):
        log = LogRecord(timestamp=TS, service="s", level="INFO", event_type="request", message="ok")
        assert LogRecord.model_validate(log.model_dump()) == log

    def test_unknown_level_rejected(self):
        with pytest.raises(ValidationError):
            LogRecord(timestamp=TS, service="s", level="FATAL", event_type="x", message="y")


class TestAnomalyEvent:
    def test_happy_path(self):
        e = AnomalyEvent(
            timestamp=TS,
            service="s",
            metric_name="cpu",
            value=0.99,
            z_score=3.1,
            severity="high",
        )
        assert e.severity == "high"

    def test_round_trip(self):
        e = AnomalyEvent(
            timestamp=TS,
            service="s",
            metric_name="cpu",
            value=0.5,
            z_score=2.6,
            severity="medium",
        )
        assert AnomalyEvent.model_validate(e.model_dump()) == e

    def test_unknown_severity_rejected(self):
        with pytest.raises(ValidationError):
            AnomalyEvent(
                timestamp=TS,
                service="s",
                metric_name="cpu",
                value=0.5,
                z_score=2.6,
                severity="critical",
            )


class TestLogSpikeEvent:
    def test_happy_path(self):
        e = LogSpikeEvent(timestamp=TS, service="s", count=42, baseline=10.0, severity="medium")
        assert e.count == 42

    def test_round_trip(self):
        e = LogSpikeEvent(timestamp=TS, service="s", count=5, baseline=2.0, severity="low")
        assert LogSpikeEvent.model_validate(e.model_dump()) == e


class TestHealthScore:
    def test_happy_path(self):
        h = HealthScore(
            window_start=TS,
            window_end="2026-03-25T10:05:00Z",
            score="amber",
            anomaly_count=2,
            log_spike_count=0,
        )
        assert h.score == "amber"

    def test_round_trip(self):
        h = HealthScore(
            window_start=TS,
            window_end="2026-03-25T10:05:00Z",
            score="green",
            anomaly_count=0,
            log_spike_count=0,
        )
        assert HealthScore.model_validate(h.model_dump()) == h

    def test_unknown_score_rejected(self):
        with pytest.raises(ValidationError):
            HealthScore(
                window_start=TS,
                window_end="2026-03-25T10:05:00Z",
                score="black",
                anomaly_count=0,
                log_spike_count=0,
            )

    def test_both_timestamps_enforce_utc(self):
        paris = timezone(timedelta(hours=1))
        with pytest.raises(ValidationError):
            HealthScore(
                window_start=datetime(2026, 3, 25, 10, 0, 0, tzinfo=paris),
                window_end="2026-03-25T10:05:00Z",
                score="green",
                anomaly_count=0,
                log_spike_count=0,
            )
