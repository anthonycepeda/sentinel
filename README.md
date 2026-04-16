# Sentinel

A learning project for building an AIOps observability system from scratch.

Sentinel pulls Prometheus metrics and Loki logs from a single microservice, detects anomalies using plain statistical methods, and reports a **green / amber / red health score** over any time range you query.

The goal is to show that telemetry a team already collects contains enough signal to flag real incidents — without training any ML model. Every algorithm is a few lines of maths you can read and explain to someone.

---

## What you will learn from reading this codebase

- How to build a typed data pipeline in Python with Pydantic models
- How Z-score anomaly detection works on time-series data
- How rolling-window baselines catch log-error bursts
- How to structure a FastAPI service with clean layer boundaries (no business logic in routes)
- How to test each layer independently — collectors with static fixtures, detectors as pure functions, routes with `TestClient` + dependency overrides

---

## How it works — the data flow

```text
Prometheus ──┐                          ┌── detect_anomalies()  ──┐
             ├── /collect ──► SQLite ──►│                          ├── score_health() ──► GET /score
Loki ────────┘                          └── detect_log_spikes() ──┘

GET /anomalies  calls detect_anomalies() directly from DB data
GET /score      calls both detectors then score_health()
POST /collect   pulls fresh telemetry and writes it to SQLite
```

All normalization happens in `collector/` before anything is stored.  
All detection happens in `detector/` as pure functions — no I/O, no DB access.  
The API in `api/routes.py` is thin wiring: read from DB → run detector → return result.

---

## Detection algorithms

### Z-score anomaly detection (`detector/anomaly.py`)

A Z-score measures how far a data point is from the recent average, in units of standard deviation:

```text
z = (value - rolling_mean) / rolling_std
```

If `abs(z) > threshold` (default **2.5**), the point is flagged as an anomaly.

**Example:** CPU usage has been 20 ± 3% for the last 30 minutes. A reading of 80% would have `z = (80 - 20) / 3 = 20` — far above the threshold. A reading of 25% would have `z = (25 - 20) / 3 = 1.7` — normal variation, not flagged.

The rolling window (default **30 minutes**) means the baseline adapts over time. A gradual rise won't trigger the detector; a sudden spike will.

Severity is scaled relative to the threshold:

| Severity | Condition                    |
| -------- | ---------------------------- |
| low      | `abs(z)` > threshold         |
| medium   | `abs(z)` > threshold × 1.5   |
| high     | `abs(z)` > threshold × 2     |

See: [src/detector/anomaly.py](src/detector/anomaly.py)

---

### Log spike detection (`detector/log_spikes.py`)

Rather than looking at individual log lines, this detector counts ERROR and CRITICAL records per 1-minute bucket, then asks: *is this minute's count unusually high compared to recent history?*

```text
baseline = rolling_mean_of_previous_buckets   (shift(1) excludes current bucket)
spike    = count > baseline × multiplier       (default multiplier = 2.0)
```

The `shift(1)` is important: it means the current bucket is never part of its own baseline. A 60-error minute doesn't "average out" a real incident.

**Example:** An API normally throws 1–2 errors per minute. At 14:32 it throws 40. The baseline (rolling mean of the preceding 30 minutes) is ~2. `40 > 2 × 2.0 = 4` → spike detected.

See: [src/detector/log_spikes.py](src/detector/log_spikes.py)

---

### Health scoring (`scorer/health.py`)

Combines both signals into a single score per time window:

| Score | Condition |
| ----- | --------- |
| 🟢 green | No anomaly events, no log spikes |
| 🟡 amber | 1–2 anomaly events, no log spikes |
| 🔴 red | 3+ anomaly events, **or** any log spike |

The logic is a pure function with no state — given the same anomaly and spike lists, it always returns the same score. This makes it trivial to unit test and easy to audit.

See: [src/scorer/health.py](src/scorer/health.py)

---

## Project layout

```text
src/
  schema/models.py      ← All Pydantic models. Start here — everything else uses these.
  config.py             ← pydantic-settings BaseSettings + get_settings() with @lru_cache
  collector/
    prometheus.py       ← Pull /api/v1/query_range → list[MetricRecord]
    loki.py             ← Pull /loki/api/v1/query_range → list[LogRecord]
  storage/
    db.py               ← SQLite read/write. The only layer that touches the DB.
  detector/
    anomaly.py          ← Rolling Z-score over MetricRecord list → list[AnomalyEvent]
    log_spikes.py       ← 1-min bucket spike detection over LogRecord list → list[LogSpikeEvent]
  scorer/
    health.py           ← Combine anomalies + spikes → HealthScore
  api/
    routes.py           ← FastAPI routes. No business logic — thin wiring only.
    app.py              ← FastAPI app entrypoint

tests/
  unit/                 ← One test file per source module, no cross-layer dependencies
  e2e/                  ← Full pipeline tests: raw records → detectors → scorer, no mocking
  fixtures/             ← Static JSON files of real Prometheus/Loki API responses
```

