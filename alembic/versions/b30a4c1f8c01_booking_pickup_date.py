"""booking pickup date

Revision ID: b30a4c1f8c01
Revises: 094d42664349
Create Date: 2026-08-14 15:53:21.000890

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b30a4c1f8c01'
down_revision: Union[str, None] = '094d42664349'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('pickup_date', sa.Date(), nullable=True))
    op.execute('UPDATE bookings SET pickup_date = storage_date WHERE pickup_date IS NULL')
    op.alter_column('bookings', 'pickup_date', nullable=False)
    op.create_index(op.f('ix_bookings_pickup_date'), 'bookings', ['pickup_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bookings_pickup_date'), table_name='bookings')
    op.drop_column('bookings', 'pickup_date')
