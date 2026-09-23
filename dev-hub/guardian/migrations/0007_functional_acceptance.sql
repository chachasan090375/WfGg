CREATE TABLE IF NOT EXISTS project_functional_contracts (
  project_id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL,
  contract_digest TEXT NOT NULL,
  contract_json TEXT NOT NULL,
  pinned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS functional_acceptance_receipts (
  receipt_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  contract_id TEXT NOT NULL,
  contract_digest TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('PASS','BLOCK','CRITICAL')),
  reason_codes_json TEXT NOT NULL,
  required_criteria_count INTEGER NOT NULL,
  passed_required_criteria_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guardian_functional_receipts_project ON functional_acceptance_receipts(project_id,created_at);
CREATE INDEX IF NOT EXISTS idx_guardian_functional_receipts_revision ON functional_acceptance_receipts(project_id,revision,created_at);
