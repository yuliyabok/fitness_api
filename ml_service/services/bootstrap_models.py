from __future__ import annotations

from pathlib import Path
from typing import Any

import torch


class BootstrapTimesFMWrapper(torch.nn.Module):
    """
    Thin adapter around a public TimesFM checkpoint.

    The project prediction pipeline expects a scalar score in the 0..100 range
    from a `.pt` artifact. Public TimesFM checkpoints are generic forecasting
    backbones, so this wrapper keeps a local `save_pretrained()` directory and
    lazily converts the forecast into a single bootstrap score.
    """

    def __init__(
        self,
        *,
        backbone_dir: str,
        loader_kind: str,
        recent_window: int = 7,
        frequency: int = 0,
    ) -> None:
        super().__init__()
        self.backbone_dir = backbone_dir
        self.loader_kind = loader_kind
        self.recent_window = recent_window
        self.frequency = frequency
        self._backbone: torch.nn.Module | None = None

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        sequence = _ensure_3d_tensor(values)
        univariate = sequence.mean(dim=-1)
        recent_context = univariate[:, -min(self.recent_window, univariate.shape[1]) :].mean(dim=1)

        model = self._load_backbone()
        freq = torch.full(
            (univariate.shape[0],),
            fill_value=self.frequency,
            dtype=torch.long,
            device=univariate.device,
        )
        outputs = model(
            past_values=[row for row in univariate],
            freq=freq,
            return_dict=True,
        )

        forecast = _extract_tensor(outputs, preferred=("mean_predictions", "full_predictions"))
        if forecast is None:
            latent = _extract_tensor(outputs, preferred=("last_hidden_state",))
            if latent is None:
                raise RuntimeError("TimesFM output does not expose forecast tensors")
            forecast_signal = torch.sigmoid(latent.reshape(latent.shape[0], -1).mean(dim=1)) * 100.0
        else:
            forecast_signal = forecast.reshape(forecast.shape[0], -1).mean(dim=1)

        score = 0.55 * recent_context + 0.45 * forecast_signal
        return _clamp_score(score).unsqueeze(-1)

    def _load_backbone(self) -> torch.nn.Module:
        if self._backbone is not None:
            return self._backbone

        backbone_path = Path(self.backbone_dir)
        if not backbone_path.exists():
            raise FileNotFoundError(
                f"TimesFM backbone directory was not found: {backbone_path}. "
                "Run ml_service.scripts.download_export_models first."
            )

        model = _load_timesfm_backbone(str(backbone_path), self.loader_kind)
        model.eval()
        self._backbone = model
        return model


class BootstrapPatchTSTWrapper(torch.nn.Module):
    """
    Adapter around a public PatchTST checkpoint.

    Public PatchTST checkpoints may expose latent states or forecasting heads
    depending on the source artifact. This wrapper accepts both shapes and maps
    them into a stable 0..100 scalar for the fitness pipeline.
    """

    def __init__(
        self,
        *,
        backbone_dir: str,
        recent_window: int = 7,
    ) -> None:
        super().__init__()
        self.backbone_dir = backbone_dir
        self.recent_window = recent_window
        self._backbone: torch.nn.Module | None = None

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        model = self._load_backbone()
        sequence = _align_patchtst_input(_ensure_3d_tensor(values), model)
        batch_size, _, channel_count = sequence.shape
        observed_mask = torch.ones_like(sequence, dtype=torch.bool)
        outputs = model(
            past_values=sequence,
            past_observed_mask=observed_mask,
            output_hidden_states=True,
            return_dict=True,
        )

        recent_window = min(self.recent_window, sequence.shape[1])
        recent_block = sequence[:, -recent_window:, :]
        recent_mean = recent_block.mean(dim=(1, 2))
        recovery_signal = recent_block[:, :, 2].mean(dim=1) if channel_count > 2 else recent_mean
        cardio_signal = recent_block[:, :, 3].mean(dim=1) if channel_count > 3 else recent_mean

        direct_output = _extract_tensor(outputs, preferred=("prediction_outputs",))
        if direct_output is not None:
            model_signal = direct_output.reshape(batch_size, -1).mean(dim=1)
            score = 0.45 * model_signal + 0.30 * recovery_signal + 0.25 * cardio_signal
            return _clamp_score(score).unsqueeze(-1)

        latent = _extract_tensor(outputs, preferred=("last_hidden_state", "hidden_states"))
        if latent is None:
            raise RuntimeError("PatchTST output does not expose usable tensors")

        latent_signal = torch.sigmoid(latent.reshape(batch_size, -1).mean(dim=1)) * 100.0
        score = 0.40 * latent_signal + 0.35 * recovery_signal + 0.25 * cardio_signal
        return _clamp_score(score).unsqueeze(-1)

    def _load_backbone(self) -> torch.nn.Module:
        if self._backbone is not None:
            return self._backbone

        backbone_path = Path(self.backbone_dir)
        if not backbone_path.exists():
            raise FileNotFoundError(
                f"PatchTST backbone directory was not found: {backbone_path}. "
                "Run ml_service.scripts.download_export_models first."
            )

        from transformers import AutoModel  # type: ignore

        model = AutoModel.from_pretrained(str(backbone_path))
        model.eval()
        self._backbone = model
        return model


