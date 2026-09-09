-- WFGG_SYSTEM_ROLE_SUPERVISOR_V1
-- OWNER reste unique. SUPERVISOR est un droit système séparé du rang d'alliance
-- et n'accorde ici que l'accès à Sentinel ; les autres droits restent pilotés
-- par le rang R1..R5.

CREATE TABLE system_roles_v3 (
  user_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('OWNER','SUPERVISOR')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO system_roles_v3(user_id,role,created_at)
SELECT user_id,role,created_at FROM system_roles;

DROP TABLE system_roles;
ALTER TABLE system_roles_v3 RENAME TO system_roles;

CREATE UNIQUE INDEX IF NOT EXISTS idx_system_roles_single_owner
  ON system_roles(role)
  WHERE role = 'OWNER';

CREATE INDEX IF NOT EXISTS idx_system_roles_role
  ON system_roles(role);

-- Attributions demandées : Flawene (alias Flawen) et Elo.
-- Les variantes historiques d'Elo sont prises en compte ; le compte reste R4.
INSERT OR IGNORE INTO system_roles(user_id,role,created_at)
SELECT u.id,'SUPERVISOR',datetime('now')
FROM users u
JOIN memberships m ON m.user_id=u.id
WHERE m.rank IN ('R4','R5')
  AND (
    lower(trim(u.player_name)) IN ('flawene','flawen')
    OR lower(trim(u.display_name)) IN ('flawene','flawen')
    OR trim(u.player_name) IN ('εlο ツ','εlα ツ','εlo ツ')
    OR trim(u.display_name) IN ('εlο ツ','εlα ツ','εlo ツ')
  )
  AND NOT EXISTS (
    SELECT 1 FROM system_roles sr WHERE sr.user_id=u.id
  );
