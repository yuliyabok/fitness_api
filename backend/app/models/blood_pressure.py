# Файл: ORM-модель для хранения артериального давления.

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BloodPressureEntry(Base):
    __tablename__ = "blood_pressure_entries"
    __table_args__ = (
        Index("ix_blood_pressure_entries_athlete_id_ts", "athlete_id", "ts"),
        UniqueConstraint(
            "athlete_id",
            "ts",
            "is_morning",
            name="uq_blood_pressure_entries_athlete_ts_is_morning",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("athlete_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_morning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
