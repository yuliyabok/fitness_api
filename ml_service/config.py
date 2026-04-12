from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

TABULAR_FEATURE_NAMES = (
    "recent_training_load",
    "chronic_training_load",
    "acute_chronic_ratio",
    "training_consistency",
    "avg_sleep_hours",
    "sleep_consistency",
    "avg_avg_hr",
    "avg_max_hr",
    "avg_spo2",
    "avg_systolic",
    "avg_diastolic",
    "avg_feeling_score",
    "athlete_age",
    "athlete_weight_kg",
    "athlete_height_cm",
)

SEQUENCE_FEATURE_NAMES = (
    "training_load",
    "sleep_hours",
    "recovery_signal",
    "cardio_signal",
    "avg_hr",
    "max_hr",
    "spo2",
    "feeling_score",
)


class MLServiceSettings(BaseSettings):
    window_size: int = Field(default=30, ge=7, le=365)
    short_horizon_days: int = Field(default=7, ge=3, le=60)
    log_level: str = "INFO"
    use_dummy_models: bool = False
    allow_missing_models: bool = True
    fitness_index_min: float = 0.0
    fitness_index_max: float = 100.0
    timesfm_model_path: str = "models/timesfm.pt"
    patchtst_model_path: str = "models/patchtst.pt"
    load_model_path: str = "models/load_model.pkl"
    recovery_model_path: str = "models/recovery_model.pkl"
    cardio_model_path: str = "models/cardio_model.pkl"
    scaler_path: str = "models/scaler.pkl"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "timesfm_model_path",
        "patchtst_model_path",
        "load_model_path",
        "recovery_model_path",
        "cardio_model_path",
        "scaler_path",
        mode="before",
    )
    @classmethod
    def _normalize_model_path(cls, value: str) -> str:
        return str(value).strip()

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return str(value).strip().upper()

    @property
    def tabular_feature_count(self) -> int:
        return len(TABULAR_FEATURE_NAMES)

    @property
    def sequence_feature_count(self) -> int:
        return len(SEQUENCE_FEATURE_NAMES)

    @property
    def resolved_timesfm_model_path(self) -> Path:
        return _resolve_path(self.timesfm_model_path)

    @property
    def resolved_patchtst_model_path(self) -> Path:
        return _resolve_path(self.patchtst_model_path)

    @property
    def resolved_load_model_path(self) -> Path:
        return _resolve_path(self.load_model_path)

    @property
    def resolved_recovery_model_path(self) -> Path:
        return _resolve_path(self.recovery_model_path)

    @property
    def resolved_cardio_model_path(self) -> Path:
        return _resolve_path(self.cardio_model_path)

    @property
    def resolved_scaler_path(self) -> Path:
        return _resolve_path(self.scaler_path)


def _resolve_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (BASE_DIR / candidate).resolve()
