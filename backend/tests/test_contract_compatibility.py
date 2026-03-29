# Файл: smoke-tests на совместимость backend-контракта с Flutter-клиентом.

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://fitness:fitness@localhost:5432/fitness_test",
)
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.api.routes import cycle  # noqa: E402
from app.core.errors import _format_validation_error  # noqa: E402
from app.main import app  # noqa: E402
from app.models.cycle import CycleSettings  # noqa: E402
from app.models.training import Training  # noqa: E402
from app.schemas.coach import CoachAthleteDetailOut  # noqa: E402


class BackendContractCompatibilityTests(unittest.TestCase):
    def _find_route(self, path: str, method: str):
        for route in app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                return route
        self.fail(f"Route {method} {path} not found")

    def test_create_endpoints_use_created_status(self) -> None:
        expectations = {
            ("POST", "/api/auth/register"): 201,
            ("POST", "/api/trainings"): 201,
            ("POST", "/api/analyses"): 201,
            ("POST", "/api/blood-pressure"): 201,
            ("POST", "/api/calories"): 201,
            ("POST", "/api/sleep"): 201,
            ("POST", "/api/spo2"): 201,
        }

        for (method, path), status_code in expectations.items():
            with self.subTest(method=method, path=path):
                route = self._find_route(path, method)
                self.assertEqual(route.status_code, status_code)

    def test_cycle_routes_raise_400_for_invalid_kind(self) -> None:
        fake_user = SimpleNamespace(id="athlete-id")

        with self.assertRaises(HTTPException) as list_ctx:
            cycle.list_cycle_events(kind="invalid", db=object(), user=fake_user)
        self.assertEqual(list_ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as replace_ctx:
            cycle.replace_cycle_events(
                payload=SimpleNamespace(kind="invalid", dates=[]),
                db=object(),
                user=fake_user,
            )
        self.assertEqual(replace_ctx.exception.status_code, 400)

    def test_validation_error_is_reduced_to_plain_detail_string(self) -> None:
        exc = RequestValidationError(
            [
                {
                    "loc": ("body", "email"),
                    "msg": "Field required",
                    "type": "missing",
                },
                {
                    "loc": ("body", "password"),
                    "msg": "String should have at least 6 characters",
                    "type": "string_too_short",
                },
            ]
        )

        self.assertEqual(
            _format_validation_error(exc),
            "email: Field required; password: String should have at least 6 characters",
        )

    def test_coach_detail_schema_uses_independent_lists(self) -> None:
        first = CoachAthleteDetailOut(
            athlete_id="00000000-0000-0000-0000-000000000001",
            first_name="Anna",
            last_name="Ivanova",
            email="anna@example.com",
        )
        second = CoachAthleteDetailOut(
            athlete_id="00000000-0000-0000-0000-000000000002",
            first_name="Maria",
            last_name="Petrova",
            email="maria@example.com",
        )

        self.assertIsNot(first.trainings, second.trainings)
        self.assertIsNot(first.analyses, second.analyses)
        self.assertIsNot(first.calories, second.calories)
        self.assertIsNot(first.blood_pressures, second.blood_pressures)
        self.assertIsNot(first.sleep_entries, second.sleep_entries)
        self.assertIsNot(first.spo2_entries, second.spo2_entries)

    def test_models_have_runtime_updated_at_hooks(self) -> None:
        self.assertIsNotNone(Training.__table__.c.updated_at.onupdate)
        self.assertIsNotNone(CycleSettings.__table__.c.updated_at.onupdate)


if __name__ == "__main__":
    unittest.main()
