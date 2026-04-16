# Sentinel

AIOps observability POC. Pulls Prometheus metrics and Loki logs from a single microservice, flags anomalies using Z-score detection and log-error spike detection, and reports a green/amber/red health score.

Statistical methods only — no ML training, no multi-service correlation. Designed as a self-contained demo to validate that existing telemetry contains enough signal to catch real incidents.

## Quickstart

```bash
uv sync
cp .env.example .env         # fill in PROMETHEUS_URL, LOKI_URL, TARGET_SERVICE
make run                     # starts uvicorn on :8000
```

## Make targets

| Target          | What it does                                    |
| --------------- | ----------------------------------------------- |
| `make install`  | `uv sync` — install all dependencies            |
| `make run`      | Start the API server on port 8000 (hot-reload)  |
| `make test`     | Run the full test suite                         |
| `make lint`     | Check with ruff                                 |
| `make format`   | Auto-fix and format with ruff                   |
| `make collect`  | POST /collect — trigger a manual telemetry pull |
| `make clean`    | Remove `.venv`, caches, and `sentinel.db`       |

## API endpoints

| Method | Path                   | Description                                       |
| ------ | ---------------------- | ------------------------------------------------- |
| `GET`  | `/health`              | Liveness check                                    |
| `GET`  | `/anomalies?from=&to=` | Anomaly events for a time range                   |
| `GET`  | `/score?from=&to=`     | Green/amber/red health score for a time range     |
| `POST` | `/collect`             | Pull latest telemetry from Prometheus and Loki    |

Timestamps use ISO 8601 UTC format, e.g. `2026-03-25T10:00:00Z`.

## Health score

| Score | Condition                                  |
| ----- | ------------------------------------------ |
| green | No anomalies, no log spikes                |
| amber | 1-2 metric anomalies, no log spikes        |
| red   | 3+ metric anomalies, or any log spike      |

## Environment variables

| Variable                      | Default         | Description                                    |
| ----------------------------- | --------------- | ---------------------------------------------- |
| `PROMETHEUS_URL`              | —               | Prometheus HTTP API base URL                   |
| `LOKI_URL`                    | —               | Loki HTTP API base URL                         |
| `TARGET_SERVICE`              | —               | Name of the microservice to monitor            |
| `COLLECTION_INTERVAL_MINUTES` | `5`             | How often to pull telemetry                    |
| `ANOMALY_WINDOW_MINUTES`      | `30`            | Rolling window for Z-score detection           |
| `ANOMALY_Z_THRESHOLD`         | `2.5`           | Z-score threshold for anomaly flagging         |
| `LOG_SPIKE_MULTIPLIER`        | `2.0`           | Error count ratio that triggers a log spike    |
| `DB_PATH`                     | `./sentinel.db` | SQLite database file path                      |

## Conventions

See [AGENTS.md](AGENTS.md) for architecture overview, layer boundaries, and coding rules.
