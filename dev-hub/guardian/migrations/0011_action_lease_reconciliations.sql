CREATE TABLE IF NOT EXISTS action_lease_reconciliations (
  receipt_id TEXT PRIMARY KEY,
  action_id TEXT NOT NULL UNIQUE,
  reconciler_actor TEXT NOT NULL,
  source_alert_id TEXT NOT NULL,
  remediation_directive_id TEXT NOT NULL,
  evidence_digest TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  reconciled_at TEXT NOT NULL,
  result TEXT NOT NULL CHECK(result IN ('PASS'))
);

CREATE INDEX IF NOT EXISTS idx_action_lease_reconciliations_action
  ON action_lease_reconciliations(action_id);
