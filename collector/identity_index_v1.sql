-- WfGg Collector · Identity Index V1
-- Canonical identity directory for targeted Player Oracle lookups.
-- UID is the only stable primary identity. Pseudos are mutable and may collide.

PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS player_identity(
  game_uid TEXT PRIMARY KEY,
  current_pseudo TEXT NOT NULL,
  pseudo_key TEXT NOT NULL,
  current_server_id TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  last_identity_change TEXT,
  source TEXT NOT NULL DEFAULT 'COLLECTOR',
  confidence TEXT NOT NULL DEFAULT 'OBSERVED'
);

CREATE INDEX IF NOT EXISTS idx_player_identity_pseudo_key
  ON player_identity(pseudo_key);
CREATE INDEX IF NOT EXISTS idx_player_identity_server
  ON player_identity(current_server_id);
CREATE INDEX IF NOT EXISTS idx_player_identity_last_seen
  ON player_identity(last_seen DESC);

-- Alias/history is deliberately many-to-many: a pseudo can be reused by more
-- than one UID and one UID can have several pseudos over time.
CREATE TABLE IF NOT EXISTS player_aliases(
  game_uid TEXT NOT NULL,
  pseudo TEXT NOT NULL,
  pseudo_key TEXT NOT NULL,
  server_id TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0,1)),
  PRIMARY KEY(game_uid,pseudo_key),
  FOREIGN KEY(game_uid) REFERENCES player_identity(game_uid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_player_aliases_lookup
  ON player_aliases(pseudo_key,is_current,last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_player_aliases_uid
  ON player_aliases(game_uid,is_current,last_seen DESC);

-- Coverage is required before we can claim that the directory contains every
-- discoverable player. One row represents the latest known sweep state of a
-- server/world scope.
CREATE TABLE IF NOT EXISTS identity_coverage(
  scope_id TEXT PRIMARY KEY,
  server_id TEXT,
  world_id TEXT,
  status TEXT NOT NULL DEFAULT 'UNKNOWN',
  last_started TEXT,
  last_completed TEXT,
  players_seen INTEGER NOT NULL DEFAULT 0,
  identities_added INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

-- Backfill the canonical directory from the Collector's existing player base.
INSERT INTO player_identity(
  game_uid,current_pseudo,pseudo_key,current_server_id,
  first_seen,last_seen,last_identity_change,source,confidence
)
SELECT
  game_uid,pseudo,lower(trim(pseudo)),server_id,
  first_seen,last_seen,last_seen,'COLLECTOR_BACKFILL','OBSERVED'
FROM players
WHERE trim(game_uid)<>'' AND trim(pseudo)<>''
ON CONFLICT(game_uid) DO UPDATE SET
  current_pseudo=excluded.current_pseudo,
  pseudo_key=excluded.pseudo_key,
  current_server_id=COALESCE(NULLIF(excluded.current_server_id,''),player_identity.current_server_id),
  last_seen=CASE WHEN excluded.last_seen>player_identity.last_seen THEN excluded.last_seen ELSE player_identity.last_seen END;

INSERT INTO player_aliases(
  game_uid,pseudo,pseudo_key,server_id,first_seen,last_seen,is_current
)
SELECT
  game_uid,pseudo,lower(trim(pseudo)),server_id,first_seen,last_seen,1
FROM players
WHERE trim(game_uid)<>'' AND trim(pseudo)<>''
ON CONFLICT(game_uid,pseudo_key) DO UPDATE SET
  pseudo=excluded.pseudo,
  server_id=COALESCE(NULLIF(excluded.server_id,''),player_aliases.server_id),
  last_seen=CASE WHEN excluded.last_seen>player_aliases.last_seen THEN excluded.last_seen ELSE player_aliases.last_seen END,
  is_current=1;

-- Read-only convenience view for the resolver. No uniqueness is assumed on
-- pseudo_key; callers must handle ambiguity explicitly.
CREATE VIEW IF NOT EXISTS identity_resolver AS
SELECT
  i.game_uid,
  i.current_pseudo AS pseudo,
  i.pseudo_key,
  i.current_server_id AS server_id,
  i.first_seen,
  i.last_seen,
  i.confidence,
  1 AS is_current
FROM player_identity i;
