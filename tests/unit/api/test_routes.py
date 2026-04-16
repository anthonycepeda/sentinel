from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from config import Settings, get_settings
from schema.models import AnomalyEvent, HealthScore, LogSpikeEvent

FROM_STR = "2026-03-25T10:00:00Z"
TO_STR = "2026-03-25T10:05:00Z"
FROM_DT = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)
TO_DT = datetime(2026, 3, 25, 10, 5, 0, tzinfo=UTC)

TEST_SETTINGS = Settings(
    prometheus_url="http://prom:9090",
    loki_url="http://loki:3100",
    target_service="svc",
    db_path=":memory:",
)


@pytest.fixture(autouse=True)
def override_settings():
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


class TestHealth:
    def test_returns_ok(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestGetAnomalies:
    def test_returns_empty_list_when_no_data(self, client: TestClient):
        with (
            patch("api.routes.read_metrics", return_value=[]),
            patch("api.routes.detect_anomalies", return_value=[]) as mock_detect,
        ):
            r = client.get(f"/anomalies?from={FROM_STR}&to={TO_STR}")
        assert r.status_code == 200
        assert r.json() == []
        mock_detect.assert_called_once()

    def test_returns_anomaly_events(self, client: TestClient):
        event = AnomalyEvent(
            timestamp=FROM_DT,
            service="svc",
            metric_name="cpu",
            value=0.99,
            z_score=3.1,
            z_threshold=2.5,
            severity="high",
        )
        with (
            patch("api.routes.read_metrics", return_value=[]),
            patch("api.routes.detect_anomalies", return_value=[event]),
        ):
            r = client.get(f"/anomalies?from={FROM_STR}&to={TO_STR}")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["metric_name"] == "cpu"
        assert data[0]["severity"] == "high"

    def test_passes_settings_to_detector(self, client: TestClient):
        with (
            patch("api.routes.read_metrics", return_value=[]) as mock_read,
            patch("api.routes.detect_anomalies", return_value=[]) as mock_detect,
        ):
            client.get(f"/anomalies?from={FROM_STR}&to={TO_STR}")

        mock_read.assert_called_once_with(":memory:", FROM_DT, TO_DT, "svc")
        _, kwargs = mock_detect.call_args
        assert kwargs["z_threshold"] == TEST_SETTINGS.anomaly_z_threshold
        assert kwargs["window_minutes"] == TEST_SETTINGS.anomaly_window_minutes

    def test_missing_from_returns_422(self, client: TestClient):
        r = client.get(f"/anomalies?to={TO_STR}")
        assert r.status_code == 422

    def test_missing_to_returns_422(self, client: TestClient):
        r = client.get(f"/anomalies?from={FROM_STR}")
        assert r.status_code == 422

    def test_invalid_datetime_returns_422(self, client: TestClient):
        r = client.get("/anomalies?from=not-a-date&to=also-not-a-date")
        assert r.status_code == 422


class TestGetScore:
    def _green_score(self) -> HealthScore:
        return HealthScore(
            window_start=FROM_DT,
            window_end=TO_DT,
            score="green",
            anomaly_count=0,
            log_spike_count=0,
        )

    def test_returns_health_score(self, client: TestClient):
        with (
            patch("api.routes.read_metrics", return_value=[]),
            patch("api.routes.read_logs", return_value=[]),
            patch("api.routes.detect_anomalies", return_value=[]),
            patch("api.routes.detect_log_spikes", return_value=[]),
            patch("api.routes.score_health", return_value=self._green_score()),
        ):
            r = client.get(f"/score?from={FROM_STR}&to={TO_STR}")
        assert r.status_code == 200
        body = r.json()
        assert body["score"] == "green"
        assert body["anomaly_count"] == 0
        assert body["log_spike_count"] == 0

    def test_passes_window_to_scorer(self, client: TestClient):
        with (
            patch("api.routes.read_metrics", return_value=[]),
            patch("api.routes.read_logs", return_value=[]),
            patch("api.routes.detect_anomalies", return_value=[]),
            patch("api.routes.detect_log_spikes", return_value=[]),
            patch("api.routes.score_health", return_value=self._green_score()) as mock_score,
        ):
            client.get(f"/score?from={FROM_STR}&to={TO_STR}")
        args = mock_score.call_args[0]
        assert args[0] == FROM_DT
        assert args[1] == TO_DT

    def test_missing_params_returns_422(self, client: TestClient):
        r = client.get("/score")
        assert r.status_code == 422

    def test_red_score_serialised(self, client: TestClient):
        red = HealthScore(
            window_start=FROM_DT,
            window_end=TO_DT,
            score="red",
            anomaly_count=5,
            log_spike_count=2,
        )
        spike = LogSpikeEvent(
            timestamp=FROM_DT, service="svc", count=10, baseline=2.0, severity="high"
        )
        with (
            patch("api.routes.read_metrics", return_value=[]),
            patch("api.routes.read_logs", return_value=[]),
            patch("api.routes.detect_anomalies", return_value=[]),
            patch("api.routes.detect_log_spikes", return_value=[spike]),
            patch("api.routes.score_health", return_value=red),
        ):
            r = client.get(f"/score?from={FROM_STR}&to={TO_STR}")
        assert r.json()["score"] == "red"


class TestCollect:
    def test_returns_written_counts(self, client: TestClient):
        with (
            patch("api.routes.prometheus.query_range", return_value=[]),
            patch("api.routes.loki.query_range", return_value=[]),
            patch("api.routes.init_db"),
            patch("api.routes.write_metrics", return_value=5),
            patch("api.routes.write_logs", return_value=12),
        ):
            r = client.post("/collect")
        assert r.status_code == 200
        body = r.json()
        assert body["metrics_written"] == 5
        assert body["logs_written"] == 12

    def test_calls_prometheus_and_loki(self, client: TestClient):
        with (
            patch("api.routes.prometheus.query_range", return_value=[]) as mock_prom,
            patch("api.routes.loki.query_range", return_value=[]) as mock_loki,
            patch("api.routes.init_db"),
            patch("api.routes.write_metrics", return_value=0),
            patch("api.routes.write_logs", return_value=0),
        ):
            client.post("/collect")
        assert mock_prom.called
        assert mock_loki.called

    def test_inits_db_before_writing(self, client: TestClient):
        call_order = []
        with (
            patch("api.routes.prometheus.query_range", return_value=[]),
            patch("api.routes.loki.query_range", return_value=[]),
            patch("api.routes.init_db", side_effect=lambda _: call_order.append("init")),
            patch(
                "api.routes.write_metrics",
                side_effect=lambda *_: call_order.append("metrics") or 0,
            ),
            patch(
                "api.routes.write_logs",
                side_effect=lambda *_: call_order.append("logs") or 0,
            ),
        ):
            client.post("/collect")
        assert call_order[0] == "init"
