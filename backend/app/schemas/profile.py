# Файл: Pydantic-схемы для профиля пользователя.

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AthleteProfileOut(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    age: int | None = None
    gender: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    sport: str | None = None
    created_at: datetime | None = None


class AthleteProfileUpdate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = Field(default=None, max_length=32)
    weight_kg: float | None = Field(default=None, ge=0)
    height_cm: float | None = Field(default=None, ge=0)
    sport: str | None = Field(default=None, max_length=120)


class CoachProfileOut(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    created_at: datetime | None = None

