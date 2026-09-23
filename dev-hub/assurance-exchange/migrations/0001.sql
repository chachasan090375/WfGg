CREATE TABLE IF NOT EXISTS exchange_identities (
  key_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','REVOKED')),
  public_key_spki_b64 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS assurance_observations (
  observation_id TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK(source IN ('GUARDIAN','SENTINEL')),
  source_receipt_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  verdict TEXT NOT NULL,
  severity TEXT NOT NULL,
  reason_codes_json TEXT NOT NULL,
  signal_codes_json TEXT NOT NULL,
  source_refs_json TEXT NOT NULL,
  source_payload_digest TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(source,source_receipt_id)
);
CREATE INDEX IF NOT EXISTS idx_exchange_observation_project_revision
  ON assurance_observations(project_id,revision,source,created_at);

CREATE TABLE IF NOT EXISTS assurance_correlations (
  correlation_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  guardian_observation_id TEXT NOT NULL,
  sentinel_observation_id TEXT NOT NULL,
  guardian_receipt_id TEXT NOT NULL,
  sentinel_receipt_id TEXT NOT NULL,
  priority TEXT NOT NULL CHECK(priority IN ('BLOCKER','OPTIMIZE','OBSERVE')),
  recommendation_type TEXT NOT NULL,
  causality_status TEXT NOT NULL CHECK(causality_status IN ('UNPROVEN','CORRELATED')),
  reason_codes_json TEXT NOT NULL,
  signal_codes_json TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL,
  technology_watch_required_if_architecture_change INTEGER NOT NULL DEFAULT 1,
  architecture_council_required_if_architecture_change INTEGER NOT NULL DEFAULT 1,
  direct_mutation_allowed INTEGER NOT NULL DEFAULT 0,
  remediation_owner TEXT NOT NULL DEFAULT 'central-orchestrator',
  status TEXT NOT NULL CHECK(status IN ('OPEN','DELIVERED','RESOLVED','DISMISSED')),
  created_at TEXT NOT NULL,
  delivered_at TEXT,
  resolved_at TEXT,
  UNIQUE(guardian_receipt_id,sentinel_receipt_id)
);
CREATE INDEX IF NOT EXISTS idx_exchange_correlations_status
  ON assurance_correlations(status,priority,created_at);
CREATE INDEX IF NOT EXISTS idx_exchange_correlations_project
  ON assurance_correlations(project_id,revision,status,created_at);
