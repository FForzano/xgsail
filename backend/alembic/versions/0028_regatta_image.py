"""Add ``image_id`` to regattas.

Lets a regatta detail page show a hero image, same upload-ticket flow as
``clubs.logo_id`` / ``groups.profile_image_id``.

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('regattas', sa.Column('image_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f('fk_regattas_image_id_images'), 'regattas', 'images', ['image_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_regattas_image_id_images'), 'regattas', type_='foreignkey')
    op.drop_column('regattas', 'image_id')
