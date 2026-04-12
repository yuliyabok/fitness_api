from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.analysis import AnalysisEntry  # noqa: E402
from app.models.blood_pressure import BloodPressureEntry  # noqa: E402
from app.models.sleep import SleepEntry  # noqa: E402
from app.models.spo2 import Spo2Entry  # noqa: E402
from app.models.training import Training  # noqa: E402
from app.models.user import AthleteProfile  # noqa: E402
from ml_service.config import SEQUENCE_FEATURE_NAMES, TABULAR_FEATURE_NAMES  # noqa: E402
from ml_service.services.bootstrap_tabular import BootstrapTabularModel, BootstrapTabularScaler  # noqa: E402

TARGET_NAMES = (
    "load_score_target",
    "recovery_score_target",
    "cardio_score_target",
    "fitness_index_target",
    "fatigue_risk_target",
    "trend_target",
    "analysis_label",
)


@dataclass(slots=True)
class AthleteContext:
    athlete_id: str
    age: float
    weight_kg: float
    height_cm: float
    sport: str


@dataclass(slots=True)
class DailyObservation:
    training_load: float
    sleep_hours: float
    recovery_signal: float
    cardio_signal: float
    avg_hr: float
    max_hr: float
    spo2: float
    feeling_score: float
    systolic: float
    diastolic: float
    has_training: bool
    has_sleep: bool
    has_pressure: bool
    has_spo2: bool


@dataclass(slots=True)
class WindowSummary:
    sequence_rows: list[list[float]]
    tabular_row: list[float]
    metrics: dict[str, float]


@dataclass(slots=True)
class DatasetSample:
    sample_id: str
    athlete_id: str
    sport: str
    anchor_date: str
    tabular_row: list[float]
    sequence_rows: list[list[float]]
    targets: dict[str, float | str | None]


def main() -> None:
    args = parse_args()
    database_url = resolve_database_url(args.database_url)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    with Session(engine) as session:
        samples = build_samples(
            session=session,
            athlete_ids=parse_athlete_ids(args.athlete_ids),
            window_size=args.window_size,
            horizon_days=args.horizon_days,
            short_horizon_days=args.short_horizon_days,
            min_history_completeness=args.min_history_completeness,
            min_future_completeness=args.min_future_completeness,
            min_samples_per_athlete=args.min_samples_per_athlete,
            date_from=args.date_from,
            date_to=args.date_to,
        )

    if not samples:
        raise SystemExit("No dataset samples were generated. Lower completeness thresholds or widen the date range.")

    split_samples = split_by_time(samples, train_ratio=args.train_ratio, val_ratio=args.val_ratio)
    for split_name, split_items in split_samples.items():
        export_split(output_dir=output_dir, split_name=split_name, samples=split_items)

    export_manifest(
        output_dir=output_dir,
        split_samples=split_samples,
        args=args,
    )
    print(f"Dataset exported to {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build supervised proxy datasets for fitness ML training from the current PostgreSQL schema. "
            "The script exports tabular CSV files and sequence NPZ files for train/val/test."
        )
    )
    parser.add_argument("--database-url", help="PostgreSQL SQLAlchemy URL. Defaults to DATABASE_URL or backend/.env.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml_service/datasets"),
        help="Directory where train/val/test artifacts will be saved.",
    )
    parser.add_argument("--window-size", type=int, default=30, help="History window in days for every sample.")
    parser.add_argument("--horizon-days", type=int, default=7, help="Future horizon used to generate proxy targets.")
    parser.add_argument(
        "--short-horizon-days",
        type=int,
        default=7,
        help="Short horizon used inside feature summarization.",
    )
    parser.add_argument(
        "--min-history-completeness",
        type=float,
        default=0.20,
        help="Minimum history completeness ratio in the feature window.",
    )
    parser.add_argument(
        "--min-future-completeness",
        type=float,
        default=0.15,
        help="Minimum future completeness ratio in the target horizon.",
    )
    parser.add_argument(
        "--min-samples-per-athlete",
        type=int,
        default=5,
        help="Skip athletes with fewer usable windows than this threshold.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Train split ratio.")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Validation split ratio.")
    parser.add_argument("--athlete-ids", help="Comma-separated list of athlete UUIDs to include.")
    parser.add_argument("--date-from", type=parse_date, help="Optional lower bound for anchor dates.")
    parser.add_argument("--date-to", type=parse_date, help="Optional upper bound for anchor dates.")
    return parser.parse_args()


