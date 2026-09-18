-- WFGG_RADAR_PROFILE_RICH_D1_V6191
-- Separate D1 cache for explicitly observed get.user.info.multi rich fields.
-- Normal fast lookup remains local-only; this table is populated only by the
-- explicit targeted profile refresh route.
CREATE TABLE IF NOT EXISTS radar_profile_rich (
  subject_uid TEXT PRIMARY KEY,
  army_power INTEGER,
  army_kill INTEGER,
  svip_level INTEGER,
  country TEXT,
  avatar_ref TEXT,
  observed_at TEXT NOT NULL,
  source_command TEXT NOT NULL DEFAULT 'get.user.info.multi'
);

CREATE INDEX IF NOT EXISTS idx_radar_profile_rich_observed
  ON radar_profile_rich(observed_at DESC);
