"""Scaffolding for third-party wearable-cloud account links
(``integration_connections``) — see backend/db/models/integration.py.

Not used by any active endpoint yet; `backend/routers/integrations.py`
returns 503 "coming soon" for every provider. Added ahead of the first real
Garmin/Polar integration so the frontend's "in arrivo" cards map to a real
(if inert) table/API surface.

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0032'
down_revision: Union[str, None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'integration_connections',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('external_athlete_id', sa.String(), nullable=True),
        sa.Column('access_token', sa.String(), nullable=True),
        sa.Column('refresh_token', sa.String(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.String(), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_foreign_key(
        'fk_integration_connections_user_id_users', 'integration_connections',
        'users', ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.create_unique_constraint(
        'one_connection_per_user_provider', 'integration_connections',
        ['user_id', 'provider'],
    )
    op.create_check_constraint(
        'provider_allowed', 'integration_connections',
        "provider IN ('garmin', 'polar')",
    )
    op.create_check_constraint(
        'status_allowed', 'integration_connections',
        "status IN ('pending', 'active', 'revoked', 'error')",
    )


def downgrade() -> None:
    op.drop_table('integration_connections')
