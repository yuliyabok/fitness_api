# Файл: ORM-модель для хранения AI-оценки физической формы.

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FitnessScore(Base):
    __tablename__ = "fitness_scores"
    __table_args__ = (
        Index("ix_fitness_scores_athlete_id_created_at", "athlete_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("athlete_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    fitness_index: Mapped[float] = mapped_column(Float, nullable=False)
    fatigue_risk: Mapped[float] = mapped_column(Float, nullable=False)
    trend: Mapped[str] = mapped_column(String(length=32), nullable=False)
    recommendations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
