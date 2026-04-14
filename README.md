# Sentinel

AIOps observability POC. Pulls Prometheus metrics and Loki logs from a single microservice, flags anomalies using Z-score detection and log-error spike detection, and reports a green/amber/red health score.

Statistical methods only — no ML training, no multi-service correlation. Designed as a self-contained demo to validate that existing telemetry contains enough signal to catch real incidents.

## Quickstart

```bash
uv sync
cp .env.example .env         # then fill in PROMETHEUS_URL, LOKI_URL, TARGET_SERVICE
uv run pytest
```

## Conventions

See [CLAUDE.md](CLAUDE.md) for architecture, build order, coding rules, and env var reference.
