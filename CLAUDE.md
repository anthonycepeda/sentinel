# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Living document. Update after every correction, every PR, every pattern discovered.
> Rule: if Claude made a mistake once, add a rule so it never happens again.

-----

## Current State

Repo is pre-code — only `CLAUDE.md` and `instructions.md` exist. Start at build order step 1 (`schema/models.py`). The Makefile and `src/` tree below are the target layout, not the current one.

-----

## Project Overview

**Name:** Sentinel *(working name — final name TBD)*
**Purpose:** AIOps observability POC that pulls Prometheus metrics and Loki logs from a single microservice and detects anomalies using statistical methods — no ML model training.
**Type:** work
**Stack:** Python 3.12 · uv · FastAPI · httpx · pandas · numpy · SQLite · Ruff
**Repo:** [link or path]
**Notes:** ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/learning/AI/sentinel/

-----

## Architecture

```
sentinel/
  src/
    collector/
      prometheus.py   # Query Prometheus HTTP API → normalized MetricRecord list
      loki.py         # Query Loki HTTP API → normalized LogRecord list
    schema/
      models.py       # ALL Pydantic models: MetricRecord, LogRecord, AnomalyEvent, LogSpikeEvent, HealthScore
    storage/
      db.py           # SQLite read/write — store MetricRecord and LogRecord
    detector/
      anomaly.py      # Z-score over rolling window on metric records
      log_spikes.py   # Error-level log spike detection per 1-minute bucket
    scorer/
      health.py       # Combine anomalies + spikes → green/amber/red HealthScore
    api/
      routes.py       # FastAPI routes: /health, /anomalies, /score, /collect
      app.py          # FastAPI app factory
  tests/
    unit/
      detector/
      scorer/
      collector/
    config.py         # pydantic-settings BaseSettings — single source for env vars
  pyproject.toml
  Makefile
  README.md
  CLAUDE.md
```

**Key principles:**

- `schema/models.py` is the single source of truth for all data models — define everything here first, nothing else starts without it
- `collector/` normalizes raw Prometheus/Loki responses into `MetricRecord` / `LogRecord` before anything is stored — raw API formats never leak downstream
- `detector/` and `scorer/` are pure functions over normalized data — no I/O, no API calls, fully unit testable
- `storage/` is the only layer that touches SQLite — no direct DB access from collector, detector, or scorer
- `api/routes.py` = HTTP only. Business logic lives in detector + scorer. Never mix.
- Config via `pydantic-settings` `BaseSettings` — never call `os.environ` directly

-----

## How to Run

> Makefile is step 10 of the build order — these targets do not exist yet. Until then, invoke `uv run ...` directly.

```bash
# Install
make install

# Run locally
make run

# Run tests
make test

# Lint / format check
make lint

# Auto-fix lint and format
make fmt

# Trigger manual data collection
make collect

# Reset local DB and cache
make clean
```

-----

## Coding Conventions

### General

- Functions do one thing. If you need "and" to describe it, split it.
- No commented-out code in PRs. Delete it or keep it, never comment it.
- Prefer explicit over clever.
- Add comments only on non-obvious code — where the why or how isn't clear from reading it.

### Data Modelling

- Always use `pydantic.BaseModel` — never `dataclass` or `TypedDict`.
- Applies to all internal models, not just API schemas.
- All models live in `schema/models.py` — never define models inline in collector, detector, or api layers.

### Telemetry Schema

Every record pulled from Prometheus or Loki must be normalized into one of these before storage:

```python
# MetricRecord
{
  "timestamp": "2026-03-25T10:00:00Z",  # ISO 8601, UTC always
  "service": "payments-api",
  "metric_name": "http_request_duration_seconds",
  "value": 0.342,
  "labels": {}
}

# LogRecord
{
  "timestamp": "2026-03-25T10:00:01Z",
  "service": "payments-api",
  "level": "ERROR",
  "event_type": "timeout",  # normalized type, not raw log string
  "message": "..."
}
```

- `timestamp` is always UTC ISO 8601 — no exceptions
- `event_type` is a normalized category, never a raw log string
- Normalization happens in `collector/` — nothing downstream ever sees raw API formats

### Naming

- `snake_case` for variables and functions, `PascalCase` for classes
- Boolean variables start with `is_`, `has_`, `should_`
- Business logic functions named `<verb>_<noun>`: `detect_anomalies`, `compute_health_score`

### Error Handling

- Never swallow exceptions silently — always log or raise
- Return structured errors from API, never raw tracebacks
- Prometheus or Loki connection failures must raise a typed exception — never return empty results silently
- If a collection pull fails, log the error and preserve whatever was already stored — never wipe existing data on failure

### Testing

