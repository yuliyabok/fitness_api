# Файл: миграция для таблицы AI-оценок физической формы.

"""create fitness scores table

Revision ID: 0007_fitness_scores
Revises: 0006_indexes_and_history_constraints
Create Date: 2026-04-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0007_fitness_scores"
down_revision: Union[str, None] = "0006_indexes_and_history_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fitness_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("fitness_index", sa.Float(), nullable=False),
        sa.Column("recommendations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fitness_scores_athlete_id_date",
        "fitness_scores",
        ["athlete_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_fitness_scores_athlete_id_created_at",
        "fitness_scores",
        ["athlete_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fitness_scores_athlete_id_created_at", table_name="fitness_scores")
    op.drop_index("ix_fitness_scores_athlete_id_date", table_name="fitness_scores")
    op.drop_table("fitness_scores")
