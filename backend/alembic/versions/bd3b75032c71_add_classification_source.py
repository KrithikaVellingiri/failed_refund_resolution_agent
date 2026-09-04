"""add_classification_source

Revision ID: bd3b75032c71
Revises: 34085a44cbe9
Create Date: 2026-09-04 05:28:59.040652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd3b75032c71'
down_revision: Union[str, Sequence[str], None] = '34085a44cbe9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE classification_source AS ENUM ('MATCHED_RULE', 'UNRECOGNIZED_DEFAULTED');")
    op.execute("ALTER TABLE refund_cases ADD COLUMN classification_source classification_source NOT NULL DEFAULT 'MATCHED_RULE';")
    op.execute("ALTER TABLE refund_cases ALTER COLUMN classification_source DROP DEFAULT;")


def downgrade() -> None:
    op.execute("ALTER TABLE refund_cases DROP COLUMN classification_source;")
    op.execute("DROP TYPE classification_source;")
