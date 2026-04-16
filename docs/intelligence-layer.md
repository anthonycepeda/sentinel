# Intelligence layer — future roadmap

The current Sentinel detects anomalies in real time using fixed statistical rules (Z-score, rolling-window spike detection). This document describes the next evolution: a system that **learns from past incidents** and **predicts failures before they happen**.

---

## The problem Sentinel does not yet solve

Today Sentinel asks: *is this metric or error count unusual compared to the last 30 minutes?*

That is reactive. The intelligence layer asks: *given how this service behaved before past incidents, is it heading toward one now?*

Loki and Sentry already do reactive alerting well. The differentiator here is learning from historical patterns — building a memory of what "about to fail" looks like for this specific service, and surfacing that as a forward-looking probability score.

---

## What is required before any ML can work

Learning requires two things the current architecture does not have:

1. **Ground truth** — a record of which past time windows were real incidents. Without labels there is nothing to train on.
2. **Sufficient history** — weeks of metric + log data with compacted aggregates. A 5-minute rolling window is not enough signal for a classifier.

Both must be built before any ML step begins. This is why the phases below are strictly ordered.

---

## Phase A — Foundation (no ML)

### A1. Incident labeling

Add a way to record confirmed incidents: what happened, when it started and ended, and how severe it was.

**API:**
```
POST /incidents   { start, end, description, severity }
GET  /incidents?from=&to=
```

**Storage:** new `incidents` table in SQLite.

**Why first:** every downstream step — feature extraction, model training, prediction evaluation — depends on labeled incidents existing.

**Initial source:** manual annotation via the API. Longer-term target: pull automatically from Dynatrace Problems API (see Phase B).

---

### A2. Data retention + compaction

The current schema stores every raw `MetricRecord` and `LogRecord` indefinitely. For prediction you need weeks of history, but raw per-second records become expensive quickly.

**What to build:**
- Configurable `HISTORY_RETENTION_DAYS` (raw records kept for N days, then dropped)
- Hourly and daily aggregate tables: `mean`, `p95`, `max`, `error_count` per metric per service
- A background compaction job (or a `POST /compact` endpoint) that rolls up old raw records into aggregates

---

### A3. Trend detection

Z-score detects magnitude (is this value high?). Trend detection asks: is this value *rising*, and how fast?

**What to build:** extend `detector/` with a `trend.py` module that computes:
- Rolling linear regression slope over a configurable window (is the metric trending up or down?)
- Acceleration (is the slope itself increasing?)
- A `TrendEvent` model: `{ timestamp, metric_name, slope, acceleration, direction }`

**Why before ML:** trend features become inputs to the classifier in Phase C. Computing them as a separate detector keeps the architecture clean.

---

## Phase B — Learning from past

### B1. Precursor feature extraction

Given a labeled incident, look back N minutes and ask: what signals were present before it?

**What to build:** a `POST /incidents/{id}/analyze` endpoint (or offline script) that:
1. Takes the incident's `start` time
2. Looks back a configurable window (e.g. 60 minutes before)
3. Computes a feature vector: metric slopes, error acceleration, how many anomaly events fired, which metrics were flagged first
4. Stores the feature vector against the incident label

This builds the training dataset.

---

### B2. Dynatrace integration

Replace manual incident labeling with automatic import from Dynatrace.

**What to build:** a `collector/dynatrace.py` module that:
- Calls the Dynatrace Problems API (`/api/v2/problems`)
- Normalizes each Problem into Sentinel's `Incident` model (start/end/severity/description)
- Can be triggered via `POST /collect/incidents` or run on a schedule

**Config additions:** `DYNATRACE_URL`, `DYNATRACE_API_TOKEN`.

**Dependency:** A1 must exist (the `incidents` table) before this can write to it.

---

## Phase C — Prediction

### C1. Failure prediction model

Train a classifier on the feature vectors from B1 to output P(incident in next N minutes).

**Approach:**
- Library: scikit-learn (logistic regression or gradient boosting — start simple, explainability matters)
- Input features: metric slopes, error acceleration, anomaly event counts, trend directions from the preceding window
- Output: probability score 0–1 + which features contributed most (feature importances)
- Retrain: `POST /model/train` triggers a training run over all labeled incidents in the DB
- Persistence: serialize the trained model to disk (joblib), load on startup

**Prediction horizons:** start at 30 minutes, extend to 1–2 hours as more labeled data accumulates.

---

### C2. Predictive endpoint

Surface the model's output via the API.

```
GET /predict?from=&to=
```

Response:
```json
{
  "probability": 0.74,
  "horizon_minutes": 30,
  "score": "amber",
  "contributing_signals": [
    { "metric": "http_request_duration_p95", "slope": 0.42, "weight": 0.38 },
    { "metric": "error_rate", "acceleration": 0.15, "weight": 0.31 }
  ]
}
```

The `contributing_signals` field is the explainability hook — it answers *why* the model thinks a failure is coming, not just that it does.

---

### C3. Feedback loop

Close the loop: when a predicted incident does or does not happen, record the outcome and use it to improve the model.

**What to build:**
- `POST /predictions/{id}/outcome` — mark prediction as correct, false positive, or missed
- Aggregate false positive / recall metrics over time
- Trigger retraining when outcome count crosses a threshold

---

## Dependency map

```
A1 incident labeling
  └─► B1 precursor extraction ──► C1 prediction model ──► C2 /predict endpoint
  └─► B2 Dynatrace integration                         └─► C3 feedback loop
A2 data retention  ──────────────► C1 (sufficient history needed for training)
A3 trend detection ──────────────► B1 (trend features feed the feature vector)
```

A1, A2, A3 can be built in parallel. B1 and B2 both require A1. C1 requires A2 + B1. C2 and C3 require C1.

---

## What stays the same

The existing detection layer (`detector/anomaly.py`, `detector/log_spikes.py`) does not go away. The prediction model sits *alongside* it — a second signal, not a replacement. The health scorer gains a third input: `prediction_score`, weighted alongside anomaly and spike counts.

The architecture principle stays too: pure functions for detection, thin routes, Pydantic models at every boundary.