class TrainedPatchTSTRegressorWrapper(torch.nn.Module):
    """
    Runtime adapter for a trained PatchTSTForRegression checkpoint.

    The training pipeline saves a Hugging Face backbone directory plus this thin
    wrapper. `ml_service` loads the wrapper through torch.load() and keeps the
    rest of the inference pipeline unchanged.
    """

    def __init__(
        self,
        *,
        backbone_dir: str,
    ) -> None:
        super().__init__()
        self.backbone_dir = backbone_dir
        self._backbone: torch.nn.Module | None = None

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        model = self._load_backbone()
        sequence = _align_patchtst_input(_ensure_3d_tensor(values), model)
        observed_mask = torch.ones_like(sequence, dtype=torch.bool)
        outputs = model(
            past_values=sequence,
            past_observed_mask=observed_mask,
            return_dict=True,
        )
        direct_output = _extract_tensor(outputs, preferred=("regression_outputs",))
        if direct_output is None:
            raise RuntimeError("Trained PatchTST checkpoint did not expose regression_outputs")
        return _clamp_score(direct_output.float())

    def _load_backbone(self) -> torch.nn.Module:
        if self._backbone is not None:
            return self._backbone

        backbone_path = Path(self.backbone_dir)
        if not backbone_path.exists():
            raise FileNotFoundError(
                f"Trained PatchTST backbone directory was not found: {backbone_path}"
            )

        from transformers import PatchTSTForRegression  # type: ignore

        model = PatchTSTForRegression.from_pretrained(str(backbone_path))
        model.eval()
        self._backbone = model
        return model


class TrainedTimesFMRegressorWrapper(torch.nn.Module):
    """
    Runtime adapter for a trained TimesFM regression head.

    The backbone stays in a Hugging Face `save_pretrained()` directory, while
    the lightweight regression head is serialized inside the `.pt` artifact.
    """

    def __init__(
        self,
        *,
        backbone_dir: str,
        loader_kind: str,
        forecast_dim: int,
        recent_window: int = 7,
        hidden_dim: int = 64,
        dropout: float = 0.1,
        frequency: int = 0,
    ) -> None:
        super().__init__()
        self.backbone_dir = backbone_dir
        self.loader_kind = loader_kind
        self.forecast_dim = forecast_dim
        self.recent_window = recent_window
        self.hidden_dim = hidden_dim
        self.dropout = dropout
        self.frequency = frequency
        self.regression_head = torch.nn.Sequential(
            torch.nn.Linear(forecast_dim + 1, hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim, 1),
        )
        self._backbone: torch.nn.Module | None = None

    def predict_raw(self, values: torch.Tensor) -> torch.Tensor:
        sequence = _ensure_3d_tensor(values)
        univariate = sequence.mean(dim=-1)
        recent_context = univariate[:, -min(self.recent_window, univariate.shape[1]) :].mean(dim=1, keepdim=True)

        model = self._load_backbone()
        with torch.no_grad():
            outputs = _run_timesfm_backbone(
                model=model,
                loader_kind=self.loader_kind,
                univariate=univariate,
                frequency=self.frequency,
            )

        forecast = _extract_tensor(outputs, preferred=("mean_predictions", "full_predictions"))
        if forecast is None:
            raise RuntimeError("Trained TimesFM checkpoint did not expose forecast tensors")
        forecast_features = forecast.reshape(forecast.shape[0], -1).float()
        features = torch.cat((forecast_features, recent_context.float()), dim=1)
        return self.regression_head(features)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return _clamp_score(self.predict_raw(values))

    def reset_backbone(self) -> None:
        self._backbone = None

    def _load_backbone(self) -> torch.nn.Module:
        if self._backbone is not None:
            return self._backbone

        backbone_path = Path(self.backbone_dir)
        if not backbone_path.exists():
            raise FileNotFoundError(
                f"Trained TimesFM backbone directory was not found: {backbone_path}"
            )

        model = _load_timesfm_backbone(str(backbone_path), self.loader_kind)
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        self._backbone = model
        return model


