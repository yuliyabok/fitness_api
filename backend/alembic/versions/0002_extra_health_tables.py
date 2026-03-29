# Файл: миграция дополнительных таблиц health-метрик.

"""add analyses, calories, cycle tables and trainings.exercises

Revision ID: 0002_extra_health_tables
Revises: 0001_init
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_extra_health_tables"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "trainings" in tables:
        training_columns = {col["name"] for col in inspector.get_columns("trainings")}
        if "exercises" not in training_columns:
            op.add_column(
                "trainings",
                sa.Column("exercises", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )

    if "analysis_entries" not in tables:
        op.create_table(
            "analysis_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("value", sa.String(length=255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "calorie_entries" not in tables:
        op.create_table(
            "calorie_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("calories", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "cycle_events" not in tables:
        op.create_table(
            "cycle_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint("kind IN ('day','excluded','start','end')", name="cycle_events_kind_check"),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "cycle_settings" not in tables:
        op.create_table(
            "cycle_settings",
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("cycle_length_days", sa.Integer(), nullable=True),
            sa.Column("period_length_days", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("athlete_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "cycle_settings" in tables:
        op.drop_table("cycle_settings")
    if "cycle_events" in tables:
        op.drop_table("cycle_events")
    if "calorie_entries" in tables:
        op.drop_table("calorie_entries")
    if "analysis_entries" in tables:
        op.drop_table("analysis_entries")

    if "trainings" in tables:
        training_columns = {col["name"] for col in inspector.get_columns("trainings")}
        if "exercises" in training_columns:
            op.drop_column("trainings", "exercises")
