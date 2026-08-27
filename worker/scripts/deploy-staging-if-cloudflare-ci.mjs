import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const isCloudflareBuild = process.env.WORKERS_CI === '1';
const branch = String(process.env.WORKERS_CI_BRANCH || '');
const allowedBranch = 'connector-readonly-v1';

if (!isCloudflareBuild || branch !== allowedBranch) {
  console.log(`[wfgg-staging] no-op (WORKERS_CI=${process.env.WORKERS_CI || ''}, branch=${branch || 'n/a'})`);
  process.exit(0);
}

if (process.env.WFGG_STAGING_DEPLOY_RUNNING === '1') {
  console.log('[wfgg-staging] recursion guard active; no-op');
  process.exit(0);
}

console.log(`[wfgg-staging] deploying isolated wfgg-api-staging for ${allowedBranch}`);
const wrangler = resolve('node_modules/.bin/wrangler');
const child = spawnSync(wrangler, ['deploy', '--env', 'staging'], {
  cwd: process.cwd(),
  stdio: 'inherit',
  env: {
    ...process.env,
    WFGG_STAGING_DEPLOY_RUNNING: '1'
  }
});

if (child.error) {
  console.error('[wfgg-staging] failed to start wrangler:', child.error.message);
  process.exit(1);
}
if (child.status !== 0) {
  console.error(`[wfgg-staging] wrangler deploy failed with status ${child.status}`);
  process.exit(child.status ?? 1);
}
console.log('[wfgg-staging] isolated staging deployment completed');