def build_samples(
    *,
    session: Session,
    athlete_ids: set[str] | None,
    window_size: int,
    horizon_days: int,
    short_horizon_days: int,
    min_history_completeness: float,
    min_future_completeness: float,
    min_samples_per_athlete: int,
    date_from: date | None,
    date_to: date | None,
) -> list[DatasetSample]:
    athlete_contexts = load_athlete_contexts(session, athlete_ids=athlete_ids)
    daily_observations = load_daily_observations(session, athlete_ids=set(athlete_contexts), date_from=date_from, date_to=date_to)
    analysis_labels = load_analysis_labels(session, athlete_ids=set(athlete_contexts), date_from=date_from, date_to=date_to)

    scaler = BootstrapTabularScaler()
    load_model = BootstrapTabularModel("load")
    recovery_model = BootstrapTabularModel("recovery")
    cardio_model = BootstrapTabularModel("cardio")

    samples: list[DatasetSample] = []

    for athlete_id, context in athlete_contexts.items():
        observations_by_day = daily_observations.get(athlete_id, {})
        if not observations_by_day:
            continue

        available_dates = sorted(observations_by_day)
        first_anchor = available_dates[0] + timedelta(days=window_size - 1)
        last_anchor = available_dates[-1] - timedelta(days=horizon_days)
        if date_from is not None:
            first_anchor = max(first_anchor, date_from)
        if date_to is not None:
            last_anchor = min(last_anchor, date_to)
        if first_anchor > last_anchor:
            continue

        athlete_samples: list[DatasetSample] = []
        current_date = first_anchor
        while current_date <= last_anchor:
            history_dates = [current_date - timedelta(days=offset) for offset in range(window_size - 1, -1, -1)]
            future_dates = [current_date + timedelta(days=offset) for offset in range(1, horizon_days + 1)]

            history_window = [observations_by_day.get(day, DailyObservation(**DEFAULT_DAILY_VALUES)) for day in history_dates]
            future_window = [observations_by_day.get(day, DailyObservation(**DEFAULT_DAILY_VALUES)) for day in future_dates]

            history_summary = summarize_window(history_window, context=context, short_horizon_days=short_horizon_days)
            future_summary = summarize_window(future_window, context=context, short_horizon_days=min(short_horizon_days, horizon_days))

            if history_summary.metrics["data_completeness"] < min_history_completeness * 100.0:
                current_date += timedelta(days=1)
                continue
            if future_summary.metrics["data_completeness"] < min_future_completeness * 100.0:
                current_date += timedelta(days=1)
                continue

            future_scaled = scaler.transform([future_summary.tabular_row])
            load_target = float(first_value(load_model.predict(future_scaled)))
            recovery_target = float(first_value(recovery_model.predict(future_scaled)))
            cardio_target = float(first_value(cardio_model.predict(future_scaled)))

            trend_target = resolve_trend(
                history_metrics=history_summary.metrics,
                future_metrics=future_summary.metrics,
            )
            fitness_index_target = clamp(
                0.30 * load_target
                + 0.36 * recovery_target
                + 0.34 * cardio_target
                + trend_adjustment(trend_target)
            )
            fatigue_risk_target = clamp(
                0.55 * (100.0 - recovery_target)
                + 0.25 * max(0.0, (future_summary.metrics["acute_chronic_ratio"] - 1.0) * 55.0)
                + 0.20 * max(0.0, future_summary.metrics["recent_load"] - history_summary.metrics["recent_load"])
                + (8.0 if trend_target == "down" else 0.0)
            )

            sample_id = f"{athlete_id}:{current_date.isoformat()}"
            athlete_samples.append(
                DatasetSample(
                    sample_id=sample_id,
                    athlete_id=athlete_id,
                    sport=context.sport,
                    anchor_date=current_date.isoformat(),
                    tabular_row=history_summary.tabular_row,
                    sequence_rows=history_summary.sequence_rows,
                    targets={
                        "load_score_target": round(load_target, 4),
                        "recovery_score_target": round(recovery_target, 4),
                        "cardio_score_target": round(cardio_target, 4),
                        "fitness_index_target": round(fitness_index_target, 4),
                        "fatigue_risk_target": round(fatigue_risk_target, 4),
                        "trend_target": trend_target,
                        "analysis_label": analysis_labels.get((athlete_id, current_date.isoformat())),
                    },
                )
            )
            current_date += timedelta(days=1)

        if len(athlete_samples) >= min_samples_per_athlete:
            samples.extend(athlete_samples)

    samples.sort(key=lambda item: (item.anchor_date, item.athlete_id))
    return samples


