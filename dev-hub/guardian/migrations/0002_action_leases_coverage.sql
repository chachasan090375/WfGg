CREATE TABLE IF NOT EXISTS action_leases (
  action_id TEXT PRIMARY KEY,
  pre_event_id TEXT NOT NULL,
  post_event_id TEXT,
  actor TEXT NOT NULL,
  subject_role TEXT NOT NULL,
  action TEXT NOT NULL,
  permission TEXT NOT NULL,
  project_id TEXT,
  run_id TEXT,
  opened_at TEXT NOT NULL,
  deadline_at TEXT NOT NULL,
  closed_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED','EXPIRED','DENIED')),
  last_verdict TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_leases_status_deadline ON action_leases(status,deadline_at);

CREATE TABLE IF NOT EXISTS expected_components (
  component_id TEXT PRIMARY KEY,
  role TEXT NOT NULL,
  kind TEXT NOT NULL,
  enforcement_point TEXT NOT NULL,
  criticality TEXT NOT NULL CHECK(criticality IN ('BLOCK','CRITICAL')),
  source_digest TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coverage_heartbeats (
  component_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  hook_active INTEGER NOT NULL,
  details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coverage_heartbeats_last_seen ON coverage_heartbeats(last_seen);
