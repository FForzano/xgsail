"""Per-user free-text templates for session crew notes (``note_templates``)
— a user's own reusable snippets (name + body) to prefill the notes-editing
textarea. Private to the owner, no sharing/club/group/boat link. See
backend/db/models/note_template.py.

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0037'
down_revision: Union[str, None] = '0036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'note_templates',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_foreign_key(
        'fk_note_templates_user_id_users', 'note_templates',
        'users', ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index('ix_note_templates_user_id', 'note_templates', ['user_id'])


def downgrade() -> None:
    op.drop_table('note_templates')
