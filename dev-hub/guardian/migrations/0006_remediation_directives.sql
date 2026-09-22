CREATE TABLE IF NOT EXISTS remediation_directives (
  directive_id TEXT PRIMARY KEY,
  source_alert_id TEXT NOT NULL,
  source_event_id TEXT NOT NULL,
  target_actor TEXT NOT NULL,
  target_role TEXT NOT NULL,
  project_id TEXT,
  run_id TEXT,
  severity TEXT NOT NULL CHECK(severity IN ('WARNING','BLOCK','CRITICAL')),
  required_action TEXT NOT NULL,
  rule_codes_json TEXT NOT NULL,
  instructions_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OPEN','DELIVERED','APPLIED','ESCALATED','CANCELLED')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  applied_at TEXT,
  resolution_evidence_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_remediation_directives_status_target
  ON remediation_directives(status,target_actor,target_role,project_id,created_at);

CREATE TABLE IF NOT EXISTS remediation_holds (
  hold_key TEXT PRIMARY KEY,
  directive_id TEXT NOT NULL,
  target_actor TEXT NOT NULL,
  target_role TEXT NOT NULL,
  project_id TEXT,
  run_id TEXT,
  severity TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  cleared_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_remediation_holds_active_target
  ON remediation_holds(active,target_actor,target_role,project_id);