---

## Quickstart

```bash
uv sync
cp .env.example .env         # fill in PROMETHEUS_URL, LOKI_URL, TARGET_SERVICE
make test                    # verify everything passes (132 tests)
make run                     # start the API on :8000
```

To trigger a manual telemetry pull:

```bash
make collect
# {"metrics_written": 42, "logs_written": 130}
```

To query the health score for the last hour:

```bash
curl "http://localhost:8000/score?from=2026-03-25T09:00:00Z&to=2026-03-25T10:00:00Z"
# {"window_start":"...","window_end":"...","score":"amber","anomaly_count":1,"log_spike_count":0}
```

---

## Make targets

| Target         | What it does                                    |
| -------------- | ----------------------------------------------- |
| `make install` | `uv sync` — install all dependencies            |
| `make run`     | Start the API server on port 8000 (hot-reload)  |
| `make test`    | Run the full test suite                         |
| `make lint`    | Check with ruff                                 |
| `make fmt`     | Auto-fix and format with ruff                   |
| `make collect` | POST /collect — trigger a manual telemetry pull |
| `make clean`   | Remove `.venv`, caches, and `sentinel.db`       |

---

## API endpoints

| Method | Path                   | Description                                       |
| ------ | ---------------------- | ------------------------------------------------- |
| `GET`  | `/health`              | Liveness check                                    |
| `GET`  | `/anomalies?from=&to=` | Anomaly events for a time range                   |
| `GET`  | `/score?from=&to=`     | Green/amber/red health score for a time range     |
| `POST` | `/collect`             | Pull latest telemetry from Prometheus and Loki    |

Timestamps use ISO 8601 UTC format, e.g. `2026-03-25T10:00:00Z`.

---

## Environment variables

| Variable                      | Default         | Description                                    |
| ----------------------------- | --------------- | ---------------------------------------------- |
| `PROMETHEUS_URL`              | —               | Prometheus HTTP API base URL                   |
| `LOKI_URL`                    | —               | Loki HTTP API base URL                         |
| `TARGET_SERVICE`              | —               | Name of the microservice to monitor            |
| `COLLECTION_INTERVAL_MINUTES` | `5`             | How often to pull telemetry                    |
| `ANOMALY_WINDOW_MINUTES`      | `30`            | Rolling window for Z-score and spike detection |
| `ANOMALY_Z_THRESHOLD`         | `2.5`           | Z-score threshold for anomaly flagging         |
| `LOG_SPIKE_MULTIPLIER`        | `2.0`           | Error count ratio that triggers a log spike    |
| `DB_PATH`                     | `./sentinel.db` | SQLite database file path                      |

---

## Key design decisions

**Why Pydantic everywhere?**  
All data crossing a layer boundary is a Pydantic model. This means validation errors surface at the boundary (the collector, not deep in the detector), and every model has a canonical JSON representation for free.

**Why pure functions for detection and scoring?**  
`detect_anomalies`, `detect_log_spikes`, and `score_health` take data in and return data out — no database calls, no HTTP requests, no side effects. This makes them trivial to test (no mocking needed) and trivial to reason about.

**Why SQLite?**  
POC scope: one service, local storage, no infrastructure. The storage layer is fully encapsulated in `storage/db.py` so it can be swapped later without touching anything else.

**Why Z-score instead of a model?**  
Explainability. You can show a stakeholder a graph, draw a line at `mean ± 2.5σ`, and say "the spike crossed that line". That is harder with a neural network.

---

## Testing strategy

```text
tests/unit/schema/      ← Model validation, UTC enforcement, round-trips
tests/unit/storage/     ← DB read/write, filter behaviour
tests/unit/collector/   ← HTTP normalisation with static JSON fixtures (no live calls)
tests/unit/detector/    ← Pure function behaviour: flat series, spikes, severity bands
tests/unit/scorer/      ← All score combinations as a parametrized matrix
tests/unit/api/         ← Route wiring: status codes, param validation, settings wired correctly
tests/e2e/              ← Full pipeline: raw records → detectors → scorer, no mocking
```

Each layer's tests only know about that layer's public API. The e2e tests are the only place where multiple layers are exercised together.

---

## Architecture reference

See [AGENTS.md](AGENTS.md) for a concise reference of conventions, commands, and layer rules.
