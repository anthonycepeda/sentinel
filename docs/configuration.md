# Configuration

All settings are loaded from environment variables (or a `.env` file) via `src/config.py`.

```bash
cp .env.example .env   # copy the template, then fill in the three required values
```

## Required

These three must be set before the app will start.

| Variable | Description |
| --- | --- |
| `PROMETHEUS_URL` | Prometheus HTTP API base URL |
| `LOKI_URL` | Loki HTTP API base URL |
| `TARGET_SERVICE` | Name of the microservice to monitor |

**Example:**

```bash
PROMETHEUS_URL=http://prometheus:9090
LOKI_URL=http://loki:3100
TARGET_SERVICE=payments-api
```

---

## Optional (with defaults)

| Variable | Default | Description |
| --- | --- | --- |
| `COLLECTION_INTERVAL_MINUTES` | `5` | Lookback window per `/collect`: how far back to query + Prometheus step |
| `ANOMALY_WINDOW_MINUTES` | `30` | Rolling window for Z-score and log spike baseline calculation |
| `ANOMALY_Z_THRESHOLD` | `2.5` | `abs(z)` must exceed this to flag a metric anomaly |
| `LOG_SPIKE_MULTIPLIER` | `2.0` | Error count must exceed `baseline × multiplier` to flag a log spike |
| `DB_PATH` | `./sentinel.db` | Path to the SQLite database file |

---

## Tuning guidance

**`ANOMALY_Z_THRESHOLD`**  
Lower values (e.g. `2.0`) flag more anomalies and increase sensitivity — useful if you are missing real incidents. Higher values (e.g. `3.0`) reduce noise — useful if you are seeing too many false positives. A threshold of `2.5` corresponds roughly to flagging values more than 2.5 standard deviations from the mean, which is a common starting point.

**`LOG_SPIKE_MULTIPLIER`**  
A multiplier of `2.0` means a minute needs double the rolling mean to be flagged. Start here and increase if your service naturally has bursty error patterns. Decrease it (e.g. `1.5`) if spikes are subtle but still meaningful.

**`ANOMALY_WINDOW_MINUTES`**  
This controls how much history both detectors use as their baseline. Shorter windows (e.g. `15`) make the detector more reactive but also more sensitive to normal intra-day variation. Longer windows (e.g. `60`) smooth out variation but may miss fast incidents.

---

## How settings are loaded

Settings are defined in `src/config.py` as a pydantic-settings `BaseSettings` class and accessed via `get_settings()`, which is decorated with `@lru_cache` so the settings object is only instantiated once per process.

```python
from config import get_settings

settings = get_settings()
print(settings.anomaly_z_threshold)  # 2.5 (or whatever is in .env)
```

In tests, override via FastAPI's dependency injection:

```python
app.dependency_overrides[get_settings] = lambda: Settings(
    prometheus_url="http://test",
    loki_url="http://test",
    target_service="svc",
    db_path=":memory:",
)
```
