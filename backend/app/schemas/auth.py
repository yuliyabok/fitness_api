# Файл: Pydantic-схемы для авторизации.

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)
    role: str = Field(pattern="^(athlete|coach)$")
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=0, le=120)
    gender: str | None = Field(default=None, max_length=32)
    weight_kg: float | None = Field(default=None, ge=0)
    height_cm: float | None = Field(default=None, ge=0)
    sport: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["athlete", "coach"]
