"""merge 0002 heads

Revision ID: 0003_merge_heads
Revises: 0002_calories_cycle, 0002_extra_health_tables
Create Date: 2026-03-07
"""

from typing import Sequence, Union


revision: str = "0003_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0002_calories_cycle",
    "0002_extra_health_tables",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
