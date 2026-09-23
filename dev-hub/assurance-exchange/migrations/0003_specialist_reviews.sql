CREATE TABLE IF NOT EXISTS specialist_authority_reviews (
  source TEXT NOT NULL,
  receipt_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  compromise_digest TEXT NOT NULL,
  verdict TEXT NOT NULL,
  hard_objections_json TEXT NOT NULL,
  soft_objections_json TEXT NOT NULL,
  evidence_refs_json TEXT NOT NULL,
  implementation_verified INTEGER NOT NULL,
  source_payload_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(source,receipt_id)
);
CREATE INDEX IF NOT EXISTS idx_specialist_reviews_project
  ON specialist_authority_reviews(project_id,revision,compromise_digest,source);
