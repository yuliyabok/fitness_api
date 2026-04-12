from __future__ import annotations

import unittest

from pydantic import ValidationError

from ml_service.config import MLServiceSettings
from ml_service.main import _predict_sync
from ml_service.schemas import PredictionRequest
from ml_service.services.model_loader import load_model_artifacts


class MLServicePredictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = MLServiceSettings(
            use_dummy_models=True,
            window_size=14,
        )
        cls.artifacts = load_model_artifacts(cls.settings)

    def test_predict_returns_fitness_index_and_recommendations(self) -> None:
        payload = PredictionRequest.model_validate(
            {
                "profile": {
                    "age": 24,
                    "weight_kg": 60,
                    "height_cm": 170,
                    "sport": "Running",
                },
                "trainings": [
                    {
                        "date": "2026-04-01",
                        "duration_minutes": 50,
                        "calories": 520,
                        "avg_hr": 148,
                        "max_hr": 172,
                        "feeling_score": 8,
                    }
                ],
                "sleep": [
                    {
                        "start_ts": "2026-03-31T22:30:00Z",
                        "end_ts": "2026-04-01T06:30:00Z",
                        "deep_minutes": 95,
                        "rem_minutes": 80,
                    }
                ],
                "blood_pressure": [
                    {
                        "ts": "2026-04-01T07:00:00Z",
                        "systolic": 118,
                        "diastolic": 76,
                    }
                ],
                "spo2": [
                    {
                        "ts": "2026-04-01T07:05:00Z",
                        "percentage": 98,
                    }
                ],
            }
        )
        result = _predict_sync(payload, self.artifacts, self.settings).model_dump()
        self.assertIsInstance(result["fitness_index"], float)
        self.assertGreaterEqual(result["fitness_index"], 0)
        self.assertLessEqual(result["fitness_index"], 100)
        self.assertIsInstance(result["fatigue_risk"], float)
        self.assertIn(result["trend"], {"up", "stable", "down"})
        self.assertTrue(result["recommendations"])
        self.assertIsInstance(result["recommendations"], list)

    def test_predict_honors_window_size(self) -> None:
        payload = PredictionRequest.model_validate(
            {
                "window_size": 10,
                "trainings": [
                    {"date": "2026-04-02", "duration_minutes": 40},
                    {"date": "2026-04-03", "duration_minutes": 55},
                ],
            }
        )
        result = _predict_sync(payload, self.artifacts, self.settings).model_dump()
        self.assertIn(result["trend"], {"up", "stable", "down"})

    def test_invalid_date_range_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionRequest.model_validate({"date_from": "2026-04-10", "date_to": "2026-04-01"})


if __name__ == "__main__":
    unittest.main()
