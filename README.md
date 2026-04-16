# Sentinel

A learning project for building an AIOps observability system from scratch.

Sentinel pulls Prometheus metrics and Loki logs from a single microservice, detects anomalies using plain statistical methods (Z-score + log-error spike detection), and reports a **green / amber / red health score** over any time range you query.

No ML training. No multi-service correlation. Every algorithm is a few lines of maths you can read and explain to someone.

## Quickstart

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set the three required values — the rest have sensible defaults:

```bash
PROMETHEUS_URL=http://localhost:9090   # your Prometheus instance
LOKI_URL=http://localhost:3100         # your Loki instance
TARGET_SERVICE=payments-api            # the service name to monitor
```

### 3. Run the tests (no live services needed — everything is mocked)

```bash
make test
```

### 4. Start the API

```bash
make run   # listens on http://localhost:8000
```

### 5. Pull telemetry and check the health score

In a second terminal, once the server is running:

```bash
make collect   # pulls the last 5 minutes from Prometheus + Loki

# Query the score for the window you just collected.
# 'now' and 'five minutes ago' as ISO 8601 UTC:
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
FIVE_MIN_AGO=$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%SZ)
curl "http://localhost:8000/score?from=${FIVE_MIN_AGO}&to=${NOW}"
```

## API

| Method | Path                   | Description                                    |
| ------ | ---------------------- | ---------------------------------------------- |
| `GET`  | `/health`              | Liveness check                                 |
| `GET`  | `/anomalies?from=&to=` | Anomaly events for a time range                |
| `GET`  | `/score?from=&to=`     | Green/amber/red health score for a time range  |
| `POST` | `/collect`             | Pull latest telemetry from Prometheus and Loki |

Timestamps use ISO 8601 UTC, e.g. `2026-03-25T10:00:00Z`.

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

## Docs

- [How it works](docs/how-it-works.md) — data flow, detection algorithms, project layout, testing strategy, design decisions
- [Configuration](docs/configuration.md) — all environment variables with tuning guidance
- [AGENTS.md](AGENTS.md) — quick reference for conventions and layer rules
