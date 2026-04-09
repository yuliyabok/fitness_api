from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ml_service.config import DEFAULT_FEATURE_NAMES, MLServiceSettings

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency in local dev
    np = None

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover - optional dependency in local dev
    ort = None

PredictTarget = Literal["timesfm", "patchtst"]


class AthleteProfileContext(BaseModel):
    age: int | None = None
    gender: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    sport: str | None = None


class TrainingRecord(BaseModel):
    id: str | None = None
    date: date
    title: str | None = None
    training_type: str | None = None
    duration_minutes: float | None = None
    calories: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    feeling_score: float | None = None
    sport: str | None = None


class SleepRecord(BaseModel):
    id: str | None = None
    start_ts: datetime
    end_ts: datetime
    deep_minutes: float | None = None
    light_minutes: float | None = None
    rem_minutes: float | None = None


class BloodPressureRecord(BaseModel):
    id: str | None = None
    ts: datetime
    systolic: float
    diastolic: float
    is_morning: bool | None = None


class Spo2Record(BaseModel):
    id: str | None = None
    ts: datetime
    percentage: float


class PredictionRequest(BaseModel):
    athlete_id: str | None = None
    target: PredictTarget = "timesfm"
    history_limit: int = Field(default=30, ge=1, le=365)
    window_size: int | None = Field(default=None, ge=7, le=365)
    date_from: date | None = None
    date_to: date | None = None
    profile: AthleteProfileContext = Field(default_factory=AthleteProfileContext)
    trainings: list[TrainingRecord] = Field(default_factory=list)
    sleep: list[SleepRecord] = Field(default_factory=list)
    blood_pressure: list[BloodPressureRecord] = Field(default_factory=list)
    spo2: list[Spo2Record] = Field(default_factory=list)


class PredictionResponse(BaseModel):
    target: PredictTarget
    fitness_index: float
    recommendations: list[str]
    window_size: int
    generated_at: datetime


@dataclass
class PredictionContext:
    window_matrix: list[list[float]]
    window_size: int
    avg_sleep_hours: float | None
    avg_systolic: float | None
    avg_diastolic: float | None
    avg_spo2: float | None
    avg_training_minutes: float | None


class _InputMeta:
    def __init__(self, name: str) -> None:
        self.name = name


class DummyHeuristicSession:
    def __init__(self, target: PredictTarget) -> None:
        self._target = target

    def get_inputs(self) -> list[_InputMeta]:
        return [_InputMeta("series")]

    def run(self, _outputs: object, feed: dict[str, object]) -> list[list[list[float]]]:
        series = next(iter(feed.values()))
        if isinstance(series, list):
            batch = series
        elif np is not None and hasattr(series, "tolist"):
            batch = series.tolist()
        else:
            raise ValueError("Unsupported input type for dummy model")

        window = batch[0] if batch else []
        score = _heuristic_score(window, variant=self._target)
        return [[[score]]]


class ModelBundle:
    def __init__(self, settings: MLServiceSettings) -> None:
        self.settings = settings
        self._sessions = self._load_sessions(settings)

    def predict(self, target: PredictTarget, window_matrix: list[list[float]]) -> float:
        session = self._sessions[target]
        input_name = session.get_inputs()[0].name
        payload = [window_matrix]
        if np is not None and ort is not None and not self.settings.use_dummy_models:
            payload = np.asarray(payload, dtype=np.float32)
        output = session.run(None, {input_name: payload})
        return _extract_score(output)

    @staticmethod
    def _load_sessions(settings: MLServiceSettings) -> dict[PredictTarget, object]:
        if settings.use_dummy_models:
            return {
                "timesfm": DummyHeuristicSession("timesfm"),
                "patchtst": DummyHeuristicSession("patchtst"),
            }

        if ort is None:
            raise RuntimeError(
                "onnxruntime is not installed. Install ml_service requirements or enable USE_DUMMY_MODELS=true."
            )
        if np is None:
            raise RuntimeError(
                "numpy is not installed. Install ml_service requirements or enable USE_DUMMY_MODELS=true."
            )

        return {
            "timesfm": _load_onnx_session(settings.resolved_timesfm_model_path),
            "patchtst": _load_onnx_session(settings.resolved_patchtst_model_path),
        }


