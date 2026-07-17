"""Add posts table (club/group feed).

Generic feed post owned by either a club or a group (``owner_type``/
``owner_id`` — no FK on ``owner_id`` since it's polymorphic; validated in the
router instead). ``author_id`` is SET NULL on user deletion so a post outlives
its author leaving the app; ``image_id`` likewise on image deletion. No
``updated_at`` — posts are create/delete only, no edit.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'posts',
        sa.Column('id', sa.Uuid(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('owner_type', sa.String(), nullable=False),
        sa.Column('owner_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('author_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('image_id', sa.Uuid(as_uuid=True), nullable=True),
        sa.CheckConstraint("owner_type IN ('club', 'group')", name=op.f('ck_posts_owner_type_allowed')),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_posts_author_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['image_id'], ['images.id'], name=op.f('fk_posts_image_id_images'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_posts')),
    )
    op.create_index(op.f('ix_posts_owner'), 'posts', ['owner_type', 'owner_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_posts_owner'), table_name='posts')
    op.drop_table('posts')
