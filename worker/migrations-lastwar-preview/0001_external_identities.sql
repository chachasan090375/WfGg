-- WFGG_LASTWAR_LAB_D1_V1
-- Dedicated PREVIEW database only: wfgg-lastwar-lab.

CREATE TABLE IF NOT EXISTS external_identities (
  id TEXT PRIMARY KEY,
  wfgg_user_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_subject TEXT NOT NULL,
  server_id TEXT NOT NULL DEFAULT '',
  alliance_subject TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING',
  verification_source TEXT,
  verified_at TEXT,
  last_verified_at TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(provider IN ('lastwar')),
  CHECK(status IN ('PENDING','VERIFIED','REVOKED'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_external_identity_provider_subject
  ON external_identities(provider, provider_subject, server_id);

CREATE INDEX IF NOT EXISTS idx_external_identity_user
  ON external_identities(wfgg_user_id, provider, status);

CREATE TABLE IF NOT EXISTS lab_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_wfgg_user_id TEXT,
  action TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  details_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lab_audit_actor
  ON lab_audit_log(actor_wfgg_user_id, created_at);