def _ensure_3d_tensor(values: torch.Tensor | Any) -> torch.Tensor:
    tensor = torch.as_tensor(values, dtype=torch.float32)
    if tensor.ndim == 2:
        tensor = tensor.unsqueeze(0)
    if tensor.ndim != 3:
        raise ValueError(f"Expected a 3D sequence tensor, got shape={tuple(tensor.shape)}")
    return tensor


def _load_timesfm_backbone(backbone_dir: str, loader_kind: str) -> torch.nn.Module:
    if loader_kind == "timesfm2_5":
        try:
            from transformers import TimesFm2_5ModelForPrediction  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "Installed transformers package does not expose TimesFm2_5ModelForPrediction. "
                "Upgrade transformers or re-export using the legacy TimesFM 2.0 loader."
            ) from exc
        return TimesFm2_5ModelForPrediction.from_pretrained(backbone_dir)

    from transformers import TimesFmModelForPrediction  # type: ignore

    return TimesFmModelForPrediction.from_pretrained(backbone_dir)


def _run_timesfm_backbone(
    *,
    model: torch.nn.Module,
    loader_kind: str,
    univariate: torch.Tensor,
    frequency: int,
) -> Any:
    if loader_kind == "timesfm2_5":
        return model(
            past_values=[row for row in univariate],
            return_dict=True,
        )

    freq = torch.full(
        (univariate.shape[0],),
        fill_value=frequency,
        dtype=torch.long,
        device=univariate.device,
    )
    return model(
        past_values=[row for row in univariate],
        freq=freq,
        return_dict=True,
    )


def _align_patchtst_input(sequence: torch.Tensor, model: torch.nn.Module) -> torch.Tensor:
    config = getattr(model, "config", None)
    expected_channels = getattr(config, "num_input_channels", sequence.shape[2]) or sequence.shape[2]
    expected_context = getattr(config, "context_length", sequence.shape[1]) or sequence.shape[1]

    if sequence.shape[2] > expected_channels:
        sequence = sequence[:, :, :expected_channels]
    elif sequence.shape[2] < expected_channels:
        channel_padding = torch.zeros(
            sequence.shape[0],
            sequence.shape[1],
            expected_channels - sequence.shape[2],
            dtype=sequence.dtype,
            device=sequence.device,
        )
        sequence = torch.cat((sequence, channel_padding), dim=2)

    if sequence.shape[1] > expected_context:
        sequence = sequence[:, -expected_context:, :]
    elif sequence.shape[1] < expected_context:
        pad_length = expected_context - sequence.shape[1]
        left_pad = sequence[:, :1, :].repeat(1, pad_length, 1)
        sequence = torch.cat((left_pad, sequence), dim=1)

    return sequence


def _extract_tensor(output: Any, *, preferred: tuple[str, ...]) -> torch.Tensor | None:
    for attr_name in preferred:
        if not hasattr(output, attr_name):
            continue
        candidate = getattr(output, attr_name)
        tensor = _coerce_tensor(candidate)
        if tensor is not None:
            return tensor
    if isinstance(output, tuple):
        for item in output:
            tensor = _coerce_tensor(item)
            if tensor is not None:
                return tensor
    return None


def _coerce_tensor(candidate: Any) -> torch.Tensor | None:
    if isinstance(candidate, torch.Tensor):
        return candidate.float()
    if isinstance(candidate, (list, tuple)):
        if not candidate:
            return None
        if isinstance(candidate[-1], torch.Tensor):
            return candidate[-1].float()
    return None


def _clamp_score(values: torch.Tensor) -> torch.Tensor:
    return torch.clamp(values.float(), min=0.0, max=100.0)
