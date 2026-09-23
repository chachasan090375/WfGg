CREATE TABLE IF NOT EXISTS final_agent_reviews (
  review_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  compromise_digest TEXT NOT NULL,
  source_receipt_id TEXT NOT NULL,
  verdict TEXT NOT NULL,
  hard_objections_json TEXT NOT NULL,
  soft_objections_json TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL,
  implementation_verified INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_guardian_final_reviews_project
  ON final_agent_reviews(project_id,revision,compromise_digest);
