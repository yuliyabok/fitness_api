# Файл: точка входа FastAPI-приложения и регистрация маршрутов.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.models.analysis import AnalysisEntry  # noqa: F401
from app.models.blood_pressure import BloodPressureEntry  # noqa: F401
from app.models.calorie import CalorieEntry  # noqa: F401
from app.models.cycle import CycleEvent, CycleSettings  # noqa: F401
from app.models.sleep import SleepEntry  # noqa: F401
from app.models.spo2 import Spo2Entry  # noqa: F401
from app.models.training import Training  # noqa: F401
from app.models.user import AppUser, AthleteProfile, CoachAthleteLink, CoachProfile  # noqa: F401
from app.core.config import settings
from app.core.errors import register_exception_handlers


app = FastAPI(title="Fitness App Backend", version="0.1.0")

origins = ["*"] if settings.cors_origins.strip() == "*" else [
    item.strip() for item in settings.cors_origins.split(",") if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False if origins == ["*"] else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)

