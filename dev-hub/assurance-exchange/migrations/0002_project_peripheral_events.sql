CREATE TABLE IF NOT EXISTS project_assurance_identities (
  key_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_exchange_project_assurance_identity_project
  ON project_assurance_identities(project_id,status);

CREATE TABLE IF NOT EXISTS peripheral_project_events (
  event_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  application_version TEXT NOT NULL,
  assurance_role TEXT NOT NULL CHECK(assurance_role IN ('curator','bastion','intendant')),
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  component_id TEXT,
  component_version TEXT,
  event_digest TEXT NOT NULL,
  fields_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exchange_peripheral_events_project
  ON peripheral_project_events(project_id,application_version,assurance_role,observed_at);
CREATE INDEX IF NOT EXISTS idx_exchange_peripheral_events_role
  ON peripheral_project_events(assurance_role,severity,observed_at);
