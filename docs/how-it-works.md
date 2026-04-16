# How Sentinel works

## What you will learn from reading this codebase

- How to build a typed data pipeline in Python with Pydantic models
- How Z-score anomaly detection works on time-series data
- How rolling-window baselines catch log-error bursts
- How to structure a FastAPI service with clean layer boundaries (no business logic in routes)
- How to test each layer independently — collectors with static fixtures, detectors as pure functions, routes with `TestClient` + dependency overrides

---

## Data flow

```text
Prometheus ──┐                          ┌── detect_anomalies()  ──┐
             ├── /collect ──► SQLite ──►│                          ├── score_health() ──► GET /score
Loki ────────┘                          └── detect_log_spikes() ──┘

POST /collect   pulls fresh telemetry and writes it to SQLite
GET /anomalies  reads from DB, runs detect_anomalies(), returns events
GET /score      reads from DB, runs both detectors, returns HealthScore
```

All normalization happens in `collector/` before anything is stored.  
All detection happens in `detector/` as pure functions — no I/O, no DB access.  
`api/routes.py` is thin wiring: read from DB → run detector → return result.

---

## Detection algorithms

### Z-score anomaly detection (`detector/anomaly.py`)

A Z-score measures how far a data point is from the recent average, in units of standard deviation:

```text
z = (value - rolling_mean) / rolling_std
```

If `abs(z) > threshold` (default **2.5**), the point is flagged as an anomaly.

**Example:** CPU usage has been 20 ± 3% for the last 30 minutes. A reading of 80% produces `z = (80 - 20) / 3 = 20` — far above the threshold. A reading of 25% produces `z = (25 - 20) / 3 = 1.7` — normal variation, not flagged.

The rolling window (default **30 minutes**) means the baseline adapts over time. A gradual rise won't trigger the detector; a sudden spike will. The window is time-based, so unevenly spaced data points are handled correctly.

Severity is scaled relative to the threshold:

| Severity | Condition                    |
| -------- | ---------------------------- |
| low      | `abs(z)` > threshold         |
| medium   | `abs(z)` > threshold × 1.5   |
| high     | `abs(z)` > threshold × 2     |

Requires at least 2 data points in the rolling window before a Z-score can be computed — earlier points are skipped, never silently flagged.

---

### Log spike detection (`detector/log_spikes.py`)

Rather than looking at individual log lines, this detector counts ERROR and CRITICAL records per 1-minute bucket, then asks: *is this minute's count unusually high compared to recent history?*

```text
baseline = rolling_mean_of_previous_buckets   (shift(1) excludes current bucket)
spike    = baseline > 0  AND  count > baseline × multiplier   (default multiplier = 2.0)
```

Two guards worth understanding:

- **`shift(1)`** — the current bucket is excluded from its own baseline. A 60-error minute doesn't "average out" a real incident.
- **`baseline > 0`** — a bucket is only flagged if there is a positive historical baseline to compare against. This prevents false positives on the first minutes of data when there is no history yet.

**Example:** An API normally throws 1–2 errors per minute. At 14:32 it throws 40. The baseline (rolling mean of the preceding 30 minutes) is ~2. `40 > 2 × 2.0 = 4` → spike detected.

Severity is based on how far the count exceeds the baseline:

| Severity | Condition                                        |
| -------- | ------------------------------------------------ |
| low      | count / baseline > multiplier                    |
| medium   | count / baseline > multiplier × 1.5              |
| high     | count / baseline > multiplier × 2                |

---

### Health scoring (`scorer/health.py`)

Combines both signals into a single score per time window. The code checks red first — "1–2 anomalies = amber" is a consequence of red firing at ≥ 3, not an explicit upper-bound check:

```python
if log_spike_count > 0 or anomaly_count >= 3:
    return "red"
if anomaly_count >= 1:
    return "amber"
return "green"
```

| Score    | Condition                               |
| -------- | --------------------------------------- |
| 🟢 green | No anomaly events, no log spikes        |
| 🟡 amber | 1–2 anomaly events, no log spikes       |
| 🔴 red   | 3+ anomaly events, **or** any log spike |

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

## Key design decisions

**Why Pydantic everywhere?**  
All data crossing a layer boundary is a Pydantic model. Validation errors surface at the boundary (the collector, not deep in the detector), and every model has a canonical JSON representation for free.

**Why pure functions for detection and scoring?**  
`detect_anomalies`, `detect_log_spikes`, and `score_health` take data in and return data out — no database calls, no HTTP requests, no side effects. This makes them trivial to test (no mocking needed) and trivial to reason about.

**Why SQLite?**  
POC scope: one service, local storage, no infrastructure. The storage layer is fully encapsulated in `storage/db.py` so it can be swapped later without touching anything else.

**Why Z-score instead of a model?**  
Explainability. You can show a stakeholder a graph, draw a line at `mean ± 2.5σ`, and say "the spike crossed that line". That is harder with a neural network.
