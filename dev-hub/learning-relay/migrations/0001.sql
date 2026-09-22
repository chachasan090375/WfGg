CREATE TABLE IF NOT EXISTS identities (
  key_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK(role IN ('CENTRAL','PRODUCER')),
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  project_id TEXT,
  deployment_id TEXT,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_identities_scope ON identities(project_id,deployment_id,status);

CREATE TABLE IF NOT EXISTS learning_deltas (
  delta_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  deployment_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  observed_at TEXT NOT NULL,
  severity TEXT,
  payload_json TEXT NOT NULL,
  producer_key_id TEXT NOT NULL,
  received_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PENDING','ACKED')),
  acked_at TEXT,
  FOREIGN KEY(producer_key_id) REFERENCES identities(key_id)
);
CREATE INDEX IF NOT EXISTS idx_learning_pending ON learning_deltas(status,received_at);
CREATE INDEX IF NOT EXISTS idx_learning_project ON learning_deltas(project_id,observed_at);
