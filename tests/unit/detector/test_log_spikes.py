from datetime import UTC

from detector.log_spikes import _spike_severity, detect_log_spikes
from schema.models import LogRecord
from tests.unit.detector.conftest import ts


def log_record(
    minutes: int,
    level: str = "ERROR",
    service: str = "svc",
    event_type: str = "error",
) -> LogRecord:
    return LogRecord(
        timestamp=ts(minutes),
        service=service,
        level=level,
        event_type=event_type,
        message="test",
    )


def spike_at(minute: int, count: int, service: str = "svc") -> list[LogRecord]:
    """Return `count` ERROR records all within the same 1-minute bucket."""
    return [log_record(minutes=minute, service=service) for _ in range(count)]


def baseline_minutes(
    start: int, end: int, count_per_min: int = 1, service: str = "svc"
) -> list[LogRecord]:
    """Return a stable baseline: `count_per_min` ERROR records per minute."""
    records = []
    for m in range(start, end):
        records.extend(spike_at(m, count_per_min, service=service))
    return records


class TestDetectLogSpikes:
    def test_empty_input_returns_empty(self):
        assert detect_log_spikes([]) == []

    def test_no_error_records_returns_empty(self):
        records = [log_record(i, level=lvl) for i, lvl in enumerate(["DEBUG", "INFO", "WARNING"])]
        assert detect_log_spikes(records) == []

    def test_flat_series_no_spike(self):
        records = baseline_minutes(0, 40, count_per_min=5)
        assert detect_log_spikes(records) == []

    def test_detects_spike_above_threshold(self):
        # 30 quiet minutes (1 ERROR each) then a bucket with 20 errors
        records = baseline_minutes(0, 30)
        records.extend(spike_at(30, 20))
        events = detect_log_spikes(records, multiplier=2.0, window_minutes=30)
        assert len(events) == 1
        assert events[0].count == 20

    def test_spike_not_flagged_without_sufficient_baseline(self):
        # Only 1 prior bucket — baseline can't be established (min_periods=2)
        records = spike_at(0, 1) + spike_at(1, 50)
        events = detect_log_spikes(records, multiplier=2.0, window_minutes=30)
        assert events == []

    def test_single_bucket_not_flagged(self):
        assert detect_log_spikes(spike_at(0, 999)) == []

    def test_only_error_and_critical_counted(self):
        # Lots of INFO/WARNING/DEBUG won't trigger anything
        noise = [log_record(i, level="INFO") for i in range(30)]
        noise += [log_record(i, level="WARNING") for i in range(30)]
        noise += [log_record(i, level="DEBUG") for i in range(30)]
        assert detect_log_spikes(noise, multiplier=2.0) == []

    def test_critical_level_counted(self):
        # CRITICAL counts the same as ERROR
        baseline = [
            LogRecord(
                timestamp=ts(i),
                service="svc",
                level="CRITICAL",
                event_type="crash",
                message="x",
            )
            for i in range(30)
        ]
        baseline.extend(
            LogRecord(
                timestamp=ts(30),
                service="svc",
                level="CRITICAL",
                event_type="crash",
                message="x",
            )
            for _ in range(20)
        )
        events = detect_log_spikes(baseline, multiplier=2.0, window_minutes=30)
        assert len(events) == 1

    def test_results_sorted_by_timestamp(self):
        records = baseline_minutes(0, 30)
        records.extend(spike_at(35, 20))
        records.extend(spike_at(25, 20))
        events = detect_log_spikes(records, multiplier=2.0, window_minutes=30)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    def test_independent_groups_per_service(self):
        # svc-a has a spike; svc-b is flat
        a = baseline_minutes(0, 30, service="svc-a")
        a.extend(spike_at(30, 20, service="svc-a"))
        b = baseline_minutes(0, 31, count_per_min=5, service="svc-b")
        events = detect_log_spikes(a + b, multiplier=2.0, window_minutes=30)
        assert all(e.service == "svc-a" for e in events)
        assert len(events) >= 1

    def test_event_fields_match_input(self):
        records = baseline_minutes(0, 30)
        records.extend(spike_at(30, 20))
        events = detect_log_spikes(records, multiplier=2.0, window_minutes=30)
        assert len(events) == 1
        e = events[0]
        assert e.service == "svc"
        assert e.count == 20
        assert e.baseline > 0
        assert e.timestamp.tzinfo is UTC

    def test_baseline_stored_on_event(self):
        records = baseline_minutes(0, 30, count_per_min=3)
        records.extend(spike_at(30, 30))
        events = detect_log_spikes(records, multiplier=2.0, window_minutes=30)
        assert len(events) == 1
        # Baseline should be close to 3.0 (the stable per-minute count)
        assert 1.0 < events[0].baseline < 10.0

    def test_severity_bands(self):
        # multiplier=2.0 → high: ratio>4.0, medium: ratio>3.0, low: else
        assert _spike_severity(5, 1.0, 2.0) == "high"  # ratio=5 > 4.0
        assert _spike_severity(4, 1.0, 2.0) == "medium"  # ratio=4 == 4.0, not strictly >
        assert _spike_severity(3, 1.0, 2.0) == "low"  # ratio=3 == 3.0, not strictly >
        assert _spike_severity(2, 1.0, 2.0) == "low"  # ratio=2 < 3.0

    def test_severity_boundaries_explicit(self):
        # multiplier=2.0 → low: ratio in (2.0, 3.0], medium: (3.0, 4.0], high: >4.0
        assert _spike_severity(21, 10.0, 2.0) == "low"  # ratio=2.1
        assert _spike_severity(30, 10.0, 2.0) == "low"  # ratio=3.0 (not strictly >3.0)
        assert _spike_severity(31, 10.0, 2.0) == "medium"  # ratio=3.1
        assert _spike_severity(40, 10.0, 2.0) == "medium"  # ratio=4.0 (not strictly >4.0)
        assert _spike_severity(41, 10.0, 2.0) == "high"  # ratio=4.1
