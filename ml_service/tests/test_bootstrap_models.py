from __future__ import annotations

import unittest
from types import SimpleNamespace

import torch

from ml_service.services.bootstrap_models import (
    BootstrapPatchTSTWrapper,
    BootstrapTimesFMWrapper,
)


class _StubTimesFMWrapper(BootstrapTimesFMWrapper):
    def __init__(self, backbone: torch.nn.Module) -> None:
        super().__init__(backbone_dir="unused", loader_kind="timesfm")
        self._stub_backbone = backbone

    def _load_backbone(self) -> torch.nn.Module:
        return self._stub_backbone


class _StubPatchTSTWrapper(BootstrapPatchTSTWrapper):
    def __init__(self, backbone: torch.nn.Module) -> None:
        super().__init__(backbone_dir="unused")
        self._stub_backbone = backbone

    def _load_backbone(self) -> torch.nn.Module:
        return self._stub_backbone


class _TimesFMForecastBackbone(torch.nn.Module):
    def forward(self, past_values, freq, return_dict=True):  # type: ignore[override]
        del freq, return_dict
        batch_size = len(past_values)
        return SimpleNamespace(mean_predictions=torch.full((batch_size, 6), 68.0))


class _TimesFMLatentBackbone(torch.nn.Module):
    def forward(self, past_values, freq, return_dict=True):  # type: ignore[override]
        del freq, return_dict
        batch_size = len(past_values)
        return SimpleNamespace(last_hidden_state=torch.full((batch_size, 4, 3), 0.25))


class _PatchTSTDirectBackbone(torch.nn.Module):
    def forward(self, past_values, past_observed_mask, output_hidden_states=True, return_dict=True):  # type: ignore[override]
        del past_observed_mask, output_hidden_states, return_dict
        batch_size = past_values.shape[0]
        return SimpleNamespace(prediction_outputs=torch.full((batch_size, 5, 2), 72.0))


class _PatchTSTLatentBackbone(torch.nn.Module):
    def forward(self, past_values, past_observed_mask, output_hidden_states=True, return_dict=True):  # type: ignore[override]
        del past_observed_mask, output_hidden_states, return_dict
        batch_size = past_values.shape[0]
        return SimpleNamespace(last_hidden_state=torch.full((batch_size, 5, 2), 0.5))


class BootstrapModelWrapperTests(unittest.TestCase):
    def test_timesfm_wrapper_uses_forecast_output(self) -> None:
        wrapper = _StubTimesFMWrapper(_TimesFMForecastBackbone())
        values = torch.full((1, 10, 8), 60.0)

        prediction = wrapper(values)

        self.assertEqual(tuple(prediction.shape), (1, 1))
        self.assertGreaterEqual(float(prediction[0][0]), 0.0)
        self.assertLessEqual(float(prediction[0][0]), 100.0)

    def test_timesfm_wrapper_falls_back_to_latent_state(self) -> None:
        wrapper = _StubTimesFMWrapper(_TimesFMLatentBackbone())
        values = torch.full((2, 12, 8), 45.0)

        prediction = wrapper(values)

        self.assertEqual(tuple(prediction.shape), (2, 1))
        self.assertTrue(torch.all(prediction >= 0.0))
        self.assertTrue(torch.all(prediction <= 100.0))

    def test_patchtst_wrapper_uses_direct_prediction_output(self) -> None:
        wrapper = _StubPatchTSTWrapper(_PatchTSTDirectBackbone())
        values = torch.full((1, 14, 8), 55.0)

        prediction = wrapper(values)

        self.assertEqual(tuple(prediction.shape), (1, 1))
        self.assertGreaterEqual(float(prediction[0][0]), 0.0)
        self.assertLessEqual(float(prediction[0][0]), 100.0)

    def test_patchtst_wrapper_maps_latent_output_to_score(self) -> None:
        wrapper = _StubPatchTSTWrapper(_PatchTSTLatentBackbone())
        values = torch.full((3, 14, 8), 52.0)

        prediction = wrapper(values)

        self.assertEqual(tuple(prediction.shape), (3, 1))
        self.assertTrue(torch.all(prediction >= 0.0))
        self.assertTrue(torch.all(prediction <= 100.0))


if __name__ == "__main__":
    unittest.main()
