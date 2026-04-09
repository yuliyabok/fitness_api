from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_FEATURE_NAMES = (
    "training_duration_minutes",
    "training_calories",
    "training_avg_hr",
    "training_max_hr",
    "training_feeling_score",
    "sleep_minutes",
    "sleep_deep_minutes",
    "sleep_rem_minutes",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "spo2_percentage",
    "athlete_age",
    "athlete_weight_kg",
    "athlete_height_cm",
)


def _parse_float_list(raw: str | None) -> list[float]:
    if raw is None:
        return []
    normalized = raw.strip()
    if not normalized:
        return []
    return [float(part.strip()) for part in normalized.split(",") if part.strip()]


class MLServiceSettings(BaseSettings):
    timesfm_model_path: str = "models/timesfm.onnx"
    patchtst_model_path: str = "models/patchtst.onnx"
    window_size: int = 30
    default_target: str = "timesfm"
    normalization_means: list[float] = Field(default_factory=list)
    normalization_stds: list[float] = Field(default_factory=list)
    use_dummy_models: bool = False

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("timesfm_model_path", "patchtst_model_path", mode="before")
    @classmethod
    def _normalize_model_path(cls, value: str) -> str:
        return str(value).strip()

    @field_validator("normalization_means", "normalization_stds", mode="before")
    @classmethod
    def _normalize_float_list(cls, value: object) -> list[float]:
        if isinstance(value, list):
            return [float(item) for item in value]
        if isinstance(value, str) or value is None:
            return _parse_float_list(value)
        raise TypeError("Expected comma-separated string or list of floats")

    @field_validator("default_target")
    @classmethod
    def _validate_target(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"timesfm", "patchtst"}:
            raise ValueError("default_target must be either 'timesfm' or 'patchtst'")
        return normalized

    @property
    def feature_count(self) -> int:
        return len(DEFAULT_FEATURE_NAMES)

    @property
    def resolved_timesfm_model_path(self) -> Path:
        return _resolve_path(self.timesfm_model_path)

    @property
    def resolved_patchtst_model_path(self) -> Path:
        return _resolve_path(self.patchtst_model_path)

    def normalized_means(self) -> list[float]:
        return _fit_vector(self.normalization_means, self.feature_count, fill=0.0)

    def normalized_stds(self) -> list[float]:
        values = _fit_vector(self.normalization_stds, self.feature_count, fill=1.0)
        return [value if abs(value) > 1e-9 else 1.0 for value in values]


def _resolve_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (BASE_DIR / candidate).resolve()


def _fit_vector(values: list[float], size: int, *, fill: float) -> list[float]:
    if len(values) >= size:
        return values[:size]
    return [*values, *([fill] * (size - len(values)))]
