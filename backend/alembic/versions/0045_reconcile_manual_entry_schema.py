"""Repair databases that applied the first, broken 0043.

The originally-shipped 0043 did not create ``regatta_entries.boat_name_normalized``
and named its indexes/constraints differently from ``RegattaEntryORM``. Every
SELECT of that model therefore emitted a column the database did not have
(UndefinedColumn -> HTTP 500 on all ``/api/regattas/{id}/entries`` routes).

0043 has since been corrected, but that does not help an already-deployed
database: the backend runs ``upgrade head`` at startup (``backend/main.py``), so
such an environment is already stamped 0044 and Alembic will skip the corrected
revision forever. Deploys are automatic (Watchtower pulls ``*-latest``), so a
repair that needs someone to open psql would simply never run. Hence a new
revision — the only thing that is guaranteed to execute on the next boot.

Every statement is written to be a no-op where the schema is already right, so
this is equally safe on a database built from the corrected 0043 and on one
carrying the broken shape.

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0045'
down_revision: Union[str, None] = '0044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('ALTER TABLE regatta_entries ADD COLUMN IF NOT EXISTS boat_name_normalized varchar')

    # Mirrors SqlRegattaRepo._normalized_name(): "name|sail", lower+trimmed.
    # Matches nothing in practice — under the broken schema every INSERT into
    # regatta_entries failed, so no manual entry can exist — but keeps the
    # revision correct if that reasoning turns out not to hold somewhere.
    op.execute("""
        UPDATE regatta_entries
           SET boat_name_normalized =
               lower(btrim(boat_name)) || '|' || lower(coalesce(btrim(sail_number), ''))
         WHERE boat_id IS NULL AND boat_name_normalized IS NULL
           AND btrim(coalesce(boat_name, '')) <> ''
    """)

    op.execute('DROP INDEX IF EXISTS uq_regatta_entries_manual_name')
    op.execute('DROP INDEX IF EXISTS uq_regatta_entries_regatta_id_boat_id')
    op.execute('ALTER TABLE regatta_entries '
               'DROP CONSTRAINT IF EXISTS uq_regatta_entries_regatta_id_boat_id')
    op.execute('ALTER TABLE regatta_entries '
               'DROP CONSTRAINT IF EXISTS ck_regatta_entries_boat_ref_present')

    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_regatta_entries_boat_id_or_boat_name'
          ) THEN
            ALTER TABLE regatta_entries ADD CONSTRAINT ck_regatta_entries_boat_id_or_boat_name
              CHECK (boat_id IS NOT NULL OR boat_name IS NOT NULL);
          END IF;
        END $$
    """)

    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_regatta_entries_regatta_boat '
               'ON regatta_entries (regatta_id, boat_id) WHERE boat_id IS NOT NULL')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_regatta_entries_regatta_manual_name '
               'ON regatta_entries (regatta_id, boat_name_normalized) WHERE boat_id IS NULL')

    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_official_standings_regatta_boat'
          ) THEN
            ALTER TABLE official_standings RENAME CONSTRAINT uq_official_standings_regatta_boat
              TO uq_official_standings_regatta_id_boat_id;
          END IF;
        END $$
    """)

    # Unrelated to 0043, same class of bug: 0031 passed an already-prefixed name
    # to create_check_constraint, which prefixes again — so databases built
    # before that was fixed carry ck_posts_ck_posts_single_event_link while a
    # fresh build gets ck_posts_single_event_link. Harmless at runtime, but it
    # makes 0031's downgrade fail on exactly the deployed databases, so
    # converge the two here.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_posts_ck_posts_single_event_link'
          ) AND NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_posts_single_event_link'
          ) THEN
            ALTER TABLE posts RENAME CONSTRAINT ck_posts_ck_posts_single_event_link
              TO ck_posts_single_event_link;
          END IF;
        END $$
    """)


def downgrade() -> None:
    """Deliberately empty: this revision only brings a schema up to what 0043
    already describes, so 0043's own downgrade is what undoes it. Re-creating
    the broken shape here would mean deliberately reintroducing the outage."""
