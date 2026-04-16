from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from schema.models import AnomalyEvent, HealthScore, LogSpikeEvent
from scorer.health import _compute_score, score_health

WINDOW_START = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 3, 25, 10, 5, 0, tzinfo=UTC)
TS = datetime(2026, 3, 25, 10, 1, 0, tzinfo=UTC)


def make_anomaly(n: int = 1) -> list[AnomalyEvent]:
    return [
        AnomalyEvent(
            timestamp=TS + timedelta(minutes=i),
            service="svc",
            metric_name="cpu",
            value=float(99 + i),
            z_score=3.0 + i,
            z_threshold=2.5,
            severity="high",
        )
        for i in range(n)
    ]


def make_spike(n: int = 1) -> list[LogSpikeEvent]:
    return [
        LogSpikeEvent(
            timestamp=TS + timedelta(minutes=i),
            service="svc",
            count=20,
            baseline=2.0,
            severity="high",
        )
        for i in range(n)
    ]


class TestScoreHealth:
    def test_green_no_events(self):
        h = score_health(WINDOW_START, WINDOW_END, [], [])
        assert h.score == "green"
        assert h.anomaly_count == 0
        assert h.log_spike_count == 0

    def test_amber_one_anomaly_no_spike(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(1), [])
        assert h.score == "amber"

    def test_amber_two_anomalies_no_spike(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(2), [])
        assert h.score == "amber"

    def test_red_three_anomalies_no_spike(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(3), [])
        assert h.score == "red"

    def test_red_many_anomalies(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(10), [])
        assert h.score == "red"

    def test_red_one_log_spike_no_anomaly(self):
        h = score_health(WINDOW_START, WINDOW_END, [], make_spike(1))
        assert h.score == "red"

    def test_red_spike_overrides_low_anomaly_count(self):
        # Even 1 anomaly + 1 spike → red (spike dominates)
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(1), make_spike(1))
        assert h.score == "red"

    def test_red_two_anomalies_plus_spike(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(2), make_spike(1))
        assert h.score == "red"

    def test_counts_stored_accurately(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(2), make_spike(3))
        assert h.anomaly_count == 2
        assert h.log_spike_count == 3

    def test_window_timestamps_preserved(self):
        h = score_health(WINDOW_START, WINDOW_END, [], [])
        assert h.window_start == WINDOW_START
        assert h.window_end == WINDOW_END

    def test_round_trip(self):
        h = score_health(WINDOW_START, WINDOW_END, make_anomaly(1), [])
        assert HealthScore.model_validate(h.model_dump()) == h

    def test_naive_window_start_coerced_to_utc(self):
        naive_start = datetime(2026, 3, 25, 10, 0, 0)
        h = score_health(naive_start, WINDOW_END, [], [])
        assert h.window_start.tzinfo is UTC

    def test_non_utc_window_start_rejected(self):
        from datetime import timezone

        paris = timezone(timedelta(hours=1))
        with pytest.raises(ValidationError):
            score_health(
                datetime(2026, 3, 25, 10, 0, 0, tzinfo=paris),
                WINDOW_END,
                [],
                [],
            )


class TestComputeScore:
    @pytest.mark.parametrize(
        "anomaly_count,spike_count,expected",
        [
            (0, 0, "green"),
            (1, 0, "amber"),
            (2, 0, "amber"),
            (3, 0, "red"),
            (4, 0, "red"),
            (0, 1, "red"),
            (1, 1, "red"),
            (2, 1, "red"),
            (3, 1, "red"),
        ],
    )
    def test_scoring_matrix(self, anomaly_count: int, spike_count: int, expected: str):
        assert _compute_score(anomaly_count, spike_count) == expected
