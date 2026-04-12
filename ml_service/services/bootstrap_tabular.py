from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional during minimal local setup
    np = None

TABULAR_FEATURE_BOUNDS: tuple[tuple[float, float], ...] = (
    (0.0, 100.0),   # recent_training_load
    (0.0, 100.0),   # chronic_training_load
    (0.4, 2.4),     # acute_chronic_ratio
    (0.0, 100.0),   # training_consistency
    (0.0, 12.0),    # avg_sleep_hours
    (0.0, 100.0),   # sleep_consistency
    (40.0, 210.0),  # avg_avg_hr
    (60.0, 230.0),  # avg_max_hr
    (85.0, 100.0),  # avg_spo2
    (85.0, 180.0),  # avg_systolic
    (45.0, 120.0),  # avg_diastolic
    (0.0, 10.0),    # avg_feeling_score
    (0.0, 100.0),   # athlete_age
    (30.0, 220.0),  # athlete_weight_kg
    (120.0, 230.0), # athlete_height_cm
)


@dataclass(slots=True)
class BootstrapTabularScaler:
    feature_bounds: tuple[tuple[float, float], ...] = TABULAR_FEATURE_BOUNDS

    def transform(self, values: Any) -> Any:
        rows = _ensure_2d(values)
        clipped_rows = [
            [
                _clip(row[index], *self.feature_bounds[index])
                for index in range(min(len(row), len(self.feature_bounds)))
            ]
            for row in rows
        ]
        return _to_output_matrix(clipped_rows)


@dataclass(slots=True)
class BootstrapTabularModel:
    kind: str

    def predict(self, values: Any) -> Any:
        rows = _ensure_2d(values)
        predictions = [self._predict_row(row) for row in rows]
        return _to_output_vector(predictions)

    def _predict_row(self, row: list[float]) -> float:
        normalized = [
            _clip(
                row[index] if index < len(row) else 0.0,
                *TABULAR_FEATURE_BOUNDS[index],
            )
            for index in range(len(TABULAR_FEATURE_BOUNDS))
        ]

        (
            recent_load,
            chronic_load,
            acute_chronic_ratio,
            training_consistency,
            avg_sleep_hours,
            sleep_consistency,
            avg_avg_hr,
            avg_max_hr,
            avg_spo2,
            avg_systolic,
            avg_diastolic,
            avg_feeling_score,
            athlete_age,
            athlete_weight_kg,
            athlete_height_cm,
        ) = normalized

        ratio_balance = _clamp(100.0 - abs(acute_chronic_ratio - 1.05) * 85.0)
        hr_efficiency = _clamp(100.0 - max(0.0, avg_avg_hr - 145.0) * 1.5)
        pressure_balance = _clamp(
            100.0
            - max(0.0, avg_systolic - 120.0) * 1.8
            - max(0.0, avg_diastolic - 80.0) * 2.5
        )
        feeling_score = _clamp(avg_feeling_score * 10.0)
        sleep_score = _clamp(avg_sleep_hours * 12.5)
        age_modifier = _clamp(100.0 - max(0.0, athlete_age - 32.0) * 0.9)
        body_balance = _clamp(
            100.0
            - max(0.0, athlete_weight_kg - 95.0) * 0.5
            - abs(athlete_height_cm - 175.0) * 0.1
        )

        if self.kind == "load":
            score = (
                0.24 * recent_load
                + 0.22 * chronic_load
                + 0.18 * ratio_balance
                + 0.16 * training_consistency
                + 0.10 * feeling_score
                + 0.06 * hr_efficiency
                + 0.04 * age_modifier
            )
            return _clamp(score)

        if self.kind == "recovery":
            score = (
                0.34 * sleep_score
                + 0.18 * sleep_consistency
                + 0.15 * feeling_score
                + 0.13 * avg_spo2
                + 0.12 * pressure_balance
                + 0.05 * body_balance
                + 0.03 * age_modifier
            )
            return _clamp(score)

        if self.kind == "cardio":
            max_hr_balance = _clamp(100.0 - abs(avg_max_hr - 175.0) * 0.8)
            score = (
                0.22 * chronic_load
                + 0.18 * hr_efficiency
                + 0.16 * avg_spo2
                + 0.14 * training_consistency
                + 0.12 * feeling_score
                + 0.10 * max_hr_balance
                + 0.04 * body_balance
                + 0.04 * age_modifier
            )
            return _clamp(score)

        raise ValueError(f"Unknown bootstrap tabular model kind: {self.kind}")


def _ensure_2d(values: Any) -> list[list[float]]:
    matrix = _to_nested_list(values)
    if not matrix:
        return [[]]
    if isinstance(matrix[0], list):
        return [[float(item) for item in row] for row in matrix]
    return [[float(item) for item in matrix]]


def _to_nested_list(values: Any) -> list[Any]:
    if np is not None and isinstance(values, np.ndarray):
        return values.tolist()
    if hasattr(values, "tolist"):
        try:
            return values.tolist()
        except Exception:
            pass
    if isinstance(values, list):
        return values
    if isinstance(values, tuple):
        return list(values)
    return [values]


def _to_output_matrix(values: list[list[float]]) -> Any:
    if np is not None:
        return np.asarray(values, dtype=float)
    return values


def _to_output_vector(values: list[float]) -> Any:
    if np is not None:
        return np.asarray(values, dtype=float)
    return values


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))
