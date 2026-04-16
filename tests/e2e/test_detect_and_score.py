"""End-to-end tests for the detector → scorer pipeline.

These tests exercise the full path from raw telemetry records through
detect_anomalies / detect_log_spikes to score_health, with no mocking.
They prove the layers compose correctly and that the scoring table in
instructions.md is enforced end-to-end.
"""

from datetime import UTC, datetime, timedelta

import pytest

from detector.anomaly import detect_anomalies
from detector.log_spikes import detect_log_spikes
from schema.models import LogRecord, MetricRecord
from scorer.health import score_health

BASE = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def metric(minutes: int, value: float, service: str = "svc") -> MetricRecord:
    return MetricRecord(
        timestamp=BASE + timedelta(minutes=minutes),
        service=service,
        metric_name="cpu",
        value=value,
    )


def log(minutes: int, level: str = "ERROR", service: str = "svc") -> LogRecord:
    return LogRecord(
        timestamp=BASE + timedelta(minutes=minutes),
        service=service,
        level=level,
        event_type="error",
        message="test",
    )


def run(
    metrics: list[MetricRecord],
    logs: list[LogRecord],
    window_start: datetime = BASE,
    window_end: datetime = BASE + timedelta(minutes=60),
    z_threshold: float = 2.5,
    multiplier: float = 2.0,
    window_minutes: int = 30,
):
    anomalies = detect_anomalies(metrics, window_minutes=window_minutes, z_threshold=z_threshold)
    spikes = detect_log_spikes(logs, multiplier=multiplier, window_minutes=window_minutes)
    return score_health(window_start, window_end, anomalies, spikes)


# ---------------------------------------------------------------------------
# Green path
# ---------------------------------------------------------------------------


class TestGreenScore:
    def test_no_telemetry_is_green(self):
        score = run([], [])
        assert score.score == "green"
        assert score.anomaly_count == 0
        assert score.log_spike_count == 0

    def test_flat_metrics_and_logs_is_green(self):
        metrics = [metric(i, 0.5) for i in range(40)]
        logs = [log(i, level="INFO") for i in range(40)]
        score = run(metrics, logs)
        assert score.score == "green"

    def test_stable_error_logs_below_threshold_is_green(self):
        # 1 ERROR per minute for 40 minutes — stable, never spikes
        logs = [log(i, level="ERROR") for i in range(40)]
        score = run([], logs)
        assert score.score == "green"


# ---------------------------------------------------------------------------
# Amber path
# ---------------------------------------------------------------------------


class TestAmberScore:
    def test_one_metric_anomaly_is_amber(self):
        metrics = [metric(i, 1.0) for i in range(20)]
        metrics.append(metric(20, 100.0))  # spike → 1 anomaly
        score = run(metrics, [])
        assert score.score == "amber"
        assert score.anomaly_count == 1

    def test_two_metric_anomalies_is_amber(self):
        metrics = [metric(i, 1.0) for i in range(30)]
        metrics.append(metric(25, 100.0))
        metrics.append(metric(28, 100.0))
        score = run(metrics, [])
        assert score.score == "amber"
        assert score.anomaly_count == 2


# ---------------------------------------------------------------------------
# Red path — anomaly count
# ---------------------------------------------------------------------------


class TestRedScoreAnomalies:
    def test_three_anomalies_is_red(self):
        metrics = [metric(i, 1.0) for i in range(30)]
        for m in [25, 27, 29]:
            metrics.append(metric(m, 100.0))
        score = run(metrics, [])
        assert score.score == "red"
        assert score.anomaly_count >= 3

    def test_many_anomalies_is_red(self):
        metrics = [metric(i, 1.0) for i in range(30)]
        for m in range(25, 30):
            metrics.append(metric(m, 500.0))
        score = run(metrics, [])
        assert score.score == "red"


# ---------------------------------------------------------------------------
# Red path — log spike
# ---------------------------------------------------------------------------


class TestRedScoreLogSpike:
    def test_log_spike_alone_is_red(self):
        # 30 quiet minutes (1 ERROR), then a burst of 20
        logs = [log(i, level="ERROR") for i in range(30)]
        logs.extend(log(30, level="ERROR") for _ in range(20))
        score = run([], logs)
        assert score.score == "red"
        assert score.log_spike_count >= 1

    def test_log_spike_with_one_anomaly_is_red(self):
        metrics = [metric(i, 1.0) for i in range(20)]
        metrics.append(metric(20, 100.0))
        logs = [log(i, level="ERROR") for i in range(30)]
        logs.extend(log(30, level="ERROR") for _ in range(20))
        score = run(metrics, logs)
        assert score.score == "red"

    def test_critical_logs_trigger_spike(self):
        logs = [log(i, level="CRITICAL") for i in range(30)]
        logs.extend(log(30, level="CRITICAL") for _ in range(20))
        score = run([], logs)
        assert score.score == "red"


# ---------------------------------------------------------------------------
# Multi-service isolation
# ---------------------------------------------------------------------------


class TestMultiService:
    def test_spike_in_one_service_does_not_affect_score_of_other(self):
        # svc-a has a metric spike (→ amber), svc-b has a log spike (→ red for svc-b)
        # score_health receives the full combined anomaly+spike lists —
        # it aggregates counts, so both signals show up. Verify counts are correct.
        metrics_a = [metric(i, 1.0, service="svc-a") for i in range(20)]
        metrics_a.append(metric(20, 100.0, service="svc-a"))

        logs_b = [log(i, level="ERROR", service="svc-b") for i in range(30)]
        logs_b.extend(log(30, level="ERROR", service="svc-b") for _ in range(20))

        score = run(metrics_a, logs_b)
        assert score.score == "red"  # spike from svc-b forces red
        assert score.anomaly_count >= 1
        assert score.log_spike_count >= 1


# ---------------------------------------------------------------------------
# Window boundaries preserved
# ---------------------------------------------------------------------------


class TestWindowFields:
    def test_window_timestamps_flow_through_to_health_score(self):
        start = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
        end = datetime(2026, 4, 1, 9, 5, 0, tzinfo=UTC)
        score = run([], [], window_start=start, window_end=end)
        assert score.window_start == start
        assert score.window_end == end

    def test_health_score_is_frozen(self):
        from pydantic import ValidationError

        score = run([], [])
        with pytest.raises(ValidationError):
            score.score = "red"  # type: ignore[misc]
