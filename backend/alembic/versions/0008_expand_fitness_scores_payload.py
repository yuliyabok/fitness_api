# Файл: расширение структуры таблицы AI-оценок физической формы.

"""expand fitness scores payload

Revision ID: 0008_fitness_scores_v2
Revises: 0007_fitness_scores
Create Date: 2026-04-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0008_fitness_scores_v2"
down_revision: Union[str, None] = "0007_fitness_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fitness_scores", sa.Column("fatigue_risk", sa.Float(), nullable=True))
    op.add_column(
        "fitness_scores",
        sa.Column("trend", sa.String(length=32), nullable=True, server_default=sa.text("'stable'")),
    )
    op.execute(
        """
        ALTER TABLE fitness_scores
        ALTER COLUMN recommendations
        TYPE JSONB
        USING CASE
            WHEN recommendations IS NULL OR btrim(recommendations) = '' THEN '[]'::jsonb
            ELSE to_jsonb(ARRAY[recommendations])
        END
        """
    )
    op.execute(
        """
        UPDATE fitness_scores
        SET fatigue_risk = GREATEST(0.0, LEAST(100.0, 100.0 - fitness_index))
        WHERE fatigue_risk IS NULL
        """
    )
    op.execute("UPDATE fitness_scores SET trend = 'stable' WHERE trend IS NULL")
    op.alter_column(
        "fitness_scores",
        "recommendations",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.alter_column("fitness_scores", "fatigue_risk", existing_type=sa.Float(), nullable=False)
    op.alter_column(
        "fitness_scores",
        "trend",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=None,
    )
    op.drop_index("ix_fitness_scores_athlete_id_date", table_name="fitness_scores")
    op.drop_column("fitness_scores", "date")


def downgrade() -> None:
    op.add_column("fitness_scores", sa.Column("date", sa.Date(), nullable=True))
    op.execute("UPDATE fitness_scores SET date = (created_at AT TIME ZONE 'UTC')::date WHERE date IS NULL")
    op.alter_column("fitness_scores", "date", existing_type=sa.Date(), nullable=False)
    op.create_index(
        "ix_fitness_scores_athlete_id_date",
        "fitness_scores",
        ["athlete_id", "date"],
        unique=False,
    )
    op.execute(
        """
        ALTER TABLE fitness_scores
        ALTER COLUMN recommendations
        TYPE TEXT
        USING CASE
            WHEN jsonb_typeof(recommendations) = 'array'
                THEN array_to_string(ARRAY(SELECT jsonb_array_elements_text(recommendations)), E'\n')
            ELSE trim(both '"' from recommendations::text)
        END
        """
    )
    op.drop_column("fitness_scores", "trend")
    op.drop_column("fitness_scores", "fatigue_risk")
