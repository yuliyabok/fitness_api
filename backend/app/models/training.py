# Файл: ORM-модель для хранения тренировок.

import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Training(Base):
    __tablename__ = "trainings"
    __table_args__ = (
        Index("ix_trainings_athlete_id_date", "athlete_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("athlete_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    training_type: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_types: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    sport: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(nullable=True)
    elevation_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_zone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hr_zone_minutes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    exercises: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    feeling_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