def create_app(
    settings: MLServiceSettings | None = None,
    *,
    model_bundle: ModelBundle | None = None,
) -> FastAPI:
    resolved_settings = settings or MLServiceSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved_settings
        app.state.model_bundle = model_bundle or ModelBundle(resolved_settings)
        yield

    app = FastAPI(
        title="Fitness Analyzer ML Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    if model_bundle is not None:
        app.state.model_bundle = model_bundle

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/predict", response_model=PredictionResponse)
    def predict(request: PredictionRequest, raw_request: Request) -> PredictionResponse:
        settings_from_app: MLServiceSettings = raw_request.app.state.settings
        bundle: ModelBundle | None = getattr(raw_request.app.state, "model_bundle", None)
        if bundle is None:
            bundle = ModelBundle(settings_from_app)
            raw_request.app.state.model_bundle = bundle
        context = _build_prediction_context(request, settings_from_app)
        predicted_index = bundle.predict(request.target, context.window_matrix)
        recommendations = _build_recommendations(request, context, predicted_index)
        return PredictionResponse(
            target=request.target,
            fitness_index=round(max(0.0, min(100.0, predicted_index)), 2),
            recommendations=recommendations,
            window_size=context.window_size,
            generated_at=datetime.now(timezone.utc),
        )

    return app


def _load_onnx_session(model_path: Path):
    if not model_path.exists():
        raise RuntimeError(f"Model file not found: {model_path}")
    assert ort is not None
    return ort.InferenceSession(str(model_path))


def _extract_score(output: object) -> float:
    if isinstance(output, (int, float)):
        return float(output)
    if np is not None and hasattr(output, "tolist"):
        return _extract_score(output.tolist())
    if isinstance(output, (list, tuple)):
        if not output:
            raise ValueError("Model returned empty output")
        return _extract_score(output[0])
    raise ValueError(f"Unexpected model output type: {type(output)!r}")


def _build_prediction_context(
    request: PredictionRequest,
    settings: MLServiceSettings,
) -> PredictionContext:
    effective_window_size = request.window_size or settings.window_size
    end_date = _resolve_end_date(request)
    start_date = end_date - timedelta(days=effective_window_size - 1)

    daily = defaultdict(
        lambda: {
            "training_duration_minutes": 0.0,
            "training_calories": 0.0,
            "training_avg_hr_sum": 0.0,
            "training_avg_hr_count": 0,
            "training_max_hr": 0.0,
            "training_feeling_score_sum": 0.0,
            "training_feeling_score_count": 0,
            "sleep_minutes": 0.0,
            "sleep_deep_minutes": 0.0,
            "sleep_rem_minutes": 0.0,
            "blood_pressure_systolic_sum": 0.0,
            "blood_pressure_diastolic_sum": 0.0,
            "blood_pressure_count": 0,
            "spo2_percentage_sum": 0.0,
            "spo2_count": 0,
        }
    )

    for entry in request.trainings[-request.history_limit :]:
        day = entry.date
        if day < start_date or day > end_date:
            continue
        bucket = daily[day]
        bucket["training_duration_minutes"] += entry.duration_minutes or 0.0
        bucket["training_calories"] += entry.calories or 0.0
        if entry.avg_hr is not None:
            bucket["training_avg_hr_sum"] += entry.avg_hr
            bucket["training_avg_hr_count"] += 1
        if entry.max_hr is not None:
            bucket["training_max_hr"] = max(bucket["training_max_hr"], entry.max_hr)
        if entry.feeling_score is not None:
            bucket["training_feeling_score_sum"] += entry.feeling_score
            bucket["training_feeling_score_count"] += 1

    for entry in request.sleep[-request.history_limit :]:
        day = entry.end_ts.date()
        if day < start_date or day > end_date:
            continue
        bucket = daily[day]
        sleep_minutes = max(0.0, (entry.end_ts - entry.start_ts).total_seconds() / 60.0)
        bucket["sleep_minutes"] += sleep_minutes
        bucket["sleep_deep_minutes"] += entry.deep_minutes or 0.0
        bucket["sleep_rem_minutes"] += entry.rem_minutes or 0.0

    for entry in request.blood_pressure[-request.history_limit :]:
        day = entry.ts.date()
        if day < start_date or day > end_date:
            continue
        bucket = daily[day]
        bucket["blood_pressure_systolic_sum"] += entry.systolic
        bucket["blood_pressure_diastolic_sum"] += entry.diastolic
        bucket["blood_pressure_count"] += 1

    for entry in request.spo2[-request.history_limit :]:
        day = entry.ts.date()
        if day < start_date or day > end_date:
            continue
        bucket = daily[day]
        bucket["spo2_percentage_sum"] += entry.percentage
        bucket["spo2_count"] += 1

    means = settings.normalized_means()
    stds = settings.normalized_stds()
    window_matrix: list[list[float]] = []
    dates = [start_date + timedelta(days=i) for i in range(effective_window_size)]
    for current_day in dates:
        bucket = daily[current_day]
        feature_values = [
            bucket["training_duration_minutes"],
            bucket["training_calories"],
            _safe_average(bucket["training_avg_hr_sum"], bucket["training_avg_hr_count"]),
            bucket["training_max_hr"],
            _safe_average(
                bucket["training_feeling_score_sum"],
                bucket["training_feeling_score_count"],
            ),
            bucket["sleep_minutes"],
            bucket["sleep_deep_minutes"],
            bucket["sleep_rem_minutes"],
            _safe_average(
                bucket["blood_pressure_systolic_sum"],
                bucket["blood_pressure_count"],
            ),
            _safe_average(
                bucket["blood_pressure_diastolic_sum"],
                bucket["blood_pressure_count"],
            ),
            _safe_average(bucket["spo2_percentage_sum"], bucket["spo2_count"]),
            float(request.profile.age or 0),
            float(request.profile.weight_kg or 0),
            float(request.profile.height_cm or 0),
        ]
        normalized = [
            (value - means[index]) / stds[index]
            for index, value in enumerate(feature_values)
        ]
        window_matrix.append(normalized)

    recent_rows = window_matrix[-7:]
    avg_sleep_hours = _mean([row[5] * stds[5] + means[5] for row in recent_rows if row])
    avg_systolic = _mean([row[8] * stds[8] + means[8] for row in recent_rows if row])
    avg_diastolic = _mean([row[9] * stds[9] + means[9] for row in recent_rows if row])
    avg_spo2 = _mean([row[10] * stds[10] + means[10] for row in recent_rows if row and (row[10] * stds[10] + means[10]) > 0])
    avg_training_minutes = _mean([row[0] * stds[0] + means[0] for row in recent_rows if row])

    return PredictionContext(
        window_matrix=window_matrix,
        window_size=effective_window_size,
        avg_sleep_hours=(avg_sleep_hours / 60.0) if avg_sleep_hours is not None else None,
        avg_systolic=avg_systolic,
        avg_diastolic=avg_diastolic,
        avg_spo2=avg_spo2,
        avg_training_minutes=avg_training_minutes,
    )


def _resolve_end_date(request: PredictionRequest) -> date:
    if request.date_to is not None:
        return request.date_to
    candidates: list[date] = []
    candidates.extend(entry.date for entry in request.trainings)
    candidates.extend(entry.end_ts.date() for entry in request.sleep)
    candidates.extend(entry.ts.date() for entry in request.blood_pressure)
    candidates.extend(entry.ts.date() for entry in request.spo2)
    return max(candidates, default=datetime.now(timezone.utc).date())


def _build_recommendations(
    request: PredictionRequest,
    context: PredictionContext,
    predicted_index: float,
) -> list[str]:
    recommendations: list[str] = []
    if context.avg_sleep_hours is not None and context.avg_sleep_hours < 7.0:
        recommendations.append("Увеличьте продолжительность сна до 7-9 часов для лучшего восстановления.")
    if (
        context.avg_systolic is not None
        and context.avg_diastolic is not None
        and (context.avg_systolic >= 135 or context.avg_diastolic >= 85)
    ):
        recommendations.append("Снизьте интенсивность ближайших тренировок и проконтролируйте давление.")
    if context.avg_spo2 is not None and context.avg_spo2 < 95:
        recommendations.append("Добавьте больше восстановительных прогулок и проверьте качество дыхания во сне.")
    if (context.avg_training_minutes or 0) < 30:
        recommendations.append("Добавьте 2-3 умеренные аэробные тренировки в неделю для роста формы.")

    sport = (request.profile.sport or "").strip()
    if predicted_index < 45:
        recommendations.append("Сделайте восстановительный микроцикл и избегайте резкого увеличения объема.")
    elif predicted_index < 70:
        recommendations.append("Форма улучшается: сохраняйте умеренную прогрессию нагрузки и контроль восстановления.")
    else:
        recommendations.append("Текущая форма высокая: можно планировать акцентную тренировку при хорошем самочувствии.")

    if sport:
        recommendations.append(f"Учитывайте специфику вида спорта: {sport}.")

    return recommendations[:4]


def _heuristic_score(window_matrix: list[list[float]], *, variant: PredictTarget) -> float:
    raw_rows = window_matrix[-14:] if len(window_matrix) > 14 else window_matrix
    if not raw_rows:
        return 50.0

    avg_training = _mean(row[0] for row in raw_rows) or 0.0
    avg_sleep = _mean(row[5] for row in raw_rows) or 0.0
    avg_pressure_penalty = ((_mean(row[8] for row in raw_rows) or 0.0) * 0.2) + (
        (_mean(row[9] for row in raw_rows) or 0.0) * 0.25
    )
    avg_spo2 = _mean(row[10] for row in raw_rows) or 0.0

    base = 55.0 + (avg_training * 3.8) + (avg_sleep * 0.08) + (avg_spo2 * 1.6) - avg_pressure_penalty
    if variant == "patchtst":
        trend = 0.0
        if len(raw_rows) >= 2:
            trend = raw_rows[-1][0] - raw_rows[-2][0]
        base += trend * 2.5 + 2.0
    return max(0.0, min(100.0, base))


def _safe_average(total: float, count: int) -> float:
    return total / count if count else 0.0


def _mean(values) -> float | None:
    seq = list(values)
    if not seq:
        return None
    return sum(seq) / len(seq)


app = create_app()
