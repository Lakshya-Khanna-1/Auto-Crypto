"""add_risk_columns

Revision ID: 3af27c5eee26
Revises: e289ccc9edd8
Create Date: 2026-07-12 14:46:10.644292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3af27c5eee26'
down_revision: Union[str, None] = 'e289ccc9edd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("signals", sa.Column("risk_decision", sa.String(), nullable=True))
    op.add_column("signals", sa.Column("risk_reason", sa.String(), nullable=True))
    op.add_column("killswitch_events", sa.Column("details_json", sa.String(), nullable=True))
    op.add_column("killswitch_events", sa.Column("positions_flattened", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("killswitch_events") as batch_op:
        batch_op.drop_column("positions_flattened")
        batch_op.drop_column("details_json")
    with op.batch_alter_table("signals") as batch_op:
        batch_op.drop_column("risk_reason")
        batch_op.drop_column("risk_decision")
        batch_op.drop_column("confidence")
