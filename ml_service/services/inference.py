from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ml_service.config import MLServiceSettings
from ml_service.services.model_loader import ModelArtifacts
from ml_service.services.preprocessing import PreparedInferenceInput

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional during minimal local setup
    np = None

try:
    import torch
except ImportError:  # pragma: no cover - optional during minimal local setup
    torch = None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PredictionResult:
    load_score: float
    recovery_score: float
    cardio_score: float
    patchtst_score: float
    timesfm_score: float
    fitness_index: float
    fatigue_risk: float
    trend: str


def run_prediction_pipeline(
    *,
    prepared: PreparedInferenceInput,
    models: ModelArtifacts,
    settings: MLServiceSettings,
) -> PredictionResult:
    scaled_features = _apply_scaler(models.scaler, prepared.tabular_features)
    sequence_batch = _wrap_sequence_batch(prepared.sequence_matrix)

    load_score = _clamp(
        _predict_scalar(
            models.load_model,
            scaled_features,
            fallback=prepared.metrics["recent_load"],
            label="load_model",
        )
    )
    recovery_score = _clamp(
        _predict_scalar(
            models.recovery_model,
            scaled_features,
            fallback=prepared.metrics["recent_recovery"],
            label="recovery_model",
        )
    )
    cardio_score = _clamp(
        _predict_scalar(
            models.cardio_model,
            scaled_features,
            fallback=prepared.metrics["recent_cardio"],
            label="cardio_model",
        )
    )
    patchtst_score = _clamp(
        _predict_scalar(
            models.patchtst_model,
            sequence_batch,
            fallback=(prepared.metrics["recent_recovery"] + prepared.metrics["recent_cardio"]) / 2.0,
            label="patchtst",
        )
    )
    timesfm_score = _clamp(
        _predict_scalar(
            models.timesfm_model,
            sequence_batch,
            fallback=(
                prepared.metrics["recent_cardio"] * 0.55
                + prepared.metrics["recent_recovery"] * 0.45
            ),
            label="timesfm",
        )
    )

    trend = _resolve_trend(prepared, patchtst_score=patchtst_score, timesfm_score=timesfm_score)
    fitness_index = _clamp(
        0.22 * load_score
        + 0.26 * recovery_score
        + 0.18 * cardio_score
        + 0.17 * patchtst_score
        + 0.17 * timesfm_score
        + _trend_adjustment(trend),
        settings.fitness_index_min,
        settings.fitness_index_max,
    )

    load_strain = max(0.0, (prepared.metrics["acute_chronic_ratio"] - 1.0) * 55.0)
    load_delta = max(0.0, prepared.metrics["recent_load"] - prepared.metrics["previous_load"])
    fatigue_risk = _clamp(
        0.55 * (100.0 - recovery_score)
        + 0.25 * load_strain
        + 0.20 * load_delta
        + (8.0 if trend == "down" else 0.0),
        0.0,
        100.0,
    )

    return PredictionResult(
        load_score=load_score,
        recovery_score=recovery_score,
        cardio_score=cardio_score,
        patchtst_score=patchtst_score,
        timesfm_score=timesfm_score,
        fitness_index=fitness_index,
        fatigue_risk=fatigue_risk,
        trend=trend,
    )


def _apply_scaler(scaler: object, values: object) -> object:
    if hasattr(scaler, "transform"):
        transformed = scaler.transform(values)
        return _to_float_array(transformed)
    if callable(scaler):
        transformed = scaler(values)
        return _to_float_array(transformed)
    return _to_float_array(values)


def _predict_scalar(model: object, payload: object, *, fallback: float, label: str) -> float:
    try:
        raw = _invoke_model(model, payload)
        return _extract_scalar(raw)
    except Exception as exc:  # pragma: no cover - depends on real artifact behavior
        logger.warning("Prediction via %s failed: %s. Using fallback=%s", label, exc, round(fallback, 2))
        return fallback


def _invoke_model(model: object, payload: object) -> Any:
    if torch is not None and hasattr(torch, "nn") and isinstance(model, torch.nn.Module):
        tensor = torch.as_tensor(payload, dtype=torch.float32)
        with torch.no_grad():
            return model(tensor)
    if hasattr(model, "predict"):
        return model.predict(payload)
    if callable(model):
        return model(payload)
    raise TypeError(f"Unsupported model type: {type(model)!r}")


def _extract_scalar(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    if np is not None:
        array = np.asarray(raw, dtype=float)
        if array.size == 0:
            raise ValueError("Model returned an empty prediction")
        return float(array.reshape(-1)[0])
    if isinstance(raw, (list, tuple)):
        if not raw:
            raise ValueError("Model returned an empty prediction")
        return _extract_scalar(raw[0])
    raise ValueError(f"Unexpected prediction payload: {raw!r}")


def _resolve_trend(
    prepared: PreparedInferenceInput,
    *,
    patchtst_score: float,
    timesfm_score: float,
) -> str:
    trend_signal = (
        prepared.metrics["trend_signal"]
        + (timesfm_score - patchtst_score) * 0.18
        + (prepared.metrics["recent_recovery"] - prepared.metrics["previous_recovery"]) * 0.08
    )
    if trend_signal >= 3.0:
        return "up"
    if trend_signal <= -3.0:
        return "down"
    return "stable"


def _trend_adjustment(trend: str) -> float:
    if trend == "up":
        return 3.0
    if trend == "down":
        return -3.0
    return 0.0


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _wrap_sequence_batch(sequence_matrix: object) -> object:
    if np is not None:
        array = np.asarray(sequence_matrix, dtype=float)
        return array.reshape(1, array.shape[0], array.shape[1])
    if isinstance(sequence_matrix, list):
        return [sequence_matrix]
    if hasattr(sequence_matrix, "tolist"):
        return [sequence_matrix.tolist()]
    raise TypeError("Unsupported sequence payload")


def _to_float_array(values: object) -> object:
    if np is not None:
        return np.asarray(values, dtype=float)
    if isinstance(values, list):
        return [_to_float_array(item) for item in values]
    if isinstance(values, tuple):
        return [_to_float_array(item) for item in values]
    return float(values)
