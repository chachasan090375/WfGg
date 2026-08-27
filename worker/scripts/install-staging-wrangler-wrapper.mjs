import fs from 'node:fs';
import path from 'node:path';

const branch = String(process.env.WORKERS_CI_BRANCH || '').trim();
const isWorkersBuild = String(process.env.WORKERS_CI || '') === '1';

if (!isWorkersBuild || branch !== 'connector-readonly-v1') {
  console.log(`[wfgg staging wrapper] skip (workers_ci=${isWorkersBuild}, branch=${branch || 'unknown'})`);
  process.exit(0);
}

const binDir = path.resolve('node_modules/.bin');
const binPath = path.join(binDir, process.platform === 'win32' ? 'wrangler.cmd' : 'wrangler');
const realCli = path.resolve('node_modules/wrangler/bin/wrangler.js');

if (!fs.existsSync(realCli)) {
  console.error(`[wfgg staging wrapper] real Wrangler CLI missing: ${realCli}`);
  process.exit(1);
}

if (process.platform === 'win32') {
  console.error('[wfgg staging wrapper] Cloudflare Workers Builds is expected to run on Linux.');
  process.exit(1);
}

try {
  fs.rmSync(binPath, { force: true });
} catch (_) {}

const wrapper = `#!/usr/bin/env sh
set -eu
REAL_CLI="${realCli.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"

if [ "\${WORKERS_CI:-}" = "1" ] && [ "\${WORKERS_CI_BRANCH:-}" = "connector-readonly-v1" ] && [ "\${1:-}" = "versions" ] && [ "\${2:-}" = "upload" ]; then
  echo "[wfgg staging wrapper] intercepting Cloudflare preview upload -> wfgg-api-staging deploy"
  if [ "\${WFGG_WRAPPER_TEST_DRY_RUN:-}" = "1" ]; then
    exec node "$REAL_CLI" deploy --env staging --containers-rollout immediate --dry-run --outdir /tmp/wfgg-api-staging-wrapper-test
  fi
  exec node "$REAL_CLI" deploy --env staging --containers-rollout immediate
fi

exec node "$REAL_CLI" "$@"
`;

fs.mkdirSync(binDir, { recursive: true });
fs.writeFileSync(binPath, wrapper, { mode: 0o755 });
console.log(`[wfgg staging wrapper] installed for branch ${branch}: ${binPath}`);
