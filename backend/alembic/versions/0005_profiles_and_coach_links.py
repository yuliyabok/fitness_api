# Файл: миграция профилей и связей между тренером и спортсменом.

"""add full athlete profile fields and coach-athlete links

Revision ID: 0005_profiles_and_coach_links
Revises: 0004_sleep_spo2
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_profiles_and_coach_links"
down_revision: Union[str, None] = "0004_sleep_spo2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    athlete_columns = {col["name"] for col in inspector.get_columns("athlete_profiles")}

    if "age" not in athlete_columns:
        op.add_column("athlete_profiles", sa.Column("age", sa.Integer(), nullable=True))
    if "gender" not in athlete_columns:
        op.add_column("athlete_profiles", sa.Column("gender", sa.String(length=32), nullable=True))
    if "weight_kg" not in athlete_columns:
        op.add_column("athlete_profiles", sa.Column("weight_kg", sa.Float(), nullable=True))
    if "height_cm" not in athlete_columns:
        op.add_column("athlete_profiles", sa.Column("height_cm", sa.Float(), nullable=True))
    if "sport" not in athlete_columns:
        op.add_column("athlete_profiles", sa.Column("sport", sa.String(length=120), nullable=True))

    tables = set(inspector.get_table_names())
    if "coach_athlete_links" not in tables:
        op.create_table(
            "coach_athlete_links",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("coach_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["coach_id"], ["coach_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("coach_id", "athlete_id", name="uq_coach_athlete_link"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "coach_athlete_links" in tables:
        op.drop_table("coach_athlete_links")

    athlete_columns = {col["name"] for col in inspector.get_columns("athlete_profiles")}
    for column in ("sport", "height_cm", "weight_kg", "gender", "age"):
        if column in athlete_columns:
            op.drop_column("athlete_profiles", column)
