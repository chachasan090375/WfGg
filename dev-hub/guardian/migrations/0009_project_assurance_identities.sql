CREATE TABLE IF NOT EXISTS project_assurance_identities (
  key_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guardian_project_assurance_identity_project
  ON project_assurance_identities(project_id,status);
