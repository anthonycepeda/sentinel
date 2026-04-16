# AGENTS.md

Project guidance for AI coding agents (OpenCode, Cursor, etc.) working in this repository.

---

## Commands

```bash
uv sync                        # install deps
uv run pytest -v               # run all tests
uv run pytest tests/unit/detector/test_anomaly.py -v  # run a single test file
uv run ruff check .            # lint
uv run ruff format .           # format
```

---

## Architecture

```
src/
  schema/models.py      # All Pydantic models — single source of truth
  config.py             # pydantic-settings BaseSettings, get_settings() with @lru_cache
  collector/
    prometheus.py       # Pull from Prometheus /api/v1/query_range → list[MetricRecord]
    loki.py             # Pull from Loki /loki/api/v1/query_range → list[LogRecord]
  storage/
    db.py               # SQLite read/write only layer — no business logic
  detector/
    anomaly.py          # Rolling Z-score over MetricRecord list → list[AnomalyEvent]
    log_spikes.py       # 1-min bucket spike detection over LogRecord list → list[LogSpikeEvent]
  scorer/
    health.py           # Combine anomalies + spikes → HealthScore (green/amber/red)
  api/
    routes.py           # FastAPI routes — no business logic, thin wiring only
    app.py              # FastAPI app entrypoint
tests/
  unit/                 # One test file per source module
  fixtures/             # Static JSON fixtures for collector tests
```

---

## Rules

### Models
- **Always use `pydantic.BaseModel`** — never `dataclass` or `TypedDict`
- All models live in `schema/models.py` — never define models elsewhere
- Use `ConfigDict(frozen=True)` for value-object semantics
- Every `datetime` field must be UTC — enforce via `field_validator` calling `_ensure_utc()`

### Layer boundaries
- `detector/` and `scorer/` are **pure functions** — no I/O, no DB access
- `storage/db.py` is the **only** layer that touches SQLite
- Schema normalization happens in `collector/` before any record reaches storage or detector
- No business logic in `api/routes.py` — routes call service functions and return results

### Config
- All env vars defined in `config.py` via `Settings(BaseSettings)`
- Access via `get_settings()` decorated with `@lru_cache`
- Never use `os.environ` directly outside `config.py`
- Never hardcode URLs, thresholds, or service names in source

### Timestamps
- All timestamps stored as ISO 8601 UTC strings in SQLite
- All `datetime` objects in Python carry `tzinfo=UTC`
- Naive datetimes are coerced to UTC; non-UTC timezone raises `ValueError`

### Testing
- httpx.MockTransport for collector tests — no real API calls
- Static JSON fixtures in `tests/fixtures/prometheus/` and `tests/fixtures/loki/`
- Shared test helpers in `tests/unit/detector/conftest.py`

### Commits
- Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`
- One branch per build-order step; tests must pass before moving to the next step

---

## Environment Variables

```
PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100
TARGET_SERVICE=<service-name>
COLLECTION_INTERVAL_MINUTES=5
ANOMALY_WINDOW_MINUTES=30
ANOMALY_Z_THRESHOLD=2.5
LOG_SPIKE_MULTIPLIER=2.0
DB_PATH=./sentinel.db
```

---

## Build Order

1. `schema/models.py` ✅
2. `storage/db.py` ✅
3. `collector/prometheus.py` ✅
4. `collector/loki.py` ✅
5. `detector/anomaly.py` ✅
6. `detector/log_spikes.py` ✅
7. `scorer/health.py`
8. `api/routes.py` + `api/app.py`
9. End-to-end tests
10. Makefile + README

Do not proceed to the next step until the current one has passing tests.
