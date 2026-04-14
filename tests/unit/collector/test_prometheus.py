import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from collector.prometheus import PrometheusError, query_range

FIXTURES = Path(__file__).parents[2] / "fixtures" / "prometheus"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://prom.test")


START = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
END = datetime(2026, 3, 13, 12, 5, tzinfo=UTC)


class TestQueryRangeSuccess:
    def test_normalizes_matrix_into_records(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/query_range"
            assert request.url.params["query"] == "http_request_duration_seconds"
            return httpx.Response(200, json=_load("query_range_success.json"))

        records = query_range(
            _client(handler),
            query="http_request_duration_seconds",
            start=START,
            end=END,
            step="60s",
            service="payments-api",
        )

        assert len(records) == 5  # 3 + 2 points across 2 series
        first = records[0]
        assert first.service == "payments-api"
        assert first.metric_name == "http_request_duration_seconds"
        assert first.value == 0.342
        assert first.timestamp.tzinfo is UTC
        assert first.labels == {
            "instance": "payments-api:8080",
            "job": "payments-api",
            "route": "/pay",
            "quantile": "0.95",
        }
        assert "__name__" not in first.labels

    def test_empty_result_returns_empty_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_load("query_range_empty.json"))

        records = query_range(
            _client(handler),
            query="nope",
            start=START,
            end=END,
            step="60s",
            service="payments-api",
        )
        assert records == []


class TestQueryRangeErrors:
    def test_non_json_5xx_raises_prometheus_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="upstream exploded")

        with pytest.raises(PrometheusError, match="HTTP 500"):
            query_range(
                _client(handler),
                query="x",
                start=START,
                end=END,
                step="60s",
                service="s",
            )

    def test_transport_failure_raises_prometheus_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns lookup failed")

        with pytest.raises(PrometheusError, match="request failed"):
            query_range(
                _client(handler),
                query="x",
                start=START,
                end=END,
                step="60s",
                service="s",
            )

    def test_prometheus_400_with_error_body_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json=_load("query_range_error.json"))

        with pytest.raises(PrometheusError, match=r"bad_data|parse error"):
            query_range(
                _client(handler),
                query="((",
                start=START,
                end=END,
                step="60s",
                service="s",
            )

    def test_non_matrix_result_type_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "vector", "result": []}},
            )

        with pytest.raises(PrometheusError, match="expected matrix"):
            query_range(
                _client(handler),
                query="x",
                start=START,
                end=END,
                step="60s",
                service="s",
            )

    def test_missing_metric_name_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "matrix",
                        "result": [{"metric": {"foo": "bar"}, "values": [[1776074400, "1.0"]]}],
                    },
                },
            )

        with pytest.raises(PrometheusError, match="__name__"):
            query_range(
                _client(handler),
                query="x",
                start=START,
                end=END,
                step="60s",
                service="s",
            )


class TestUtcEnforcement:
    def _noop_handler(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "matrix", "result": []}}
        )

    def test_naive_start_rejected(self):
        with pytest.raises(PrometheusError, match="start must be"):
            query_range(
                _client(self._noop_handler),
                query="x",
                start=datetime(2026, 3, 13, 12, 0),
                end=END,
                step="60s",
                service="s",
            )

    def test_non_utc_end_rejected(self):
        paris = timezone(timedelta(hours=1))
        with pytest.raises(PrometheusError, match="end must be"):
            query_range(
                _client(self._noop_handler),
                query="x",
                start=START,
                end=datetime(2026, 3, 13, 12, 5, tzinfo=paris),
                step="60s",
                service="s",
            )
