import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.schemas.analysis import AnalysisOut
from app.schemas.blood_pressure import BloodPressureOut
from app.schemas.calorie import CalorieOut
from app.schemas.sleep import SleepOut
from app.schemas.spo2 import Spo2Out
from app.schemas.training import TrainingOut


class CoachLinkedAthleteOut(BaseModel):
    athlete_id: uuid.UUID
    first_name: str
    last_name: str
    email: EmailStr
    age: int | None = None
    gender: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    sport: str | None = None


class CoachAthleteDetailOut(CoachLinkedAthleteOut):
    trainings: list[TrainingOut] = []
    analyses: list[AnalysisOut] = []
    calories: list[CalorieOut] = []
    blood_pressures: list[BloodPressureOut] = []
    sleep_entries: list[SleepOut] = []
    spo2_entries: list[Spo2Out] = []


class CoachLinkAthleteRequest(BaseModel):
    email: EmailStr


class CoachLinkAthleteResponse(BaseModel):
    athlete_id: uuid.UUID
    linked_at: datetime