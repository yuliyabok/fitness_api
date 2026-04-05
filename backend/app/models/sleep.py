# Файл: ORM-модель для хранения сна.

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SleepEntry(Base):
    __tablename__ = "sleep_entries"
    __table_args__ = (
        Index("ix_sleep_entries_athlete_id_end_ts", "athlete_id", "end_ts"),
        UniqueConstraint("athlete_id", "start_ts", "end_ts", name="uq_sleep_entries_athlete_start_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("athlete_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    light_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rem_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
