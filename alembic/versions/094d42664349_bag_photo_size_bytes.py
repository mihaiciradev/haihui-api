"""bag photo size bytes

Revision ID: 094d42664349
Revises: 9ebb48f32c95
Create Date: 2026-08-14 14:10:39.181458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '094d42664349'
down_revision: Union[str, None] = '9ebb48f32c95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bag_photos', sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0')
    )
    op.alter_column('bag_photos', 'size_bytes', server_default=None)


def downgrade() -> None:
    op.drop_column('bag_photos', 'size_bytes')