def load_athlete_contexts(session: Session, athlete_ids: set[str] | None) -> dict[str, AthleteContext]:
    query = select(AthleteProfile)
    if athlete_ids:
        query = query.where(AthleteProfile.user_id.in_([UUID(item) for item in athlete_ids]))

    contexts: dict[str, AthleteContext] = {}
    for profile in session.execute(query).scalars():
        athlete_id = str(profile.user_id)
        contexts[athlete_id] = AthleteContext(
            athlete_id=athlete_id,
            age=float(profile.age or 0.0),
            weight_kg=float(profile.weight_kg or 0.0),
            height_cm=float(profile.height_cm or 0.0),
            sport=(profile.sport or "unknown").strip() or "unknown",
        )
    return contexts


def load_daily_observations(
    session: Session,
    *,
    athlete_ids: set[str],
    date_from: date | None,
    date_to: date | None,
) -> dict[str, dict[date, DailyObservation]]:
    if not athlete_ids:
        return {}

    parsed_ids = [UUID(item) for item in athlete_ids]
    trainings_by_day: defaultdict[tuple[str, date], list[Training]] = defaultdict(list)
    sleep_by_day: defaultdict[tuple[str, date], list[SleepEntry]] = defaultdict(list)
    pressure_by_day: defaultdict[tuple[str, date], list[BloodPressureEntry]] = defaultdict(list)
    spo2_by_day: defaultdict[tuple[str, date], list[Spo2Entry]] = defaultdict(list)

    training_query = select(Training).where(Training.athlete_id.in_(parsed_ids))
    if date_from is not None:
        training_query = training_query.where(Training.date >= date_from - timedelta(days=90))
    if date_to is not None:
        training_query = training_query.where(Training.date <= date_to + timedelta(days=30))
    for item in session.execute(training_query).scalars():
        trainings_by_day[(str(item.athlete_id), item.date)].append(item)

    sleep_query = select(SleepEntry).where(SleepEntry.athlete_id.in_(parsed_ids))
    if date_from is not None:
        sleep_query = sleep_query.where(SleepEntry.end_ts >= datetime.combine(date_from - timedelta(days=90), datetime.min.time()))
    if date_to is not None:
        sleep_query = sleep_query.where(SleepEntry.end_ts <= datetime.combine(date_to + timedelta(days=30), datetime.max.time()))
    for item in session.execute(sleep_query).scalars():
        sleep_by_day[(str(item.athlete_id), item.end_ts.date())].append(item)

    pressure_query = select(BloodPressureEntry).where(BloodPressureEntry.athlete_id.in_(parsed_ids))
    if date_from is not None:
        pressure_query = pressure_query.where(BloodPressureEntry.ts >= datetime.combine(date_from - timedelta(days=90), datetime.min.time()))
    if date_to is not None:
        pressure_query = pressure_query.where(BloodPressureEntry.ts <= datetime.combine(date_to + timedelta(days=30), datetime.max.time()))
    for item in session.execute(pressure_query).scalars():
        pressure_by_day[(str(item.athlete_id), item.ts.date())].append(item)

    spo2_query = select(Spo2Entry).where(Spo2Entry.athlete_id.in_(parsed_ids))
    if date_from is not None:
        spo2_query = spo2_query.where(Spo2Entry.ts >= datetime.combine(date_from - timedelta(days=90), datetime.min.time()))
    if date_to is not None:
        spo2_query = spo2_query.where(Spo2Entry.ts <= datetime.combine(date_to + timedelta(days=30), datetime.max.time()))
    for item in session.execute(spo2_query).scalars():
        spo2_by_day[(str(item.athlete_id), item.ts.date())].append(item)

    keys = set(trainings_by_day) | set(sleep_by_day) | set(pressure_by_day) | set(spo2_by_day)
    observations: dict[str, dict[date, DailyObservation]] = defaultdict(dict)
    for athlete_id, day in sorted(keys):
        training_rows = trainings_by_day.get((athlete_id, day), [])
        sleep_rows = sleep_by_day.get((athlete_id, day), [])
        pressure_rows = pressure_by_day.get((athlete_id, day), [])
        spo2_rows = spo2_by_day.get((athlete_id, day), [])

        duration_minutes = sum((item.duration_minutes or 0) for item in training_rows)
        calories = sum((item.calories or 0) for item in training_rows)
        avg_hr = mean([float(item.avg_hr) for item in training_rows if item.avg_hr is not None])
        max_hr = max_value([float(item.max_hr) for item in training_rows if item.max_hr is not None])
        feeling_score = mean([float(item.feeling_score) for item in training_rows if item.feeling_score is not None])

        sleep_hours = sum(sleep_duration_hours(item) for item in sleep_rows)
        systolic = mean([float(item.systolic) for item in pressure_rows if item.systolic is not None])
        diastolic = mean([float(item.diastolic) for item in pressure_rows if item.diastolic is not None])
        spo2 = mean([float(item.percentage) for item in spo2_rows if item.percentage is not None])

        training_load = clamp(
            duration_minutes * 0.6
            + calories * 0.04
            + max(0.0, avg_hr - 110.0) * 0.35
            + max(0.0, max_hr - 150.0) * 0.10
        )
        recovery_signal = clamp(
            20.0
            + sleep_hours * 7.0
            + feeling_score * 5.0
            + max(0.0, spo2 - 94.0) * 6.0
            - max(0.0, systolic - 120.0) * 0.6
            - max(0.0, diastolic - 80.0) * 0.9
        )
        cardio_signal = clamp(
            15.0
            + duration_minutes * 0.35
            + max(0.0, 155.0 - avg_hr) * 0.45
            + max(0.0, spo2 - 92.0) * 4.0
            + max(0.0, 60.0 - abs(duration_minutes - 60.0)) * 0.15
        )

        observations[athlete_id][day] = DailyObservation(
            training_load=training_load,
            sleep_hours=sleep_hours,
            recovery_signal=recovery_signal,
            cardio_signal=cardio_signal,
            avg_hr=avg_hr,
            max_hr=max_hr,
            spo2=spo2,
            feeling_score=feeling_score,
            systolic=systolic,
            diastolic=diastolic,
            has_training=training_load > 0,
            has_sleep=sleep_hours > 0,
            has_pressure=systolic > 0 or diastolic > 0,
            has_spo2=spo2 > 0,
        )
    return observations


