CREATE TABLE IF NOT EXISTS technical_workflow_attestations (
  repository TEXT NOT NULL,
  revision TEXT NOT NULL,
  workflow_name TEXT NOT NULL,
  workflow_run_id TEXT NOT NULL,
  audit_digest TEXT NOT NULL,
  conclusion TEXT NOT NULL CHECK(conclusion IN ('PASS','BLOCK')),
  attested_at TEXT NOT NULL,
  PRIMARY KEY(repository,revision,workflow_name)
);
CREATE INDEX IF NOT EXISTS idx_technical_workflow_attestations_revision
  ON technical_workflow_attestations(revision,workflow_name,conclusion);
