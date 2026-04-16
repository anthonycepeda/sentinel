from datetime import UTC, datetime, timedelta

import pytest

from detector.anomaly import detect_anomalies
from schema.models import MetricRecord


def _ts(minutes: int) -> datetime:
    return datetime(2026, 3, 25, 10, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _record(minutes: int, value: float, metric: str = "cpu", service: str = "svc") -> MetricRecord:
    return MetricRecord(timestamp=_ts(minutes), service=service, metric_name=metric, value=value)


class TestDetectAnomalies:
    def test_empty_input_returns_empty(self):
        assert detect_anomalies([]) == []

    def test_no_anomaly_in_flat_series(self):
        records = [_record(i, 0.5) for i in range(10)]
        assert detect_anomalies(records) == []

    def test_detects_spike_above_threshold(self):
        # Build a stable baseline then insert a clear spike
        records = [_record(i, 1.0) for i in range(20)]
        records.append(_record(20, 100.0))  # massive spike
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        assert len(events) == 1
        assert events[0].metric_name == "cpu"
        assert events[0].value == 100.0
        assert events[0].z_score > 2.5

    def test_detects_dip_below_threshold(self):
        records = [_record(i, 100.0) for i in range(20)]
        records.append(_record(20, 1.0))  # sharp dip
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        assert len(events) == 1
        assert events[0].z_score < -2.5

    def test_only_two_points_in_window_produces_z_score(self):
        # Two points: mean=(1+100)/2=50.5, std≈70.0 → z for 100 ≈ 0.7 (no flag)
        # With very small threshold it would flag — but natural pair won't exceed 2.5
        records = [_record(0, 1.0), _record(1, 100.0)]
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        # z = (100 - 50.5) / 70.0 ≈ 0.71 — below threshold, no event expected
        assert events == []

    def test_single_point_not_flagged(self):
        assert detect_anomalies([_record(0, 999.0)]) == []

    def test_results_sorted_by_timestamp(self):
        # Two spikes at different times
        records = [_record(i, 1.0) for i in range(30)]
        records.append(_record(25, 200.0))
        records.append(_record(15, 200.0))
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    def test_independent_groups_per_metric(self):
        # cpu has a spike; memory is flat — only cpu should flag
        cpu = [_record(i, 1.0, metric="cpu") for i in range(20)]
        cpu.append(_record(20, 100.0, metric="cpu"))
        mem = [_record(i, 50.0, metric="memory") for i in range(21)]
        events = detect_anomalies(cpu + mem, window_minutes=30, z_threshold=2.5)
        assert all(e.metric_name == "cpu" for e in events)
        assert len(events) >= 1

    def test_independent_groups_per_service(self):
        # svc-a has spike; svc-b is flat
        a = [_record(i, 1.0, service="svc-a") for i in range(20)]
        a.append(_record(20, 100.0, service="svc-a"))
        b = [_record(i, 50.0, service="svc-b") for i in range(21)]
        events = detect_anomalies(a + b, window_minutes=30, z_threshold=2.5)
        assert all(e.service == "svc-a" for e in events)

    def test_points_outside_window_excluded(self):
        # Baseline 60 minutes ago, then flat recent series + spike
        old = [_record(i, 1000.0) for i in range(5)]  # t=0..4 — outside 30 min window
        recent = [_record(60 + i, 1.0) for i in range(20)]  # t=60..79 — inside window
        spike = _record(80, 100.0)
        events = detect_anomalies(old + recent + [spike], window_minutes=30, z_threshold=2.5)
        # Old extreme values outside the window should not inflate std for the spike
        assert len(events) >= 1
        assert events[-1].value == 100.0

    def test_severity_bands(self):
        threshold = 2.5
        # Build a series where we can engineer a known z-score
        # Use z > threshold*2 (>=5.0) for high; z > threshold*1.5 (>=3.75) for medium
        records = [_record(i, 1.0) for i in range(30)]
        records.append(_record(30, 50.0))  # large spike → high
        events = detect_anomalies(records, window_minutes=60, z_threshold=threshold)
        assert len(events) >= 1
        spike_event = events[-1]
        # abs(z) at this scale is well above threshold*2
        assert spike_event.severity in ("medium", "high")

    def test_event_fields_match_record(self):
        records = [_record(i, 1.0) for i in range(20)]
        records.append(_record(20, 200.0))
        events = detect_anomalies(records)
        assert len(events) == 1
        e = events[0]
        assert e.service == "svc"
        assert e.metric_name == "cpu"
        assert e.value == 200.0
        assert e.timestamp == _ts(20)
        assert e.timestamp.tzinfo is UTC

    @pytest.mark.parametrize("threshold", [1.0, 2.5, 3.0])
    def test_custom_threshold_respected(self, threshold: float):
        records = [_record(i, 1.0) for i in range(20)]
        records.append(_record(20, 100.0))
        events = detect_anomalies(records, z_threshold=threshold)
        assert all(abs(e.z_score) > threshold for e in events)