def load_analysis_labels(
    session: Session,
    *,
    athlete_ids: set[str],
    date_from: date | None,
    date_to: date | None,
) -> dict[tuple[str, str], str]:
    if not athlete_ids:
        return {}

    parsed_ids = [UUID(item) for item in athlete_ids]
    query = select(AnalysisEntry).where(AnalysisEntry.athlete_id.in_(parsed_ids))
    if date_from is not None:
        query = query.where(AnalysisEntry.date >= date_from)
    if date_to is not None:
        query = query.where(AnalysisEntry.date <= date_to)

    labels: dict[tuple[str, str], str] = {}
    for item in session.execute(query).scalars():
        value = (item.value or item.title or "").strip()
        if value:
            labels[(str(item.athlete_id), item.date.isoformat())] = value
    return labels


def summarize_window(
    observations: list[DailyObservation],
    *,
    context: AthleteContext,
    short_horizon_days: int,
) -> WindowSummary:
    sequence_rows = [
        [
            item.training_load,
            item.sleep_hours,
            item.recovery_signal,
            item.cardio_signal,
            item.avg_hr,
            item.max_hr,
            item.spo2,
            item.feeling_score,
        ]
        for item in observations
    ]

    daily_training_loads = [item.training_load for item in observations]
    daily_sleep_hours = [item.sleep_hours for item in observations]
    daily_recovery_scores = [item.recovery_signal for item in observations]
    daily_cardio_scores = [item.cardio_signal for item in observations]
    avg_hrs = [item.avg_hr for item in observations if item.avg_hr > 0]
    max_hrs = [item.max_hr for item in observations if item.max_hr > 0]
    spo2_values = [item.spo2 for item in observations if item.spo2 > 0]
    systolic_values = [item.systolic for item in observations if item.systolic > 0]
    diastolic_values = [item.diastolic for item in observations if item.diastolic > 0]
    feeling_values = [item.feeling_score for item in observations if item.feeling_score > 0]
    training_days = sum(1 for item in observations if item.has_training)
    sleep_days = sum(1 for item in observations if item.has_sleep)
    pressure_days = sum(1 for item in observations if item.has_pressure)
    spo2_days = sum(1 for item in observations if item.has_spo2)

    effective_window = max(1, len(observations))
    recent_window = min(short_horizon_days, effective_window)
    previous_window = min(recent_window, max(1, effective_window - recent_window))

    recent_load = mean(daily_training_loads[-recent_window:])
    chronic_load = mean(daily_training_loads)
    previous_load = (
        mean(daily_training_loads[-(recent_window + previous_window):-recent_window])
        if effective_window > recent_window
        else chronic_load
    )
    recent_recovery = mean(daily_recovery_scores[-recent_window:])
    previous_recovery = (
        mean(daily_recovery_scores[-(recent_window + previous_window):-recent_window])
        if effective_window > recent_window
        else mean(daily_recovery_scores)
    )
    recent_cardio = mean(daily_cardio_scores[-recent_window:])
    previous_cardio = (
        mean(daily_cardio_scores[-(recent_window + previous_window):-recent_window])
        if effective_window > recent_window
        else mean(daily_cardio_scores)
    )

    avg_sleep_hours = mean(daily_sleep_hours, default=7.0)
    sleep_consistency = clamp(100.0 - std_dev(daily_sleep_hours or [7.0]) * 18.0)
    training_consistency = clamp(training_days / effective_window * 100.0)
    acute_chronic_ratio = recent_load / chronic_load if chronic_load > 0 else (1.0 if recent_load == 0 else 1.35)
    avg_avg_hr = mean(avg_hrs, default=135.0)
    avg_max_hr = mean(max_hrs, default=165.0)
    avg_spo2 = mean(spo2_values, default=97.0)
    avg_systolic = mean(systolic_values, default=120.0)
    avg_diastolic = mean(diastolic_values, default=80.0)
    avg_feeling_score = mean(feeling_values, default=6.5)
    trend_signal = (
        (recent_recovery - previous_recovery) * 0.55
        + (recent_cardio - previous_cardio) * 0.45
        - max(0.0, recent_load - previous_load) * 0.35
    )
    data_completeness = clamp(
        (training_days + sleep_days + pressure_days + spo2_days) / (effective_window * 4) * 100.0
    )

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
        context.age,
        context.weight_kg,
        context.height_cm,
    ]
    metrics = {
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
    }
    return WindowSummary(sequence_rows=sequence_rows, tabular_row=tabular_row, metrics=metrics)


