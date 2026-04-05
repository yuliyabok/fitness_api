# Файл: миграция индексов и ограничений уникальности для исторических данных спортсмена.

"""add indexes and uniqueness for athlete history tables

Revision ID: 0006_history_indexes
Revises: 0005_profiles_and_coach_links
Create Date: 2026-03-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_history_indexes"
down_revision: Union[str, None] = "0005_profiles_and_coach_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_DEFINITIONS = (
    ("analysis_entries", "ix_analysis_entries_athlete_id_date", ("athlete_id", "date")),
    ("calorie_entries", "ix_calorie_entries_athlete_id_date", ("athlete_id", "date")),
    ("blood_pressure_entries", "ix_blood_pressure_entries_athlete_id_ts", ("athlete_id", "ts")),
    ("cycle_events", "ix_cycle_events_athlete_id_date", ("athlete_id", "date")),
    ("sleep_entries", "ix_sleep_entries_athlete_id_end_ts", ("athlete_id", "end_ts")),
    ("spo2_entries", "ix_spo2_entries_athlete_id_ts", ("athlete_id", "ts")),
    ("trainings", "ix_trainings_athlete_id_date", ("athlete_id", "date")),
)

UNIQUE_DEFINITIONS = (
    (
        "analysis_entries",
        "uq_analysis_entries_athlete_date_title",
        ("athlete_id", "date", "title"),
    ),
    ("calorie_entries", "uq_calorie_entries_athlete_date", ("athlete_id", "date")),
    (
        "blood_pressure_entries",
        "uq_blood_pressure_entries_athlete_ts_is_morning",
        ("athlete_id", "ts", "is_morning"),
    ),
    ("cycle_events", "uq_cycle_events_athlete_date_kind", ("athlete_id", "date", "kind")),
    ("sleep_entries", "uq_sleep_entries_athlete_start_end", ("athlete_id", "start_ts", "end_ts")),
    ("spo2_entries", "uq_spo2_entries_athlete_ts", ("athlete_id", "ts")),
)


def _delete_duplicates(table_name: str, partition_columns: Sequence[str]) -> None:
    partition_sql = ", ".join(partition_columns)
    op.execute(
        sa.text(
            f"""
            DELETE FROM {table_name}
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY {partition_sql}
                            ORDER BY created_at DESC NULLS LAST, id DESC
                        ) AS row_number
                    FROM {table_name}
                ) ranked
                WHERE ranked.row_number > 1
            )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table_name, index_name, columns in INDEX_DEFINITIONS:
        if table_name not in tables:
            continue
        existing_indexes = {item["name"] for item in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, list(columns), unique=False)

    for table_name, constraint_name, columns in UNIQUE_DEFINITIONS:
        if table_name not in tables:
            continue
        existing_unique_constraints = {
            item["name"] for item in inspector.get_unique_constraints(table_name) if item["name"]
        }
        if constraint_name in existing_unique_constraints:
            continue
        _delete_duplicates(table_name, columns)
        op.create_unique_constraint(constraint_name, table_name, list(columns))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table_name, constraint_name, _columns in reversed(UNIQUE_DEFINITIONS):
        if table_name not in tables:
            continue
        existing_unique_constraints = {
            item["name"] for item in inspector.get_unique_constraints(table_name) if item["name"]
        }
        if constraint_name in existing_unique_constraints:
            op.drop_constraint(constraint_name, table_name, type_="unique")

    for table_name, index_name, _columns in reversed(INDEX_DEFINITIONS):
        if table_name not in tables:
            continue
        existing_indexes = {item["name"] for item in inspector.get_indexes(table_name)}
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)
