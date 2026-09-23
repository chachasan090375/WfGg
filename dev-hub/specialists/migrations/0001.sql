CREATE TABLE IF NOT EXISTS authority_identities (
  key_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_assurance_identities (
  key_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_project_identity_project ON project_assurance_identities(project_id,status);
CREATE TABLE IF NOT EXISTS project_events (
  event_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  component_id TEXT,
  component_version TEXT,
  event_digest TEXT NOT NULL,
  fields_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_events_project_revision ON project_events(project_id,revision,observed_at);
CREATE TABLE IF NOT EXISTS specialist_reviews (
  review_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  compromise_digest TEXT NOT NULL,
  verdict TEXT NOT NULL,
  hard_objections_json TEXT NOT NULL,
  soft_objections_json TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL,
  implementation_verified INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_specialist_reviews_project_revision ON specialist_reviews(project_id,revision,created_at);
CREATE TABLE IF NOT EXISTS security_incidents (
  incident_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  response_action TEXT NOT NULL,
  status TEXT NOT NULL,
  corroboration_count INTEGER NOT NULL DEFAULT 0,
  scope TEXT NOT NULL DEFAULT 'PROJECT',
  e_stop_eligible INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS response_directives (
  directive_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_response_directives_status ON response_directives(status,created_at);
