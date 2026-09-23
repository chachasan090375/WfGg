CREATE TABLE IF NOT EXISTS sentinel_identities (
  key_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS technical_release_receipts (
  receipt_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  repository TEXT NOT NULL,
  revision TEXT NOT NULL,
  workflow_name TEXT NOT NULL,
  workflow_run_id TEXT,
  workflow_url TEXT,
  verdict TEXT NOT NULL CHECK(verdict IN ('PASS','BLOCK','UNAVAILABLE')),
  reason_codes_json TEXT NOT NULL,
  audit_digest TEXT,
  advisory_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sentinel_receipts_project ON technical_release_receipts(project_id,created_at);
CREATE INDEX IF NOT EXISTS idx_sentinel_receipts_revision ON technical_release_receipts(repository,revision,created_at);

CREATE TABLE IF NOT EXISTS sentinel_directives (
  directive_id TEXT PRIMARY KEY,
  receipt_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('WARNING','BLOCK','CRITICAL')),
  required_action TEXT NOT NULL,
  reason_codes_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OPEN','DELIVERED','APPLIED')),
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  applied_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sentinel_directives_status ON sentinel_directives(status,created_at);
