from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ml_service.config import MLServiceSettings
from ml_service.services.bootstrap_tabular import BootstrapTabularModel, BootstrapTabularScaler

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional during minimal local setup
    np = None

try:
    import joblib
except ImportError:  # pragma: no cover - optional during minimal local setup
    joblib = None

try:
    import torch
except ImportError:  # pragma: no cover - optional during minimal local setup
    torch = None

logger = logging.getLogger(__name__)


class ModelLoadingError(RuntimeError):
    pass


@dataclass(slots=True)
class ModelArtifacts:
    timesfm_model: object
    patchtst_model: object
    load_model: object
    recovery_model: object
    cardio_model: object
    scaler: object


class HeuristicSequenceModel:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def predict(self, values: Any) -> Any:
        batch = _ensure_3d(values)
        predictions = [self._predict_sequence(sequence) for sequence in batch]
        return _to_output_vector(predictions)

    def _predict_sequence(self, sequence: list[list[float]]) -> float:
        if not sequence:
            return 50.0

        training_load = [row[0] for row in sequence]

        recent_window = min(7, len(sequence))
        recent_slice = sequence[-recent_window:]
        earlier_slice = sequence[:-recent_window] if len(sequence) > recent_window else sequence

        recent_load = _mean([row[0] for row in recent_slice])
        recent_recovery = _mean([row[2] for row in recent_slice])
        recent_cardio = _mean([row[3] for row in recent_slice])
        earlier_load = _mean([row[0] for row in earlier_slice], default=recent_load)
        earlier_recovery = _mean([row[2] for row in earlier_slice], default=recent_recovery)
        earlier_cardio = _mean([row[3] for row in earlier_slice], default=recent_cardio)

        if self.kind == "patchtst":
            trend_component = 50.0 + (recent_recovery - earlier_recovery) * 0.8 - max(0.0, recent_load - earlier_load)
            score = (
                0.28 * _mean(training_load)
                + 0.32 * recent_recovery
                + 0.24 * recent_cardio
                + 0.16 * trend_component
            )
            return _clamp(score)

        if self.kind == "timesfm":
            forecast_component = (
                50.0
                + (recent_cardio - earlier_cardio) * 0.8
                + (recent_recovery - earlier_recovery) * 0.6
                - max(0.0, recent_load - earlier_load) * 0.5
            )
            score = (
                0.22 * recent_load
                + 0.28 * recent_recovery
                + 0.30 * recent_cardio
                + 0.20 * forecast_component
            )
            return _clamp(score)

        raise ValueError(f"Unknown heuristic sequence model kind: {self.kind}")


def load_model_artifacts(settings: MLServiceSettings) -> ModelArtifacts:
    logger.info("Loading ML artifacts from %s", settings.resolved_timesfm_model_path.parent)
    return ModelArtifacts(
        timesfm_model=_load_torch_model(
            path=settings.resolved_timesfm_model_path,
            fallback=HeuristicSequenceModel("timesfm"),
            settings=settings,
            label="timesfm",
        ),
        patchtst_model=_load_torch_model(
            path=settings.resolved_patchtst_model_path,
            fallback=HeuristicSequenceModel("patchtst"),
            settings=settings,
            label="patchtst",
        ),
        load_model=_load_pickle_model(
            path=settings.resolved_load_model_path,
            fallback=BootstrapTabularModel("load"),
            settings=settings,
            label="load_model",
        ),
        recovery_model=_load_pickle_model(
            path=settings.resolved_recovery_model_path,
            fallback=BootstrapTabularModel("recovery"),
            settings=settings,
            label="recovery_model",
        ),
        cardio_model=_load_pickle_model(
            path=settings.resolved_cardio_model_path,
            fallback=BootstrapTabularModel("cardio"),
            settings=settings,
            label="cardio_model",
        ),
        scaler=_load_pickle_model(
            path=settings.resolved_scaler_path,
            fallback=BootstrapTabularScaler(),
            settings=settings,
            label="scaler",
        ),
    )


