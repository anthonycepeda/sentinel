from datetime import datetime

from schema.models import AnomalyEvent, HealthColor, HealthScore, LogSpikeEvent


def score_health(
    window_start: datetime,
    window_end: datetime,
    anomalies: list[AnomalyEvent],
    log_spikes: list[LogSpikeEvent],
) -> HealthScore:
    """Combine anomaly and log-spike signals into a green/amber/red health score.

    Scoring rules (from instructions.md):
    - green: no anomalies and no log spikes
    - amber: 1-2 anomaly events and no log spikes
    - red:   3+ anomaly events OR any log spike

    Args:
        window_start: Start of the evaluation window (must be UTC).
        window_end:   End of the evaluation window (must be UTC).
        anomalies:    AnomalyEvent list for the window (may be empty).
        log_spikes:   LogSpikeEvent list for the window (may be empty).

    Returns:
        A frozen HealthScore with the computed score and event counts.
    """
    anomaly_count = len(anomalies)
    log_spike_count = len(log_spikes)
    score: HealthColor = _compute_score(anomaly_count, log_spike_count)

    return HealthScore(
        window_start=window_start,
        window_end=window_end,
        score=score,
        anomaly_count=anomaly_count,
        log_spike_count=log_spike_count,
    )


def _compute_score(anomaly_count: int, log_spike_count: int) -> HealthColor:
    if log_spike_count > 0 or anomaly_count >= 3:
        return "red"
    if anomaly_count >= 1:
        return "amber"
    return "green"
