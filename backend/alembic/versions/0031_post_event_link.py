"""Link a post to the activity/regatta it announces.

Optional, mutually-exclusive FKs so a club/group post can double as an
announcement for an event it organizes, while plain news posts (neither
set) keep working unchanged. ``ON DELETE SET NULL`` — the post survives the
event being deleted, it just stops linking anywhere.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0031'
down_revision: Union[str, None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('activity_id', sa.Uuid(as_uuid=True), nullable=True))
    op.add_column('posts', sa.Column('regatta_id', sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_posts_activity_id_activities', 'posts', 'activities', ['activity_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_posts_regatta_id_regattas', 'posts', 'regattas', ['regatta_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_check_constraint(
        'single_event_link', 'posts',
        'activity_id IS NULL OR regatta_id IS NULL',
    )


def downgrade() -> None:
    # `drop_constraint` applies the same `ck_<table>_` naming convention as
    # `create_check_constraint`, so it must be given the same bare name — an
    # already-prefixed one gets prefixed twice
    # (`ck_posts_ck_posts_single_event_link`) and the DROP fails.
    op.drop_constraint('single_event_link', 'posts', type_='check')
    op.drop_constraint('fk_posts_regatta_id_regattas', 'posts', type_='foreignkey')
    op.drop_constraint('fk_posts_activity_id_activities', 'posts', type_='foreignkey')
    op.drop_column('posts', 'regatta_id')
    op.drop_column('posts', 'activity_id')
