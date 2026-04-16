import pandas as pd

from schema.models import AnomalyEvent, MetricRecord


def detect_anomalies(
    records: list[MetricRecord],
    window_minutes: int = 30,
    z_threshold: float = 2.5,
) -> list[AnomalyEvent]:
    """Detect metric anomalies using Z-score over a rolling time window.

    For each (service, metric_name) group, computes a rolling mean and standard
    deviation over `window_minutes` and flags any point where abs(z) > z_threshold.

    Requires at least 2 data points in the rolling window before a z-score can be
    computed — earlier points are skipped, never silently flagged.

    Returns AnomalyEvent list sorted by timestamp ascending.
    """
    if not records:
        return []

    df = pd.DataFrame(
        [
            {
                "timestamp": r.timestamp,
                "service": r.service,
                "metric_name": r.metric_name,
                "value": r.value,
            }
            for r in records
        ]
    )

    events: list[AnomalyEvent] = []
    window = f"{window_minutes}min"

    for (service, metric_name), group in df.groupby(["service", "metric_name"]):
        group = group.sort_values("timestamp").set_index("timestamp")
        rolling = group["value"].rolling(window, min_periods=2)
        means = rolling.mean()
        stds = rolling.std()

        z_scores = (group["value"] - means) / stds.replace(0.0, float("nan"))
        flagged = group[z_scores.abs() > z_threshold].copy()
        flagged["z_score"] = z_scores[z_scores.abs() > z_threshold]

        for ts, row in flagged.iterrows():
            z = float(row["z_score"])
            events.append(
                AnomalyEvent(
                    timestamp=ts,
                    service=str(service),
                    metric_name=str(metric_name),
                    value=float(row["value"]),
                    z_score=round(z, 4),
                    severity=_severity(abs(z), z_threshold),
                )
            )

    return sorted(events, key=lambda e: e.timestamp)


def _severity(abs_z: float, threshold: float) -> str:
    if abs_z > threshold * 2:
        return "high"
    if abs_z > threshold * 1.5:
        return "medium"
    return "low"
