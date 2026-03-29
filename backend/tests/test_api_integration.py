# Файл: интеграционные API-тесты backend для ключевых сценариев Flutter-клиента.

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://fitness:fitness@localhost:5432/fitness",
)
os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self) -> None:
        self.client.cookies.clear()

    def _register_athlete(
        self,
        email: str = "athlete@example.com",
        password: str = "secret123",
    ) -> str:
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": password,
                "role": "athlete",
                "first_name": "Anna",
                "last_name": "Ivanova",
                "age": 23,
                "gender": "female",
                "weight_kg": 60,
                "height_cm": 170,
                "sport": "Running",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["access_token"]

    def _register_coach(
        self,
        email: str = "coach@example.com",
        password: str = "coach123",
    ) -> str:
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": password,
                "role": "coach",
                "first_name": "Ivan",
                "last_name": "Petrov",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["access_token"]

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_auth_and_profile_roundtrip(self) -> None:
        token = self._register_athlete()

        profile_response = self.client.get(
            "/api/profile/me",
            headers=self._auth_headers(token),
        )
        self.assertEqual(profile_response.status_code, 200, profile_response.text)
        profile = profile_response.json()
        self.assertEqual(profile["email"], "athlete@example.com")
        self.assertEqual(profile["sport"], "Running")

        update_response = self.client.put(
            "/api/profile/me",
            headers=self._auth_headers(token),
            json={
                "first_name": "Anna",
                "last_name": "Sidorova",
                "age": 24,
                "gender": "female",
                "weight_kg": 61,
                "height_cm": 170,
                "sport": "Triathlon",
            },
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)
        updated = update_response.json()
        self.assertEqual(updated["last_name"], "Sidorova")
        self.assertEqual(updated["sport"], "Triathlon")

    def test_training_crud_roundtrip(self) -> None:
        token = self._register_athlete()

        create_response = self.client.post(
            "/api/trainings",
            headers=self._auth_headers(token),
            json={
                "title": "Morning Run",
                "training_type": "Кардио",
                "date": "2026-03-20",
                "start_time": "07:15:00",
                "duration_minutes": 55,
                "distance_km": 10.5,
                "elevation_m": 120,
                "avg_hr": 148,
                "max_hr": 172,
                "calories": 620,
                "notes": "Intervals",
                "sport": "Running",
                "hr_zone": "Z3",
                "hr_zone_minutes": {"z2": 20, "z3": 25},
                "activity_types": ["run", "intervals"],
                "exercises": [{"name": "Sprint", "quantity": 6, "unit": "reps"}],
                "feeling_score": 8,
            },
        )
        self.assertEqual(create_response.status_code, 201, create_response.text)
        created = create_response.json()
        training_id = created["id"]
        self.assertEqual(created["duration_minutes"], 55)
        self.assertEqual(created["activity_types"], ["run", "intervals"])

        list_response = self.client.get(
            "/api/trainings",
            headers=self._auth_headers(token),
        )
        self.assertEqual(list_response.status_code, 200, list_response.text)
        trainings = list_response.json()
        self.assertEqual(len(trainings), 1)
        self.assertEqual(trainings[0]["id"], training_id)

        update_response = self.client.put(
            f"/api/trainings/{training_id}",
            headers=self._auth_headers(token),
            json={
                "title": "Morning Run Updated",
                "training_type": "Кардио",
                "date": "2026-03-20",
                "start_time": "07:30:00",
                "duration_minutes": 60,
                "distance_km": 11.2,
                "elevation_m": 150,
                "avg_hr": 150,
                "max_hr": 175,
                "calories": 660,
                "notes": "More tempo",
                "sport": "Running",
                "hr_zone": "Z4",
                "hr_zone_minutes": {"z3": 30, "z4": 15},
                "activity_types": ["run", "tempo"],
                "exercises": [{"name": "Hill sprint", "quantity": 8, "unit": "reps"}],
                "feeling_score": 9,
            },
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)
        updated = update_response.json()
        self.assertEqual(updated["title"], "Morning Run Updated")
        self.assertEqual(updated["distance_km"], 11.2)

        delete_response = self.client.delete(
            f"/api/trainings/{training_id}",
            headers=self._auth_headers(token),
        )
        self.assertEqual(delete_response.status_code, 204, delete_response.text)

        after_delete_response = self.client.get(
            "/api/trainings",
            headers=self._auth_headers(token),
        )
        self.assertEqual(after_delete_response.status_code, 200, after_delete_response.text)
        self.assertEqual(after_delete_response.json(), [])

    def test_cycle_roundtrip_and_invalid_kind_error(self) -> None:
        token = self._register_athlete()
        headers = self._auth_headers(token)

        settings_response = self.client.put(
            "/api/cycle/settings",
            headers=headers,
            json={
                "cycle_length_days": 28,
                "period_length_days": 5,
            },
        )
        self.assertEqual(settings_response.status_code, 200, settings_response.text)
        self.assertEqual(settings_response.json()["cycle_length_days"], 28)

        replace_response = self.client.put(
            "/api/cycle/events",
            headers=headers,
            json={
                "kind": "start",
                "dates": ["2026-03-01", "2026-03-29"],
            },
        )
        self.assertEqual(replace_response.status_code, 200, replace_response.text)
        self.assertEqual(replace_response.json(), ["2026-03-01", "2026-03-29"])

        list_response = self.client.get(
            "/api/cycle/events",
            headers=headers,
            params={"kind": "start"},
        )
        self.assertEqual(list_response.status_code, 200, list_response.text)
        self.assertEqual(list_response.json(), ["2026-03-01", "2026-03-29"])

        invalid_response = self.client.get(
            "/api/cycle/events",
            headers=headers,
            params={"kind": "wrong"},
        )
        self.assertEqual(invalid_response.status_code, 400, invalid_response.text)
        self.assertIn("Unsupported cycle event kind", invalid_response.json()["detail"])

    def test_coach_can_link_athlete_and_read_details(self) -> None:
        athlete_token = self._register_athlete(email="athlete2@example.com")
        self.client.post(
            "/api/trainings",
            headers=self._auth_headers(athlete_token),
            json={
                "title": "Pool Session",
                "training_type": "Плавание",
                "date": "2026-03-18",
                "start_time": "08:00:00",
                "duration_minutes": 45,
                "distance_km": 2.0,
                "elevation_m": 0,
                "avg_hr": 132,
                "max_hr": 150,
                "calories": 410,
                "notes": "Technique",
                "sport": "Swimming",
                "hr_zone": "Z2",
                "hr_zone_minutes": {"z2": 30},
                "activity_types": ["swim"],
                "exercises": [{"name": "Freestyle", "quantity": 20, "unit": "laps"}],
                "feeling_score": 7,
            },
        )

        coach_token = self._register_coach()
        coach_headers = self._auth_headers(coach_token)

        link_response = self.client.post(
            "/api/coach/athletes",
            headers=coach_headers,
            json={"email": "athlete2@example.com"},
        )
        self.assertEqual(link_response.status_code, 200, link_response.text)
        athlete_id = link_response.json()["athlete_id"]

        athletes_response = self.client.get(
            "/api/coach/athletes",
            headers=coach_headers,
        )
        self.assertEqual(athletes_response.status_code, 200, athletes_response.text)
        athletes = athletes_response.json()
        self.assertEqual(len(athletes), 1)
        self.assertEqual(athletes[0]["email"], "athlete2@example.com")

        detail_response = self.client.get(
            f"/api/coach/athletes/{athlete_id}",
            headers=coach_headers,
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.text)
        detail = detail_response.json()
        self.assertEqual(detail["email"], "athlete2@example.com")
        self.assertEqual(len(detail["trainings"]), 1)
        self.assertEqual(detail["trainings"][0]["title"], "Pool Session")

    def test_validation_errors_are_returned_as_plain_detail_text(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": "broken@example.com",
                "role": "athlete",
                "first_name": "Broken",
                "last_name": "User",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)
        payload = response.json()
        self.assertIsInstance(payload["detail"], str)
        self.assertIn("password", payload["detail"])


if __name__ == "__main__":
    unittest.main()
