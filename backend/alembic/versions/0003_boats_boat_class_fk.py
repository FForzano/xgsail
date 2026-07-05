"""Replace free-text ``boats.type`` with a ``boat_class_id`` FK.

Boat class is catalog data (``boat_classes``, superadmin-managed) — a free
string invited drift and couldn't join polars/regatta class filters.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'boats',
        sa.Column('boat_class_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None, 'boats', 'boat_classes', ['boat_class_id'], ['id'], ondelete='SET NULL'
    )
    op.drop_column('boats', 'type')


def downgrade() -> None:
    op.add_column('boats', sa.Column('type', sa.String(), nullable=True))
    op.drop_constraint('fk_boats_boat_class_id_boat_classes', 'boats', type_='foreignkey')
    op.drop_column('boats', 'boat_class_id')
