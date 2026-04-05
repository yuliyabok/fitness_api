# Файл: Pydantic-схемы для сатурации.

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Spo2Create(BaseModel):
    ts: datetime
    percentage: int = Field(ge=70, le=100)
    source: str = "manual"


class Spo2Update(Spo2Create):
    pass


class Spo2Out(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    ts: datetime
    percentage: int
    source: str

    class Config:
        from_attributes = True
