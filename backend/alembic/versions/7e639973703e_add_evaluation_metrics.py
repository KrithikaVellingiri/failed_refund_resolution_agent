"""add_evaluation_metrics

Revision ID: 7e639973703e
Revises: bd3b75032c71
Create Date: 2026-09-05 16:06:10.858731

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e639973703e'
down_revision: Union[str, Sequence[str], None] = 'bd3b75032c71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE evaluation_runs ADD COLUMN metrics JSONB;")
    op.execute("ALTER TABLE evaluation_results ADD COLUMN reason_codes JSONB;")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE evaluation_results DROP COLUMN reason_codes;")
    op.execute("ALTER TABLE evaluation_runs DROP COLUMN metrics;")
