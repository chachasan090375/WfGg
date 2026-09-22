CREATE TABLE IF NOT EXISTS guardian_identities (
  key_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS role_contracts (
  contract_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  allowed_actions_json TEXT NOT NULL,
  forbidden_actions_json TEXT NOT NULL,
  allowed_permissions_json TEXT NOT NULL,
  required_evidence_json TEXT NOT NULL,
  unknown_role INTEGER NOT NULL DEFAULT 0,
  source_digest TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS governance_events (
  event_id TEXT PRIMARY KEY,
  received_at TEXT NOT NULL,
  phase TEXT NOT NULL,
  actor TEXT NOT NULL,
  subject_role TEXT NOT NULL,
  action TEXT NOT NULL,
  task_kind TEXT,
  permission TEXT,
  project_id TEXT,
  run_id TEXT,
  verdict TEXT NOT NULL,
  severity TEXT NOT NULL,
  contract_id TEXT,
  reason_codes_json TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guardian_events_project ON governance_events(project_id,received_at);
CREATE INDEX IF NOT EXISTS idx_guardian_events_verdict ON governance_events(verdict,received_at);

CREATE TABLE IF NOT EXISTS guardian_alerts (
  alert_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OPEN','ACKED')),
  summary TEXT NOT NULL,
  reason_codes_json TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guardian_alerts_status ON guardian_alerts(status,created_at);