def split_by_time(
    samples: list[DatasetSample],
    *,
    train_ratio: float,
    val_ratio: float,
) -> dict[str, list[DatasetSample]]:
    unique_dates = sorted({item.anchor_date for item in samples})
    if len(unique_dates) < 3:
        return {"train": samples, "val": [], "test": []}

    train_index = max(0, min(len(unique_dates) - 1, math.floor(len(unique_dates) * train_ratio) - 1))
    val_index = max(train_index + 1, min(len(unique_dates) - 1, math.floor(len(unique_dates) * (train_ratio + val_ratio)) - 1))

    train_cutoff = unique_dates[train_index]
    val_cutoff = unique_dates[val_index]

    split_samples = {"train": [], "val": [], "test": []}
    for item in samples:
        if item.anchor_date <= train_cutoff:
            split_samples["train"].append(item)
        elif item.anchor_date <= val_cutoff:
            split_samples["val"].append(item)
        else:
            split_samples["test"].append(item)
    return split_samples


def export_split(*, output_dir: Path, split_name: str, samples: list[DatasetSample]) -> None:
    tabular_path = output_dir / f"tabular_{split_name}.csv"
    sequence_path = output_dir / f"sequence_{split_name}.npz"

    fieldnames = [
        "sample_id",
        "athlete_id",
        "sport",
        "anchor_date",
        *TABULAR_FEATURE_NAMES,
        *TARGET_NAMES,
    ]
    with tabular_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for item in samples:
            row = {
                "sample_id": item.sample_id,
                "athlete_id": item.athlete_id,
                "sport": item.sport,
                "anchor_date": item.anchor_date,
            }
            row.update({name: item.tabular_row[index] for index, name in enumerate(TABULAR_FEATURE_NAMES)})
            row.update(item.targets)
            writer.writerow(row)

    if not samples:
        np.savez_compressed(
            sequence_path,
            X=np.empty((0, 0, 0), dtype=np.float32),
            athlete_ids=np.asarray([], dtype=str),
            anchor_dates=np.asarray([], dtype=str),
            sample_ids=np.asarray([], dtype=str),
            sports=np.asarray([], dtype=str),
            **{name: np.asarray([], dtype=np.float32 if name != "trend_target" and name != "analysis_label" else str) for name in TARGET_NAMES},
        )
        return

    sequence_array = np.asarray([item.sequence_rows for item in samples], dtype=np.float32)
    np.savez_compressed(
        sequence_path,
        X=sequence_array,
        athlete_ids=np.asarray([item.athlete_id for item in samples], dtype=str),
        anchor_dates=np.asarray([item.anchor_date for item in samples], dtype=str),
        sample_ids=np.asarray([item.sample_id for item in samples], dtype=str),
        sports=np.asarray([item.sport for item in samples], dtype=str),
        load_score_target=np.asarray([float(item.targets["load_score_target"]) for item in samples], dtype=np.float32),
        recovery_score_target=np.asarray([float(item.targets["recovery_score_target"]) for item in samples], dtype=np.float32),
        cardio_score_target=np.asarray([float(item.targets["cardio_score_target"]) for item in samples], dtype=np.float32),
        fitness_index_target=np.asarray([float(item.targets["fitness_index_target"]) for item in samples], dtype=np.float32),
        fatigue_risk_target=np.asarray([float(item.targets["fatigue_risk_target"]) for item in samples], dtype=np.float32),
        trend_target=np.asarray([str(item.targets["trend_target"]) for item in samples], dtype=str),
        analysis_label=np.asarray([str(item.targets["analysis_label"] or "") for item in samples], dtype=str),
    )


