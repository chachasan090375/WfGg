CREATE TABLE IF NOT EXISTS dynamic_role_contracts (
  contract_id TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','RETIRED')),
  template_contract_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  package_id TEXT NOT NULL,
  allowed_actions_json TEXT NOT NULL,
  forbidden_actions_json TEXT NOT NULL,
  allowed_permissions_json TEXT NOT NULL,
  allowed_capabilities_json TEXT NOT NULL,
  allowed_tools_json TEXT NOT NULL,
  source_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retired_at TEXT,
  PRIMARY KEY(contract_id, version)
);
CREATE INDEX IF NOT EXISTS idx_dynamic_role_contracts_active
  ON dynamic_role_contracts(contract_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_dynamic_role_contracts_project
  ON dynamic_role_contracts(project_id, status, created_at);
