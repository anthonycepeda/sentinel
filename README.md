# Sentinel

A learning project for building an AIOps observability system from scratch.

Sentinel pulls Prometheus metrics and Loki logs from a single microservice, detects anomalies using plain statistical methods (Z-score + log-error spike detection), and reports a **green / amber / red health score** over any time range you query.

No ML training. No multi-service correlation. Every algorithm is a few lines of maths you can read and explain to someone.

## Quickstart

```bash
uv sync
cp .env.example .env   # fill in PROMETHEUS_URL, LOKI_URL, TARGET_SERVICE
make test              # verify everything passes
make run               # start the API on :8000
```

Trigger a telemetry pull, then query the health score:

```bash
make collect
curl "http://localhost:8000/score?from=2026-03-25T09:00:00Z&to=2026-03-25T10:00:00Z"
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
