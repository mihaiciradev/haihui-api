"""admin totp lockout

Revision ID: a1b2c3d4e5f6
Revises: 5dfecc15823e
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5dfecc15823e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('admin_failed_totp_attempts', sa.SmallInteger(), nullable=False, server_default='0'),
    )
    op.add_column(
        'users',
        sa.Column('admin_totp_locked_until', sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column('users', 'admin_failed_totp_attempts', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'admin_totp_locked_until')
    op.drop_column('users', 'admin_failed_totp_attempts')