def _load_torch_model(
    *,
    path: Path,
    fallback: object,
    settings: MLServiceSettings,
    label: str,
) -> object:
    if settings.use_dummy_models:
        logger.warning("Using heuristic fallback for %s because USE_DUMMY_MODELS is enabled", label)
        return fallback
    if not path.exists():
        return _handle_missing_artifact(path=path, fallback=fallback, settings=settings, label=label)
    if torch is None:
        return _handle_load_failure(
            message=f"torch is not installed; cannot load {label} from {path}",
            fallback=fallback,
            settings=settings,
            label=label,
        )

    try:
        try:
            model = torch.jit.load(str(path), map_location="cpu")
        except Exception:
            model = _torch_load(path)
        model = _unwrap_torch_model(model)
        if hasattr(model, "eval"):
            model.eval()
        return model
    except Exception as exc:  # pragma: no cover - depends on real model format
        return _handle_load_failure(
            message=f"Failed to load {label} from {path}: {exc}",
            fallback=fallback,
            settings=settings,
            label=label,
        )


def _load_pickle_model(
    *,
    path: Path,
    fallback: object,
    settings: MLServiceSettings,
    label: str,
) -> object:
    if settings.use_dummy_models:
        logger.warning("Using heuristic fallback for %s because USE_DUMMY_MODELS is enabled", label)
        return fallback
    if not path.exists():
        return _handle_missing_artifact(path=path, fallback=fallback, settings=settings, label=label)

    try:
        if joblib is not None:
            try:
                return joblib.load(path)
            except Exception as joblib_exc:
                logger.debug(
                    "joblib failed to load %s from %s: %s. Falling back to pickle.",
                    label,
                    path,
                    joblib_exc,
                )
        with path.open("rb") as file_obj:
            return pickle.load(file_obj)
    except Exception as exc:  # pragma: no cover - depends on real model format
        return _handle_load_failure(
            message=f"Failed to load {label} from {path}: {exc}",
            fallback=fallback,
            settings=settings,
            label=label,
        )


def _unwrap_torch_model(model: object) -> object:
    if isinstance(model, dict):
        if "model" in model:
            return _unwrap_torch_model(model["model"])
        if "module" in model:
            return _unwrap_torch_model(model["module"])
        raise ModelLoadingError(
            "Torch checkpoint contains only weights/state and no executable module. "
            "Provide a serialized module or enable allow_missing_models/use_dummy_models."
        )
    return model


def _torch_load(path: Path) -> object:
    if torch is None:  # pragma: no cover - guarded by caller
        raise RuntimeError("torch is not installed")
    try:
        return torch.load(str(path), map_location="cpu", weights_only=False)
    except TypeError:
        return torch.load(str(path), map_location="cpu")


def _handle_missing_artifact(
    *,
    path: Path,
    fallback: object,
    settings: MLServiceSettings,
    label: str,
) -> object:
    message = f"Artifact {label} was not found at {path}"
    if settings.allow_missing_models:
        logger.warning("%s. Falling back to heuristic implementation.", message)
        return fallback
    raise ModelLoadingError(message)


def _handle_load_failure(
    *,
    message: str,
    fallback: object,
    settings: MLServiceSettings,
    label: str,
) -> object:
    if settings.allow_missing_models:
        logger.warning("%s. Falling back to heuristic implementation for %s.", message, label)
        return fallback
    raise ModelLoadingError(message)


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _to_float_matrix(values: Any) -> Any:
    if np is not None:
        return np.asarray(values, dtype=float)
    if isinstance(values, list):
        return [_to_float_matrix(item) for item in values]
    if isinstance(values, tuple):
        return [_to_float_matrix(item) for item in values]
    return float(values)


def _ensure_2d(values: Any) -> list[list[float]]:
    matrix = _to_nested_list(values)
    if not matrix:
        return [[]]
    if isinstance(matrix[0], list):
        return [[float(item) for item in row] for row in matrix]
    return [[float(item) for item in matrix]]


def _ensure_3d(values: Any) -> list[list[list[float]]]:
    nested = _to_nested_list(values)
    if not nested:
        return [[[]]]
    if isinstance(nested[0], list) and nested[0] and isinstance(nested[0][0], list):
        return [
            [[float(item) for item in row] for row in batch]
            for batch in nested
        ]
    return [[[float(item) for item in row] for row in nested]]


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


def _to_output_vector(values: list[float]) -> Any:
    if np is not None:
        return np.asarray(values, dtype=float)
    return values


def _mean(values: list[float], *, default: float = 0.0) -> float:
    if not values:
        return default
    return float(sum(values) / len(values))
