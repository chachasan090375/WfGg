PRAGMA foreign_keys = ON;

ALTER TABLE memberships
ADD COLUMN officer_title TEXT
CHECK (
  officer_title IS NULL OR
  (rank = 'R4' AND officer_title IN ('WARLORD','RECRUITER','MUSE','BUTLER'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_memberships_single_r5_per_alliance
  ON memberships(alliance_id)
  WHERE rank = 'R5';

CREATE UNIQUE INDEX IF NOT EXISTS idx_memberships_unique_officer_per_alliance
  ON memberships(alliance_id, officer_title)
  WHERE officer_title IS NOT NULL;

CREATE TABLE IF NOT EXISTS system_roles (
  user_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('OWNER')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_system_roles_single_owner
  ON system_roles(role);
