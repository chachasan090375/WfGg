-- WFGG_EXTERNAL_IDENTITIES_V1
-- Prépare la liaison de comptes externes (Last War en premier) sans modifier
-- l'authentification actuelle par code WfGg.

CREATE TABLE IF NOT EXISTS external_identities (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
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
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  CHECK(provider IN ('lastwar')),
  CHECK(status IN ('PENDING','VERIFIED','REVOKED'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_external_identity_provider_subject
  ON external_identities(provider, provider_subject, server_id);

CREATE INDEX IF NOT EXISTS idx_external_identity_user
  ON external_identities(user_id, provider, status);
