CREATE TABLE IF NOT EXISTS project_functional_events (
  event_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  application_version TEXT NOT NULL,
  assurance_role TEXT NOT NULL CHECK(assurance_role='guardian'),
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  event_digest TEXT NOT NULL,
  fields_json TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guardian_project_events_project
  ON project_functional_events(project_id,application_version,received_at);
