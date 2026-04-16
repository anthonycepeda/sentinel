from datetime import UTC

import pytest

from detector.anomaly import _severity, detect_anomalies
from tests.unit.detector.conftest import metric_record, ts


class TestDetectAnomalies:
    def test_empty_input_returns_empty(self):
        assert detect_anomalies([]) == []

    def test_no_anomaly_in_flat_series(self):
        records = [metric_record(i, 0.5) for i in range(10)]
        assert detect_anomalies(records) == []

    def test_detects_spike_above_threshold(self):
        # Build a stable baseline then insert a clear spike
        records = [metric_record(i, 1.0) for i in range(20)]
        records.append(metric_record(20, 100.0))  # massive spike
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        assert len(events) == 1
        assert events[0].metric_name == "cpu"
        assert events[0].value == 100.0
        assert events[0].z_score > 2.5

    def test_detects_dip_below_threshold(self):
        # A sharp dip produces a negative z-score; threshold check is on abs(z)
        records = [metric_record(i, 100.0) for i in range(20)]
        records.append(metric_record(20, 1.0))  # sharp dip
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        assert len(events) == 1
        assert events[0].z_score < -2.5

    def test_only_two_points_in_window_produces_z_score(self):
        # Two points: mean=(1+100)/2=50.5, std≈70.0 → z for 100 ≈ 0.71 (below threshold)
        records = [metric_record(0, 1.0), metric_record(1, 100.0)]
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        assert events == []

    def test_single_point_not_flagged(self):
        assert detect_anomalies([metric_record(0, 999.0)]) == []

    def test_results_sorted_by_timestamp(self):
        records = [metric_record(i, 1.0) for i in range(30)]
        records.append(metric_record(25, 200.0))
        records.append(metric_record(15, 200.0))
        events = detect_anomalies(records, window_minutes=30, z_threshold=2.5)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    def test_independent_groups_per_metric(self):
        # cpu has a spike; memory is flat — only cpu should flag
        cpu = [metric_record(i, 1.0, metric="cpu") for i in range(20)]
        cpu.append(metric_record(20, 100.0, metric="cpu"))
        mem = [metric_record(i, 50.0, metric="memory") for i in range(21)]
        events = detect_anomalies(cpu + mem, window_minutes=30, z_threshold=2.5)
        assert all(e.metric_name == "cpu" for e in events)
        assert len(events) >= 1

    def test_independent_groups_per_service(self):
        # svc-a has spike; svc-b is flat
        a = [metric_record(i, 1.0, service="svc-a") for i in range(20)]
        a.append(metric_record(20, 100.0, service="svc-a"))
        b = [metric_record(i, 50.0, service="svc-b") for i in range(21)]
        events = detect_anomalies(a + b, window_minutes=30, z_threshold=2.5)
        assert all(e.service == "svc-a" for e in events)

    def test_points_outside_window_excluded(self):
        # Old extreme values (t=0..4) fall outside the 30-min rolling window
        # anchored at the recent series (t=60..80). If they leaked into the window,
        # the std would be dominated by 1000.0 values and the spike at t=80 might
        # not register — or extra events would appear. Exactly 1 event expected.
        old = [metric_record(i, 1000.0) for i in range(5)]  # t=0..4 — outside window
        recent = [metric_record(60 + i, 1.0) for i in range(20)]  # t=60..79 — inside window
        spike = metric_record(80, 100.0)
        events = detect_anomalies(old + recent + [spike], window_minutes=30, z_threshold=2.5)
        assert len(events) == 1
        assert events[0].value == 100.0

    def test_severity_bands(self):
        threshold = 2.5
        records = [metric_record(i, 1.0) for i in range(30)]
        records.append(metric_record(30, 50.0))  # large spike → well above threshold*2
        events = detect_anomalies(records, window_minutes=60, z_threshold=threshold)
        assert len(events) >= 1
        assert events[-1].severity in ("medium", "high")

    def test_severity_boundaries(self):
        # _severity bands relative to threshold=2.5 (exclusive boundaries):
        # low:    (2.5, 3.75]
        # medium: (3.75, 5.0]
        # high:   (5.0, ∞)
        assert _severity(2.6, 2.5) == "low"
        assert _severity(3.75, 2.5) == "low"  # boundary is exclusive
        assert _severity(3.76, 2.5) == "medium"
        assert _severity(5.0, 2.5) == "medium"  # boundary is exclusive
        assert _severity(5.01, 2.5) == "high"
        assert _severity(10.0, 2.5) == "high"

    def test_event_fields_match_record(self):
        records = [metric_record(i, 1.0) for i in range(20)]
        records.append(metric_record(20, 200.0))
        events = detect_anomalies(records, z_threshold=2.5)
        assert len(events) == 1
        e = events[0]
        assert e.service == "svc"
        assert e.metric_name == "cpu"
        assert e.value == 200.0
        assert e.z_threshold == 2.5
        assert e.timestamp == ts(20)
        assert e.timestamp.tzinfo is UTC

    def test_z_threshold_stored_on_event(self):
        records = [metric_record(i, 1.0) for i in range(20)]
        records.append(metric_record(20, 100.0))
        for threshold in [1.0, 2.5, 3.0]:
            events = detect_anomalies(records, z_threshold=threshold)
            assert all(e.z_threshold == threshold for e in events)

    @pytest.mark.parametrize("threshold", [1.0, 2.5, 3.0])
    def test_custom_threshold_respected(self, threshold: float):
        records = [metric_record(i, 1.0) for i in range(20)]
        records.append(metric_record(20, 100.0))
        events = detect_anomalies(records, z_threshold=threshold)
        # z_score stored at full precision — no rounding that could cause abs(z) == threshold
        assert all(abs(e.z_score) > threshold for e in events)
