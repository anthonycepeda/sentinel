# Sentinel — AIOps Observability POC

## Context

Internal POC for the BNP Robotic team. Proves that existing telemetry (Prometheus metrics + Loki logs) from a single microservice contains enough signal to detect anomalies automatically.

No ML model training in this phase. Statistical anomaly detection only — explainable, fast to build, easy to validate against real past incidents.

Goal: a working demo we can show the team to get buy-in for a full multi-service build.

---

## Stack

- Python 3.12
- uv (package manager — no pip, no pipenv)
- FastAPI — internal API + health endpoints
- httpx — pull data from Prometheus and Loki HTTP APIs
- pandas + numpy — time-series manipulation and anomaly detection
- SQLite — local storage for pulled telemetry (POC only, no external DB)
- Ruff — linting and formatting

---

## Project Structure

```
sentinel/
  src/
    collector/        # Pulls data from Prometheus and Loki
      prometheus.py   # Query Prometheus HTTP API, return normalized records
      loki.py         # Query Loki HTTP API, return normalized records
    schema/
      models.py       # Pydantic models: MetricRecord, LogRecord, NormalizedEvent
    storage/
      db.py           # SQLite read/write — store raw pulls, normalized events
    detector/
      anomaly.py      # Z-score + rolling window anomaly detection on metrics
      log_spikes.py   # Error-level log spike detection per time window
    scorer/
      health.py       # Combine metric anomalies + log spikes into green/amber/red score
    api/
      routes.py       # FastAPI routes: /health, /anomalies, /score
      app.py          # FastAPI app entrypoint
  tests/
    unit/
  pyproject.toml
  CLAUDE.md
  Makefile
  README.md
```

---

## Telemetry Schema

Every record pulled from either source is normalized into a common structure before storage or analysis:

```python
# MetricRecord
{
  "timestamp": "2026-03-25T10:00:00Z",  # ISO 8601, UTC always
  "service": "payments-api",
  "metric_name": "http_request_duration_seconds",
  "value": 0.342,
  "labels": {}  # passthrough from Prometheus
}

# LogRecord
{
  "timestamp": "2026-03-25T10:00:01Z",
  "service": "payments-api",
  "level": "ERROR",
  "event_type": "timeout",  # normalized, not raw log string
  "message": "..."
}
```

Schema normalization happens in `collector/` before anything is stored. Nothing downstream touches raw Prometheus or Loki response formats.

---

## Anomaly Detection Logic

### Metrics (detector/anomaly.py)

- Rolling window: configurable, default 30 minutes
- Method: Z-score — flag any value where `abs(z) > 2.5`
- Apply to: request latency (p50, p95), error rate, memory usage, CPU
- Output: list of `AnomalyEvent` with timestamp, metric, value, z_score, severity

### Logs (detector/log_spikes.py)

- Bucket log records into 1-minute windows
- Count ERROR + CRITICAL level entries per window
- Flag windows where count exceeds rolling mean by 2x or more
- Output: list of `LogSpikeEvent` with timestamp, count, baseline, severity

---

## Health Score (scorer/health.py)

Combine both signals into a single score per time window:

| Score | Condition |
|-------|-----------|
| 🟢 green | No anomalies detected |
| 🟡 amber | 1–2 anomaly events, no log spikes |
| 🔴 red | 3+ anomaly events OR any log spike detected |

Simple and explainable — no black box for the demo.

---

## API Endpoints

```
GET  /health                    # Service liveness
GET  /anomalies?from=&to=       # List anomaly events in time range
GET  /score?from=&to=           # Health score for time range
POST /collect                   # Trigger manual pull from Prometheus + Loki
```

---

## Makefile Commands

```
make install     # uv sync
make run         # uvicorn src/api/app.py
make test        # pytest
make lint        # ruff check + ruff format
make collect     # POST /collect to trigger a manual data pull
make clean       # remove .venv, __pycache__, sentinel.db
```

---

## Environment Variables

```
PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100
TARGET_SERVICE=<service-name-to-monitor>
COLLECTION_INTERVAL_MINUTES=5
ANOMALY_WINDOW_MINUTES=30
ANOMALY_Z_THRESHOLD=2.5
LOG_SPIKE_MULTIPLIER=2.0
DB_PATH=./sentinel.db
```

---

## Build Order

1. `schema/models.py` — define all Pydantic models first, nothing else starts without this
2. `storage/db.py` — SQLite setup, read/write for MetricRecord and LogRecord
3. `collector/prometheus.py` — pull and normalize metrics
4. `collector/loki.py` — pull and normalize logs
5. `detector/anomaly.py` — Z-score detection over metric records
6. `detector/log_spikes.py` — spike detection over log records
7. `scorer/health.py` — combine into green/amber/red
8. `api/routes.py` + `api/app.py` — wire everything into FastAPI
9. Tests for detector and scorer (these are the critical units)
10. Makefile + README

Do not proceed to the next step until the current one has passing tests.

---

## What NOT to Do

- ❌ No ML model training — statistical detection only for this POC
- ❌ No multi-service correlation — one service only
- ❌ No real-time streaming — pull-based collection is enough
- ❌ No external database — SQLite only
- ❌ No Docker or Helm — out of scope for POC
- ❌ Don't invent env var names — use only the ones defined above
- ❌ Don't skip schema normalization — raw Prometheus/Loki formats must never reach the detector layer
