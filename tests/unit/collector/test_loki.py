import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from collector.loki import LokiError, query_range

FIXTURES = Path(__file__).parents[2] / "fixtures" / "loki"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://loki.test")


START = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
END = datetime(2026, 3, 13, 12, 5, tzinfo=UTC)


class TestQueryRangeSuccess:
    def test_normalizes_streams_into_records(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/loki/api/v1/query_range"
            assert request.url.params["direction"] == "forward"
            assert request.url.params["query"] == '{service_name="payments-api"}'
            return httpx.Response(200, json=_load("query_range_success.json"))

        records = query_range(
            _client(handler),
            query='{service_name="payments-api"}',
            start=START,
            end=END,
            service="payments-api",
        )

        assert len(records) == 3
        assert records[0].timestamp <= records[1].timestamp <= records[2].timestamp
        first = records[0]
        assert first.service == "payments-api"
        assert first.level == "ERROR"  # normalized from lowercase 'error'
        assert first.event_type == "timeout"
        assert first.timestamp.tzinfo is UTC

    def test_results_sorted_ascending_even_when_streams_interleave(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_load("query_range_success.json"))

        records = query_range(
            _client(handler), query="x", start=START, end=END, service="payments-api"
        )
        timestamps = [r.timestamp for r in records]
        assert timestamps == sorted(timestamps)

    def test_empty_result_returns_empty_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_load("query_range_empty.json"))

        assert (
            query_range(_client(handler), query="x", start=START, end=END, service="payments-api")
            == []
        )

    def test_start_end_serialized_as_nanoseconds(self):
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["start"] = request.url.params["start"]
            captured["end"] = request.url.params["end"]
            return httpx.Response(200, json=_load("query_range_empty.json"))

        query_range(
            _client(handler),
            query="x",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
            service="s",
        )
        assert captured["start"].endswith("000000000")  # ns precision
        assert int(captured["end"]) - int(captured["start"]) == 1_000_000_000


class TestQueryRangeErrors:
    def test_loki_400_with_error_body_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json=_load("query_range_error.json"))

        with pytest.raises(LokiError, match=r"bad_data|parse error"):
            query_range(_client(handler), query="((", start=START, end=END, service="s")

    def test_non_json_5xx_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        with pytest.raises(LokiError, match="HTTP 500"):
            query_range(_client(handler), query="x", start=START, end=END, service="s")

    def test_transport_failure_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns lookup failed")

        with pytest.raises(LokiError, match="request failed"):
            query_range(_client(handler), query="x", start=START, end=END, service="s")

    def test_non_streams_result_type_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"status": "success", "data": {"resultType": "matrix", "result": []}},
            )

        with pytest.raises(LokiError, match="expected streams"):
            query_range(_client(handler), query="x", start=START, end=END, service="s")

    def test_missing_level_label_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"event_type": "x"},
                                "values": [["1776074400000000000", "msg"]],
                            }
                        ],
                    },
                },
            )

        with pytest.raises(LokiError, match="level"):
            query_range(_client(handler), query="x", start=START, end=END, service="s")

    def test_missing_event_type_label_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"level": "INFO"},
                                "values": [["1776074400000000000", "msg"]],
                            }
                        ],
                    },
                },
            )

        with pytest.raises(LokiError, match="event_type"):
            query_range(_client(handler), query="x", start=START, end=END, service="s")

    def test_unknown_log_level_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {
                                "stream": {"level": "FATAL", "event_type": "x"},
                                "values": [["1776074400000000000", "msg"]],
                            }
                        ],
                    },
                },
            )

        with pytest.raises(LokiError, match="unknown log level"):
            query_range(_client(handler), query="x", start=START, end=END, service="s")


class TestUtcEnforcement:
    def _ok(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "success", "data": {"resultType": "streams", "result": []}}
        )

    def test_naive_start_rejected(self):
        with pytest.raises(LokiError, match="start must be"):
            query_range(
                _client(self._ok),
                query="x",
                start=datetime(2026, 3, 13, 12, 0),
                end=END,
                service="s",
            )

    def test_non_utc_end_rejected(self):
        paris = timezone(timedelta(hours=1))
        with pytest.raises(LokiError, match="end must be"):
            query_range(
                _client(self._ok),
                query="x",
                start=START,
                end=datetime(2026, 3, 13, 12, 5, tzinfo=paris),
                service="s",
            )
