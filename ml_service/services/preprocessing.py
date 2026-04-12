from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from ml_service.config import MLServiceSettings
from ml_service.schemas import (
    BloodPressureRecord,
    PredictionRequest,
    SleepRecord,
    Spo2Record,
    TrainingRecord,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional during minimal local setup
    np = None


@dataclass(slots=True)
class PreparedInferenceInput:
    window_size: int
    sequence_matrix: object
    tabular_features: object
    metrics: dict[str, float]


def prepare_inference_input(
    request: PredictionRequest,
    settings: MLServiceSettings,
) -> PreparedInferenceInput:
    window_size = min(request.window_size or settings.window_size, request.history_limit)
    end_date = _resolve_end_date(request)
    if request.date_to is not None:
        end_date = request.date_to

    start_date = request.date_from or (end_date - timedelta(days=window_size - 1))
    if start_date > end_date:
        raise ValueError("No data range available for prediction")

    available_days = (end_date - start_date).days + 1
    effective_window = max(1, min(window_size, available_days))
    start_date = end_date - timedelta(days=effective_window - 1)

    trainings_by_day = _group_trainings(request.trainings)
    sleep_by_day = _group_sleep(request.sleep)
    pressure_by_day = _group_blood_pressure(request.blood_pressure)
    spo2_by_day = _group_spo2(request.spo2)

    sequence_rows: list[list[float]] = []
    daily_training_loads: list[float] = []
    daily_sleep_hours: list[float] = []
    daily_recovery_scores: list[float] = []
    daily_cardio_scores: list[float] = []
    avg_hrs: list[float] = []
    max_hrs: list[float] = []
    spo2_values: list[float] = []
    systolic_values: list[float] = []
    diastolic_values: list[float] = []
    feeling_values: list[float] = []
    training_days = 0
    sleep_days = 0
    pressure_days = 0
    spo2_days = 0

    for offset in range(effective_window):
        current_date = start_date + timedelta(days=offset)
        training_rows = trainings_by_day[current_date]
        sleep_rows = sleep_by_day[current_date]
        pressure_rows = pressure_by_day[current_date]
        spo2_rows = spo2_by_day[current_date]

        duration_minutes = sum(item.duration_minutes or 0.0 for item in training_rows)
        calories = sum(item.calories or 0.0 for item in training_rows)
        avg_hr = _mean([item.avg_hr for item in training_rows if item.avg_hr is not None])
        max_hr = _max([item.max_hr for item in training_rows if item.max_hr is not None])
        feeling_score = _mean([item.feeling_score for item in training_rows if item.feeling_score is not None])

        sleep_hours = sum(_sleep_duration_hours(item) for item in sleep_rows)
        systolic = _mean([item.systolic for item in pressure_rows])
        diastolic = _mean([item.diastolic for item in pressure_rows])
        spo2 = _mean([item.percentage for item in spo2_rows])

        training_load = _clamp(
            duration_minutes * 0.6
            + calories * 0.04
            + max(0.0, avg_hr - 110.0) * 0.35
            + max(0.0, max_hr - 150.0) * 0.10
        )
        recovery_signal = _clamp(
            20.0
            + sleep_hours * 7.0
            + feeling_score * 5.0
            + max(0.0, spo2 - 94.0) * 6.0
            - max(0.0, systolic - 120.0) * 0.6
            - max(0.0, diastolic - 80.0) * 0.9
        )
        cardio_signal = _clamp(
            15.0
            + duration_minutes * 0.35
            + max(0.0, 155.0 - avg_hr) * 0.45
            + max(0.0, spo2 - 92.0) * 4.0
            + max(0.0, 60.0 - abs(duration_minutes - 60.0)) * 0.15
        )

        sequence_rows.append(
            [
                training_load,
                sleep_hours,
                recovery_signal,
                cardio_signal,
                avg_hr,
                max_hr,
                spo2,
                feeling_score,
            ]
        )
        daily_training_loads.append(training_load)
        daily_sleep_hours.append(sleep_hours)
        daily_recovery_scores.append(recovery_signal)
        daily_cardio_scores.append(cardio_signal)

        if training_load > 0:
            training_days += 1
        if sleep_hours > 0:
            sleep_days += 1
        if systolic > 0 or diastolic > 0:
            pressure_days += 1
        if spo2 > 0:
            spo2_days += 1

        if avg_hr > 0:
            avg_hrs.append(avg_hr)
        if max_hr > 0:
            max_hrs.append(max_hr)
        if spo2 > 0:
            spo2_values.append(spo2)
        if systolic > 0:
            systolic_values.append(systolic)
        if diastolic > 0:
            diastolic_values.append(diastolic)
        if feeling_score > 0:
            feeling_values.append(feeling_score)

    recent_window = min(settings.short_horizon_days, effective_window)
    previous_window = min(recent_window, max(1, effective_window - recent_window))
    recent_load = _mean(daily_training_loads[-recent_window:])
    chronic_load = _mean(daily_training_loads)
    previous_load = _mean(daily_training_loads[-(recent_window + previous_window):-recent_window]) if effective_window > recent_window else chronic_load
    recent_recovery = _mean(daily_recovery_scores[-recent_window:])
    previous_recovery = _mean(daily_recovery_scores[-(recent_window + previous_window):-recent_window]) if effective_window > recent_window else _mean(daily_recovery_scores)
    recent_cardio = _mean(daily_cardio_scores[-recent_window:])
    previous_cardio = _mean(daily_cardio_scores[-(recent_window + previous_window):-recent_window]) if effective_window > recent_window else _mean(daily_cardio_scores)

    avg_sleep_hours = _mean(daily_sleep_hours, default=7.0)
    sleep_consistency = _clamp(100.0 - _std(daily_sleep_hours or [7.0]) * 18.0)
    training_consistency = _clamp(training_days / effective_window * 100.0)
    acute_chronic_ratio = recent_load / chronic_load if chronic_load > 0 else (1.0 if recent_load == 0 else 1.35)
    avg_avg_hr = _mean(avg_hrs, default=135.0)
    avg_max_hr = _mean(max_hrs, default=165.0)
    avg_spo2 = _mean(spo2_values, default=97.0)
    avg_systolic = _mean(systolic_values, default=120.0)
    avg_diastolic = _mean(diastolic_values, default=80.0)
    avg_feeling_score = _mean(feeling_values, default=6.5)
    trend_signal = (
        (recent_recovery - previous_recovery) * 0.55
        + (recent_cardio - previous_cardio) * 0.45
        - max(0.0, recent_load - previous_load) * 0.35
    )
    data_completeness = _clamp(
        (training_days + sleep_days + pressure_days + spo2_days) / (effective_window * 4) * 100.0
    )

    profile = request.profile
    tabular_row = [
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
        float(profile.age or 0.0),
        float(profile.weight_kg or 0.0),
        float(profile.height_cm or 0.0),
    ]
    tabular_features = _to_array([tabular_row])
    sequence_matrix = _to_array(sequence_rows)

    return PreparedInferenceInput(
        window_size=effective_window,
        sequence_matrix=sequence_matrix,
        tabular_features=tabular_features,
        metrics={
            "recent_load": recent_load,
            "chronic_load": chronic_load,
            "previous_load": previous_load,
            "acute_chronic_ratio": acute_chronic_ratio,
            "training_consistency": training_consistency,
            "avg_sleep_hours": avg_sleep_hours,
            "sleep_consistency": sleep_consistency,
            "avg_spo2": avg_spo2,
            "avg_systolic": avg_systolic,
            "avg_diastolic": avg_diastolic,
            "avg_feeling_score": avg_feeling_score,
            "recent_recovery": recent_recovery,
            "previous_recovery": previous_recovery,
            "recent_cardio": recent_cardio,
            "previous_cardio": previous_cardio,
            "trend_signal": trend_signal,
            "data_completeness": data_completeness,
        },
    )


def _resolve_end_date(request: PredictionRequest) -> date:
    candidates: list[date] = []
    if request.date_to is not None:
        candidates.append(request.date_to)
    candidates.extend(item.date for item in request.trainings)
    candidates.extend(item.end_ts.date() for item in request.sleep)
    candidates.extend(item.ts.date() for item in request.blood_pressure)
    candidates.extend(item.ts.date() for item in request.spo2)
    if candidates:
        return max(candidates)
    return date.today()


def _group_trainings(entries: list[TrainingRecord]) -> defaultdict[date, list[TrainingRecord]]:
    grouped: defaultdict[date, list[TrainingRecord]] = defaultdict(list)
    for entry in entries:
        grouped[entry.date].append(entry)
    return grouped


def _group_sleep(entries: list[SleepRecord]) -> defaultdict[date, list[SleepRecord]]:
    grouped: defaultdict[date, list[SleepRecord]] = defaultdict(list)
    for entry in entries:
        grouped[entry.end_ts.date()].append(entry)
    return grouped


def _group_blood_pressure(
    entries: list[BloodPressureRecord],
) -> defaultdict[date, list[BloodPressureRecord]]:
    grouped: defaultdict[date, list[BloodPressureRecord]] = defaultdict(list)
    for entry in entries:
        grouped[entry.ts.date()].append(entry)
    return grouped


def _group_spo2(entries: list[Spo2Record]) -> defaultdict[date, list[Spo2Record]]:
    grouped: defaultdict[date, list[Spo2Record]] = defaultdict(list)
    for entry in entries:
        grouped[entry.ts.date()].append(entry)
    return grouped


def _sleep_duration_hours(entry: SleepRecord) -> float:
    duration_hours = (entry.end_ts - entry.start_ts).total_seconds() / 3600.0
    if duration_hours > 0:
        return duration_hours
    staged_minutes = (entry.deep_minutes or 0.0) + (entry.light_minutes or 0.0) + (entry.rem_minutes or 0.0)
    return staged_minutes / 60.0


def _mean(values: list[float], *, default: float = 0.0) -> float:
    if not values:
        return default
    return float(sum(values) / len(values))


def _max(values: list[float], *, default: float = 0.0) -> float:
    if not values:
        return default
    return float(max(values))


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _std(values: list[float]) -> float:
    if np is not None:
        return float(np.std(values))
    if not values:
        return 0.0
    mean_value = _mean(values)
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    return variance ** 0.5


def _to_array(values: list[list[float]]) -> object:
    if np is not None:
        return np.asarray(values, dtype=float)
    return [[float(item) for item in row] for row in values]
