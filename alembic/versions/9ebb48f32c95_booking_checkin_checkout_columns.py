"""booking checkin checkout columns

Revision ID: 9ebb48f32c95
Revises: a1b2c3d4e5f6
Create Date: 2026-08-13 20:12:51.884468

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ebb48f32c95'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('checked_in_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bookings', sa.Column('checked_in_staff_id', sa.UUID(), nullable=True))
    op.add_column('bookings', sa.Column('checked_out_staff_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_bookings_checked_in_staff_id', 'bookings', 'staff_members', ['checked_in_staff_id'], ['id']
    )
    op.create_foreign_key(
        'fk_bookings_checked_out_staff_id', 'bookings', 'staff_members', ['checked_out_staff_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_bookings_checked_out_staff_id', 'bookings', type_='foreignkey')
    op.drop_constraint('fk_bookings_checked_in_staff_id', 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'checked_out_staff_id')
    op.drop_column('bookings', 'checked_in_staff_id')
    op.drop_column('bookings', 'checked_in_at')
