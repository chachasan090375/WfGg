CREATE TABLE IF NOT EXISTS task_contract_leases (
  action_id TEXT PRIMARY KEY,
  subject_role TEXT NOT NULL,
  subject_contract_id TEXT,
  subject_contract_version TEXT,
  binding_digest TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED','MISMATCH'))
);
CREATE INDEX IF NOT EXISTS idx_task_contract_leases_status
  ON task_contract_leases(status, opened_at);
