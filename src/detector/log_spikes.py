import pandas as pd

from schema.models import LogRecord, LogSpikeEvent, Severity

_ERROR_LEVELS = {"ERROR", "CRITICAL"}


def detect_log_spikes(
    records: list[LogRecord],
    multiplier: float = 2.0,
    window_minutes: int = 30,
) -> list[LogSpikeEvent]:
    """Detect error-level log spikes using a rolling count baseline.

    For each service, buckets ERROR+CRITICAL records into 1-minute windows and
    computes a rolling mean count over `window_minutes`. Any bucket whose count
    exceeds `rolling_mean * multiplier` is flagged as a spike.

    Requires at least 2 non-empty buckets in the rolling window before a
    baseline can be established — earlier buckets are never silently flagged.

    Returns LogSpikeEvent list sorted by timestamp ascending.
    """
    if not records:
        return []

    error_records = [r for r in records if r.level in _ERROR_LEVELS]
    if not error_records:
        return []

    df = pd.DataFrame([{"timestamp": r.timestamp, "service": r.service} for r in error_records])

    events: list[LogSpikeEvent] = []
    window = f"{window_minutes}min"

    for service, group in df.groupby("service"):
        group = group.set_index("timestamp").sort_index()
        counts = group.resample("1min").size()

        rolling_mean = counts.rolling(window, min_periods=2).mean()
        baseline_series = rolling_mean.shift(1)

        flagged_mask = (baseline_series > 0) & (counts > baseline_series * multiplier)
        flagged = counts[flagged_mask]
        baselines = baseline_series[flagged_mask]

        for ts, count in flagged.items():
            baseline = float(baselines[ts])
            events.append(
                LogSpikeEvent(
                    timestamp=ts.to_pydatetime(),
                    service=str(service),
                    count=int(count),
                    baseline=baseline,
                    severity=_spike_severity(int(count), baseline, multiplier),
                )
            )

    return sorted(events, key=lambda e: e.timestamp)


def _spike_severity(count: int, baseline: float, multiplier: float) -> Severity:
    """Classify spike magnitude relative to multiplier threshold.

    Boundaries are exclusive: ratio must strictly exceed each band.
    - count > baseline * multiplier * 2   → "high"
    - count > baseline * multiplier * 1.5 → "medium"
    - else                                → "low"
    """
    ratio = count / baseline
    if ratio > multiplier * 2:
        return "high"
    if ratio > multiplier * 1.5:
        return "medium"
    return "low"
