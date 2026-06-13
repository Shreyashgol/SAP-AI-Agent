"""
Anomaly Detection — statistical outlier detection for time-series metric data.

Spec: AD-001, AD-002, AD-003
  - AD-001: Z-score based detection; threshold configurable (default ±2.5σ)
  - AD-002: IQR-based detection as alternative (more robust to non-normal distributions)
  - AD-003: Returns AnomalyResult with value, expected range, severity, and description

Used by:
  - RCA agent to highlight anomalous data points
  - Proactive alerts (Sprint 14) to surface anomalies automatically
  - Dashboard widgets that show "outlier" badges

No ML framework dependency — pure Python statistics for low-latency detection.
For complex multivariate anomaly detection, Sprint 14+ extends this with Prophet.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class AnomalyResult:
    value: float
    mean: float
    std_dev: float
    z_score: float
    is_anomaly: bool
    severity: str          # "low" | "medium" | "high" | "none"
    description: str
    lower_bound: float
    upper_bound: float


def detect_zscore(
    values: list[float],
    target_index: int = -1,
    threshold: float = 2.5,
) -> AnomalyResult | None:
    """
    Z-score anomaly detection for a list of numeric values.
    target_index: which value to evaluate (-1 = last/most recent).
    Returns None if fewer than 3 data points (insufficient for statistics).
    """
    clean = [v for v in values if v is not None and not math.isnan(v)]
    if len(clean) < 3:
        return None

    target = clean[target_index]
    others = clean[:target_index] if target_index != -1 else clean[:-1]

    if len(others) < 2:
        return None

    mean = statistics.mean(others)
    std = statistics.stdev(others)

    if std == 0:
        # All prior values identical — any deviation is anomalous
        z = float("inf") if target != mean else 0.0
    else:
        z = (target - mean) / std

    is_anomaly = abs(z) > threshold
    severity = _severity(abs(z), threshold)
    lower = mean - threshold * std
    upper = mean + threshold * std

    direction = "above" if z > 0 else "below"
    description = (
        f"Value {target:.2f} is {abs(z):.1f}σ {direction} the recent average of {mean:.2f}."
        if is_anomaly
        else f"Value {target:.2f} is within normal range (mean={mean:.2f}, ±{threshold}σ)."
    )

    return AnomalyResult(
        value=target,
        mean=mean,
        std_dev=std,
        z_score=round(z, 3),
        is_anomaly=is_anomaly,
        severity=severity,
        description=description,
        lower_bound=round(lower, 4),
        upper_bound=round(upper, 4),
    )


def detect_iqr(
    values: list[float],
    target_index: int = -1,
    multiplier: float = 1.5,
) -> AnomalyResult | None:
    """
    IQR-based anomaly detection (more robust than Z-score for skewed data).
    Flags target if it falls outside [Q1 - multiplier*IQR, Q3 + multiplier*IQR].
    """
    clean = [v for v in values if v is not None and not math.isnan(v)]
    if len(clean) < 4:
        return None

    target = clean[target_index]
    population = sorted(clean[:target_index] if target_index != -1 else clean[:-1])

    n = len(population)
    q1 = population[n // 4]
    q3 = population[(3 * n) // 4]
    iqr = q3 - q1

    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    is_anomaly = target < lower or target > upper
    mean = statistics.mean(population)
    std = statistics.stdev(population) if len(population) > 1 else 0.0
    z = (target - mean) / std if std > 0 else 0.0

    severity = _severity(abs(z), 2.5)

    direction = "above" if target > upper else "below"
    description = (
        f"Value {target:.2f} is {direction} the expected range [{lower:.2f}, {upper:.2f}] (IQR method)."
        if is_anomaly
        else f"Value {target:.2f} is within the expected range [{lower:.2f}, {upper:.2f}]."
    )

    return AnomalyResult(
        value=target,
        mean=round(mean, 4),
        std_dev=round(std, 4),
        z_score=round(z, 3),
        is_anomaly=is_anomaly,
        severity=severity,
        description=description,
        lower_bound=round(lower, 4),
        upper_bound=round(upper, 4),
    )


def scan_column_for_anomalies(
    rows: list[dict],
    column: str,
    method: str = "zscore",
    threshold: float = 2.5,
) -> list[dict[str, Any]]:
    """
    Scan all values in a result column and return anomalous rows with their scores.
    Used by the response formatter to annotate data tables.
    """
    values: list[float] = []
    for row in rows:
        v = row.get(column)
        try:
            values.append(float(v))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            values.append(float("nan"))

    anomalies: list[dict] = []
    detect_fn = detect_zscore if method == "zscore" else detect_iqr

    for i, (row, val) in enumerate(zip(rows, values)):
        if math.isnan(val) or len(values) < 3:
            continue
        result = detect_fn(values, target_index=i, threshold=threshold)
        if result and result.is_anomaly:
            anomalies.append({
                "row_index": i,
                "row": row,
                "column": column,
                "anomaly": {
                    "value": result.value,
                    "z_score": result.z_score,
                    "severity": result.severity,
                    "description": result.description,
                },
            })

    return anomalies


# ── Private ────────────────────────────────────────────────────────────────────

def _severity(abs_z: float, threshold: float) -> str:
    if abs_z <= threshold:
        return "none"
    if abs_z <= threshold * 1.5:
        return "low"
    if abs_z <= threshold * 2.0:
        return "medium"
    return "high"
