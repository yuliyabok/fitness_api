# Файл: интеграционные API-тесты backend для ключевых сценариев Flutter-клиента.

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


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
        payload = response.json()
        self.assertEqual(payload["role"], "athlete")
        return payload["access_token"]

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
        payload = response.json()
        self.assertEqual(payload["role"], "coach")
        return payload["access_token"]

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_auth_and_profile_roundtrip(self) -> None:
        token = self._register_athlete()

        login_response = self.client.post(
            "/api/auth/login",
            json={
                "email": "athlete@example.com",
                "password": "secret123",
            },
        )
        self.assertEqual(login_response.status_code, 200, login_response.text)
        self.assertEqual(login_response.json()["role"], "athlete")

        profile_response = self.client.get(
            "/api/profile/me",
            headers=self._auth_headers(token),
        )
        self.assertEqual(profile_response.status_code, 200, profile_response.text)
        profile = profile_response.json()
        self.assertEqual(profile["role"], "athlete")
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
        self.assertEqual(updated["role"], "athlete")
        self.assertEqual(updated["last_name"], "Sidorova")
        self.assertEqual(updated["sport"], "Triathlon")

        coach_token = self._register_coach(email="coach-role@example.com", password="coach-pass")
        coach_profile_response = self.client.get(
            "/api/profile/me",
            headers=self._auth_headers(coach_token),
        )
        self.assertEqual(coach_profile_response.status_code, 200, coach_profile_response.text)
        self.assertEqual(coach_profile_response.json()["role"], "coach")

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

    def test_training_list_supports_date_range_and_pagination(self) -> None:
        token = self._register_athlete()
        headers = self._auth_headers(token)

        for title, training_date in (
            ("Recovery Run", "2026-03-10"),
            ("Tempo Run", "2026-03-18"),
            ("Long Run", "2026-03-24"),
        ):
            response = self.client.post(
                "/api/trainings",
                headers=headers,
                json={
                    "title": title,
                    "training_type": "Кардио",
                    "date": training_date,
                    "duration_minutes": 40,
                    "distance_km": 8.0,
                },
            )
            self.assertEqual(response.status_code, 201, response.text)

        filtered_response = self.client.get(
            "/api/trainings",
            headers=headers,
            params={
                "date_from": "2026-03-15",
                "date_to": "2026-03-25",
                "limit": 1,
                "offset": 0,
            },
        )
        self.assertEqual(filtered_response.status_code, 200, filtered_response.text)
        payload = filtered_response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["title"], "Long Run")

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

    def test_health_resources_support_full_crud(self) -> None:
        token = self._register_athlete()
        headers = self._auth_headers(token)

        scenarios = (
            {
                "name": "analysis",
                "path": "/api/analyses",
                "create": {
                    "date": "2026-03-10",
                    "title": "Hemoglobin",
                    "value": "140",
                    "notes": "baseline",
                },
                "update": {
                    "date": "2026-03-12",
                    "title": "Hemoglobin",
                    "value": "142",
                    "notes": "updated",
                },
                "list_params": {"date_from": "2026-03-01", "date_to": "2026-03-31", "limit": 10},
                "expect": {"field": "value", "created": "140", "updated": "142"},
            },
            {
                "name": "calorie",
                "path": "/api/calories",
                "create": {
                    "date": "2026-03-11",
                    "calories": 2500,
                    "notes": "base",
                },
                "update": {
                    "date": "2026-03-12",
                    "calories": 2700,
                    "notes": "race day",
                },
                "list_params": {"date_from": "2026-03-01", "date_to": "2026-03-31", "limit": 10},
                "expect": {"field": "calories", "created": 2500, "updated": 2700},
            },
            {
                "name": "blood pressure",
                "path": "/api/blood-pressure",
                "create": {
                    "ts": "2026-03-13T07:30:00",
                    "is_morning": True,
                    "systolic": 118,
                    "diastolic": 76,
                },
                "update": {
                    "ts": "2026-03-13T19:45:00",
                    "is_morning": False,
                    "systolic": 122,
                    "diastolic": 80,
                },
                "list_params": {"date_from": "2026-03-13", "date_to": "2026-03-13", "limit": 10},
                "expect": {"field": "systolic", "created": 118, "updated": 122},
            },
            {
                "name": "sleep",
                "path": "/api/sleep",
                "create": {
                    "start_ts": "2026-03-13T23:00:00",
                    "end_ts": "2026-03-14T07:00:00",
                    "deep_minutes": 100,
                    "light_minutes": 260,
                    "rem_minutes": 80,
                    "source": "manual",
                },
                "update": {
                    "start_ts": "2026-03-14T00:00:00",
                    "end_ts": "2026-03-14T08:15:00",
                    "deep_minutes": 110,
                    "light_minutes": 250,
                    "rem_minutes": 90,
                    "source": "watch",
                },
                "list_params": {"date_from": "2026-03-14", "date_to": "2026-03-14", "limit": 10},
                "expect": {"field": "source", "created": "manual", "updated": "watch"},
            },
            {
                "name": "spo2",
                "path": "/api/spo2",
                "create": {
                    "ts": "2026-03-15T08:30:00",
                    "percentage": 97,
                    "source": "manual",
                },
                "update": {
                    "ts": "2026-03-15T21:10:00",
                    "percentage": 99,
                    "source": "watch",
                },
                "list_params": {"date_from": "2026-03-15", "date_to": "2026-03-15", "limit": 10},
                "expect": {"field": "percentage", "created": 97, "updated": 99},
            },
        )

        for scenario in scenarios:
            with self.subTest(resource=scenario["name"]):
                create_response = self.client.post(
                    scenario["path"],
                    headers=headers,
                    json=scenario["create"],
                )
                self.assertEqual(create_response.status_code, 201, create_response.text)
                created = create_response.json()
                resource_id = created["id"]
                self.assertEqual(created[scenario["expect"]["field"]], scenario["expect"]["created"])

                get_response = self.client.get(
                    f"{scenario['path']}/{resource_id}",
                    headers=headers,
                )
                self.assertEqual(get_response.status_code, 200, get_response.text)
                self.assertEqual(get_response.json()["id"], resource_id)

                list_response = self.client.get(
                    scenario["path"],
                    headers=headers,
                    params=scenario["list_params"],
                )
                self.assertEqual(list_response.status_code, 200, list_response.text)
                list_payload = list_response.json()
                self.assertEqual(len(list_payload), 1)
                self.assertEqual(list_payload[0]["id"], resource_id)

                update_response = self.client.put(
                    f"{scenario['path']}/{resource_id}",
                    headers=headers,
                    json=scenario["update"],
                )
                self.assertEqual(update_response.status_code, 200, update_response.text)
                updated = update_response.json()
                self.assertEqual(updated[scenario["expect"]["field"]], scenario["expect"]["updated"])

                delete_response = self.client.delete(
                    f"{scenario['path']}/{resource_id}",
                    headers=headers,
                )
                self.assertEqual(delete_response.status_code, 204, delete_response.text)

                after_delete_response = self.client.get(
                    scenario["path"],
                    headers=headers,
                )
                self.assertEqual(after_delete_response.status_code, 200, after_delete_response.text)
                self.assertEqual(after_delete_response.json(), [])

    def test_duplicate_health_records_return_conflict(self) -> None:
        token = self._register_athlete()
        headers = self._auth_headers(token)

        first_response = self.client.post(
            "/api/calories",
            headers=headers,
            json={
                "date": "2026-03-20",
                "calories": 2100,
                "notes": "base",
            },
        )
        self.assertEqual(first_response.status_code, 201, first_response.text)

        duplicate_response = self.client.post(
            "/api/calories",
            headers=headers,
            json={
                "date": "2026-03-20",
                "calories": 2200,
                "notes": "duplicate",
            },
        )
        self.assertEqual(duplicate_response.status_code, 409, duplicate_response.text)
        self.assertEqual(duplicate_response.json()["detail"], "Data conflict")

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

    def test_coach_detail_supports_filters_and_pagination(self) -> None:
        athlete_token = self._register_athlete(email="athlete-filter@example.com")
        athlete_headers = self._auth_headers(athlete_token)

        for title, training_date in (
            ("Early Session", "2026-03-10"),
            ("Target Session", "2026-03-18"),
        ):
            response = self.client.post(
                "/api/trainings",
                headers=athlete_headers,
                json={
                    "title": title,
                    "training_type": "Кардио",
                    "date": training_date,
                    "duration_minutes": 50,
                    "distance_km": 9.0,
                },
            )
            self.assertEqual(response.status_code, 201, response.text)

        for ts, percentage in (
            ("2026-03-10T08:00:00", 96),
            ("2026-03-18T08:00:00", 99),
        ):
            response = self.client.post(
                "/api/spo2",
                headers=athlete_headers,
                json={
                    "ts": ts,
                    "percentage": percentage,
                    "source": "manual",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)

        coach_token = self._register_coach(email="coach-filter@example.com")
        coach_headers = self._auth_headers(coach_token)
        link_response = self.client.post(
            "/api/coach/athletes",
            headers=coach_headers,
            json={"email": "athlete-filter@example.com"},
        )
        self.assertEqual(link_response.status_code, 200, link_response.text)
        athlete_id = link_response.json()["athlete_id"]

        filtered_detail_response = self.client.get(
            f"/api/coach/athletes/{athlete_id}",
            headers=coach_headers,
            params={
                "date_from": "2026-03-15",
                "date_to": "2026-03-20",
                "limit": 1,
                "offset": 0,
            },
        )
        self.assertEqual(filtered_detail_response.status_code, 200, filtered_detail_response.text)
        detail = filtered_detail_response.json()
        self.assertEqual(len(detail["trainings"]), 1)
        self.assertEqual(detail["trainings"][0]["title"], "Target Session")
        self.assertEqual(len(detail["spo2_entries"]), 1)
        self.assertEqual(detail["spo2_entries"][0]["percentage"], 99)

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

    def test_ai_prediction_roundtrip_and_background_refresh(self) -> None:
        token = self._register_athlete(email="ai-athlete@example.com")
        headers = self._auth_headers(token)

        with patch(
            "app.services.fitness_ai_service.settings.ai_service_url",
            "http://ai-service.test/predict",
        ), patch(
            "app.services.fitness_ai_service._call_ai_service",
            side_effect=[
                (81.5, "Сохранить объем сна и постепенно повышать интенсивность."),
                (84.0, "Форма обновлена после новой тренировки."),
            ],
        ):
            explicit_prediction_response = self.client.post(
                "/api/ai/predict",
                headers=headers,
                json={"history_limit": 14},
            )
            self.assertEqual(explicit_prediction_response.status_code, 201, explicit_prediction_response.text)
            explicit_prediction = explicit_prediction_response.json()
            self.assertEqual(explicit_prediction["fitness_index"], 81.5)

            create_training_response = self.client.post(
                "/api/trainings",
                headers=headers,
                json={
                    "title": "AI Tempo",
                    "training_type": "Кардио",
                    "date": "2026-03-21",
                    "duration_minutes": 52,
                    "distance_km": 9.3,
                    "avg_hr": 149,
                    "max_hr": 171,
                },
            )
            self.assertEqual(create_training_response.status_code, 201, create_training_response.text)

        last_response = self.client.get(
            "/api/ai/last",
            headers=headers,
        )
        self.assertEqual(last_response.status_code, 200, last_response.text)
        latest = last_response.json()
        self.assertEqual(latest["fitness_index"], 84.0)
        self.assertIn("новой тренировки", latest["recommendations"])

    def test_ai_routes_require_authentication(self) -> None:
        response = self.client.get("/api/ai/last")
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
