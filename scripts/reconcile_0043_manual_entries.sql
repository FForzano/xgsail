-- One-time reconciliation for databases that applied the FIRST (broken) 0043.
--
-- The originally-committed 0043 did not create ``regatta_entries.boat_name_normalized``
-- and used different index/constraint names than ``RegattaEntryORM`` declares. Since the
-- backend runs ``alembic upgrade head`` at startup (backend/main.py), any environment that
-- booted that revision is already stamped 0043/0044 and will SKIP the corrected migration --
-- leaving a physical schema the ORM cannot query (every SELECT emits boat_name_normalized,
-- which does not exist -> UndefinedColumn -> HTTP 500 on all /entries endpoints).
--
-- Run this ONLY when ``SELECT version_num FROM alembic_version`` is already 0043 or 0044.
-- At 0042 or lower, deploying and letting Alembic run is sufficient -- do not run this.
--
-- Idempotent: safe to re-run, and safe on a database that is already correct.

BEGIN;

ALTER TABLE regatta_entries ADD COLUMN IF NOT EXISTS boat_name_normalized varchar;

-- Mirrors SqlRegattaRepo._normalized_name(): "name|sail", lower+trimmed. Matches zero rows
-- in practice -- the broken schema made every INSERT on regatta_entries fail, so no manual
-- entry can exist -- but is kept so the script stays correct if that assumption is wrong.
UPDATE regatta_entries
   SET boat_name_normalized = lower(btrim(boat_name)) || '|' || lower(coalesce(btrim(sail_number), ''))
 WHERE boat_id IS NULL AND boat_name_normalized IS NULL
   AND btrim(coalesce(boat_name, '')) <> '';

DROP INDEX IF EXISTS uq_regatta_entries_manual_name;
DROP INDEX IF EXISTS uq_regatta_entries_regatta_id_boat_id;
ALTER TABLE regatta_entries DROP CONSTRAINT IF EXISTS uq_regatta_entries_regatta_id_boat_id;
ALTER TABLE regatta_entries DROP CONSTRAINT IF EXISTS ck_regatta_entries_boat_ref_present;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_regatta_entries_boat_id_or_boat_name') THEN
    ALTER TABLE regatta_entries ADD CONSTRAINT ck_regatta_entries_boat_id_or_boat_name
      CHECK (boat_id IS NOT NULL OR boat_name IS NOT NULL);
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_regatta_entries_regatta_boat ON regatta_entries
  (regatta_id, boat_id) WHERE boat_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_regatta_entries_regatta_manual_name ON regatta_entries
  (regatta_id, boat_name_normalized) WHERE boat_id IS NULL;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_official_standings_regatta_boat') THEN
    ALTER TABLE official_standings RENAME CONSTRAINT uq_official_standings_regatta_boat
      TO uq_official_standings_regatta_id_boat_id;
  END IF;
END $$;

COMMIT;