- Every new endpoint or backend feature must ship with at least one test — no exceptions for "simple" endpoints
- `detector/` and `scorer/` must have unit tests — these are pure functions, there is no excuse not to test them
- Use fixtures in `conftest.py`, not setup/teardown in test files
- Test file mirrors source path: `src/detector/anomaly.py` → `tests/unit/detector/test_anomaly.py`
- No real Prometheus or Loki calls in tests — use fixtures with pre-built `MetricRecord` / `LogRecord` lists

-----

## What NOT to Do

- ❌ Don't push directly to `main` — always branch and PR
- ❌ Don't hardcode values that belong in config or env vars
- ❌ Don't call `os.environ` directly — always go through `config.py`
- ❌ Don't define routes in `app.py` — only register routers there
- ❌ Don't put business logic in `routes.py` — delegate to detector + scorer
- ❌ Don't use `dataclass` or `TypedDict` — always `pydantic.BaseModel`
- ❌ Don't let raw Prometheus or Loki response formats leak past `collector/` — normalize immediately
- ❌ Don't train any ML model — statistical detection only for this POC
- ❌ Don't add multi-service correlation — one service only
- ❌ Don't add Docker or Helm — out of scope for POC
- ❌ Don't use an external database — SQLite only
- ❌ Don't invent new env var names — use only the ones defined in Environment & Config below

-----

## Workflow

### Branching

- `main` — stable, demoed
- `feature/<slug>` — new work
- `fix/<slug>` — bug fixes

### Build Order

Follow this strictly — do not skip ahead:

1. `schema/models.py` — all Pydantic models
2. `storage/db.py` — SQLite setup
3. `collector/prometheus.py` — pull + normalize metrics
4. `collector/loki.py` — pull + normalize logs
5. `detector/anomaly.py` — Z-score detection
6. `detector/log_spikes.py` — spike detection
7. `scorer/health.py` — green/amber/red score
8. `api/routes.py` + `api/app.py` — FastAPI wiring
9. Tests for detector and scorer
10. Makefile + README

Do not proceed to the next step until the current one has passing tests.

### PR Checklist

- [ ] Tests pass (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] No debug logs or `print()` statements
- [ ] `README.md` updated if endpoints or behavior changed
- [ ] `CLAUDE.md` updated if a new pattern was established or a mistake corrected

### Commits

- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`
- One logical change per commit — don't bundle unrelated changes

-----

## Environment & Config

```bash
# Required
PROMETHEUS_URL=        # e.g. http://localhost:9090
LOKI_URL=              # e.g. http://localhost:3100
TARGET_SERVICE=        # name of the microservice to monitor

# Optional
COLLECTION_INTERVAL_MINUTES=5     # default: 5
ANOMALY_WINDOW_MINUTES=30         # rolling window for Z-score — default: 30
ANOMALY_Z_THRESHOLD=2.5           # flag if abs(z) exceeds this — default: 2.5
LOG_SPIKE_MULTIPLIER=2.0          # flag if error count exceeds rolling mean by this factor — default: 2.0
DB_PATH=./sentinel.db             # default: ./sentinel.db
```

Config lives in: `config.py` (pydantic-settings `BaseSettings`)
Secrets managed via: `.env` (never committed — `.gitignore` enforced)

-----

## External Services & Integrations

| Service    | Purpose                              | Docs                                      |
|------------|--------------------------------------|-------------------------------------------|
| Prometheus | Source of truth for metrics          | <https://prometheus.io/docs/prometheus/latest/querying/api/> |
| Loki       | Source of truth for logs             | <https://grafana.com/docs/loki/latest/reference/api/> |

-----

## Anomaly Detection Reference

### Metrics — Z-score (detector/anomaly.py)

- Rolling window: `ANOMALY_WINDOW_MINUTES` (default 30 min)
- Flag if `abs(z_score) > ANOMALY_Z_THRESHOLD` (default 2.5)
- Apply to: request latency (p50, p95), error rate, memory usage, CPU

### Logs — Spike Detection (detector/log_spikes.py)

- Bucket into 1-minute windows
- Count ERROR + CRITICAL entries per window
- Flag if count exceeds rolling mean × `LOG_SPIKE_MULTIPLIER` (default 2.0)

### Health Score (scorer/health.py)

| Score        | Condition                                          |
|--------------|----------------------------------------------------|
| 🟢 green     | No anomalies, no log spikes                        |
| 🟡 amber     | 1–2 anomaly events, no log spikes                  |
| 🔴 red       | 3+ anomaly events OR any log spike detected        |

-----

## Known Issues / Gotchas

<!-- Hard-won knowledge. Add every time something surprising happens. -->

- Prometheus and Loki timestamps may differ slightly — always convert to UTC before storing, never assume clock sync
- Loki log queries return newest-first by default — reverse before bucketing into time windows
- [Add as you discover them]

-----

*Last updated: 2026-03-25 — initial CLAUDE.md for Sentinel AIOps POC*
