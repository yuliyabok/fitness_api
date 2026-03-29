# Файл: главный роутер, который собирает все маршруты backend API.

from fastapi import APIRouter

from app.api.routes import analyses, auth, blood_pressure, calories, coach, cycle, health, profile, sleep, spo2, trainings

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(analyses.router)
api_router.include_router(coach.router)
api_router.include_router(trainings.router)
api_router.include_router(blood_pressure.router)
api_router.include_router(calories.router)
api_router.include_router(spo2.router)
api_router.include_router(sleep.router)
api_router.include_router(cycle.router)