def export_manifest(*, output_dir: Path, split_samples: dict[str, list[DatasetSample]], args: argparse.Namespace) -> None:
    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "config": {
            "window_size": args.window_size,
            "horizon_days": args.horizon_days,
            "short_horizon_days": args.short_horizon_days,
            "min_history_completeness": args.min_history_completeness,
            "min_future_completeness": args.min_future_completeness,
            "min_samples_per_athlete": args.min_samples_per_athlete,
            "train_ratio": args.train_ratio,
            "val_ratio": args.val_ratio,
            "date_from": args.date_from.isoformat() if args.date_from else None,
            "date_to": args.date_to.isoformat() if args.date_to else None,
        },
        "features": {
            "tabular": list(TABULAR_FEATURE_NAMES),
            "sequence": list(SEQUENCE_FEATURE_NAMES),
            "targets": list(TARGET_NAMES),
        },
        "split_counts": {name: len(items) for name, items in split_samples.items()},
        "athlete_counts": {
            name: len({item.athlete_id for item in items})
            for name, items in split_samples.items()
        },
        "notes": [
            "Targets are proxy labels generated from future windows, not human-annotated ground truth.",
            "Use this dataset to bootstrap tabular baselines first, then fine-tune sequence models.",
            "If expert labels become available, replace analysis_label/proxy targets with true supervision.",
        ],
    }
    (output_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_trend(*, history_metrics: dict[str, float], future_metrics: dict[str, float]) -> str:
    trend_signal = (
        (future_metrics["recent_recovery"] - history_metrics["recent_recovery"]) * 0.45
        + (future_metrics["recent_cardio"] - history_metrics["recent_cardio"]) * 0.35
        - max(0.0, future_metrics["recent_load"] - history_metrics["recent_load"]) * 0.20
    )
    if trend_signal >= 3.0:
        return "up"
    if trend_signal <= -3.0:
        return "down"
    return "stable"


def trend_adjustment(trend: str) -> float:
    if trend == "up":
        return 3.0
    if trend == "down":
        return -3.0
    return 0.0


def resolve_database_url(explicit_value: str | None) -> str:
    value = explicit_value or os.getenv("DATABASE_URL") or load_database_url_from_env_file(BACKEND_ROOT / ".env")
    if not value:
        raise SystemExit("DATABASE_URL is not set. Pass --database-url or define it in backend/.env.")
    normalized = value.strip()
    if normalized.startswith("postgres://"):
        return "postgresql+psycopg://" + normalized[len("postgres://"):]
    if normalized.startswith("postgresql://") and "postgresql+" not in normalized:
        return "postgresql+psycopg://" + normalized[len("postgresql://"):]
    return normalized


def load_database_url_from_env_file(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "DATABASE_URL":
            return value.strip()
    return None


def parse_athlete_ids(raw_value: str | None) -> set[str] | None:
    if not raw_value:
        return None
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def sleep_duration_hours(item: SleepEntry) -> float:
    duration_hours = (item.end_ts - item.start_ts).total_seconds() / 3600.0
    if duration_hours > 0:
        return duration_hours
    staged_minutes = float(item.deep_minutes or 0) + float(item.light_minutes or 0) + float(item.rem_minutes or 0)
    return staged_minutes / 60.0


def mean(values: list[float], *, default: float = 0.0) -> float:
    if not values:
        return default
    return float(sum(values) / len(values))


def std_dev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def max_value(values: list[float], *, default: float = 0.0) -> float:
    if not values:
        return default
    return max(values)


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def first_value(raw: Any) -> float:
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, list):
        if not raw:
            raise ValueError("Expected a non-empty prediction vector")
        return float(raw[0])
    return float(raw)


DEFAULT_DAILY_VALUES = {
    "training_load": 0.0,
    "sleep_hours": 0.0,
    "recovery_signal": 0.0,
    "cardio_signal": 0.0,
    "avg_hr": 0.0,
    "max_hr": 0.0,
    "spo2": 0.0,
    "feeling_score": 0.0,
    "systolic": 0.0,
    "diastolic": 0.0,
    "has_training": False,
    "has_sleep": False,
    "has_pressure": False,
    "has_spo2": False,
}


if __name__ == "__main__":
    main()
