from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from ml_service.config import MLServiceSettings
from ml_service.main import create_app


class MLServicePredictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        settings = MLServiceSettings(
            use_dummy_models=True,
            window_size=14,
        )
        cls.client = TestClient(create_app(settings))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_predict_returns_fitness_index_and_recommendations(self) -> None:
        response = self.client.post(
            "/predict",
            json={
                "target": "timesfm",
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
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["target"], "timesfm")
        self.assertIsInstance(payload["fitness_index"], float)
        self.assertGreaterEqual(payload["fitness_index"], 0)
        self.assertLessEqual(payload["fitness_index"], 100)
        self.assertTrue(payload["recommendations"])

    def test_predict_supports_patchtst_target(self) -> None:
        response = self.client.post(
            "/predict",
            json={
                "target": "patchtst",
                "window_size": 10,
                "trainings": [
                    {"date": "2026-04-02", "duration_minutes": 40},
                    {"date": "2026-04-03", "duration_minutes": 55},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["target"], "patchtst")
        self.assertEqual(payload["window_size"], 10)

    def test_invalid_target_is_rejected(self) -> None:
        response = self.client.post("/predict", json={"target": "unknown"})
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
