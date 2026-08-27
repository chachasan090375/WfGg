PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lastwar_pairings (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  code_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lastwar_pairings_user
  ON lastwar_pairings(user_id, expires_at);

CREATE TABLE IF NOT EXISTS lastwar_devices (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  refresh_token_hash TEXT NOT NULL UNIQUE,
  device_name TEXT NOT NULL,
  connector_version TEXT,
  source_uid TEXT,
  created_at TEXT NOT NULL,
  refresh_expires_at TEXT NOT NULL,
  last_seen_at TEXT,
  last_sync_at TEXT,
  revoked_at TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lastwar_devices_user
  ON lastwar_devices(user_id, revoked_at);
CREATE INDEX IF NOT EXISTS idx_lastwar_devices_refresh
  ON lastwar_devices(refresh_token_hash);

CREATE TABLE IF NOT EXISTS lastwar_snapshots (
  user_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  game_uid TEXT NOT NULL,
  server_id TEXT,
  player_name TEXT,
  source_collected_at TEXT,
  received_at TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (device_id) REFERENCES lastwar_devices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lastwar_snapshots_received
  ON lastwar_snapshots(received_at DESC);
