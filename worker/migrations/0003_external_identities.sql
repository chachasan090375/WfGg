-- WFGG_EXTERNAL_IDENTITIES_LAB_V2
-- Dedicated PREVIEW D1 only. No foreign key to production tables.
-- wfgg_user_id is an opaque reference validated through the production /api/me
-- endpoint, but every write below remains in the laboratory database.

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
