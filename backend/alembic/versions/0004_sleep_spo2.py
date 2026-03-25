"""add sleep and spo2 tables

Revision ID: 0004_sleep_spo2
Revises: 0003_merge_heads
Create Date: 2026-03-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_sleep_spo2"
down_revision: Union[str, None] = "0003_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "spo2_entries" not in tables:
        op.create_table(
            "spo2_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("percentage", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "sleep_entries" not in tables:
        op.create_table(
            "sleep_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("athlete_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deep_minutes", sa.Integer(), nullable=True),
            sa.Column("light_minutes", sa.Integer(), nullable=True),
            sa.Column("rem_minutes", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["athlete_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sleep_entries" in tables:
        op.drop_table("sleep_entries")
    if "spo2_entries" in tables:
        op.drop_table("spo2_entries")
