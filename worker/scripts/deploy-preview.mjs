import { spawnSync } from 'node:child_process';
import path from 'node:path';

const branch = String(process.env.WORKERS_CI_BRANCH || process.env.GITHUB_REF_NAME || '').trim();
const realCli = path.resolve('node_modules/wrangler/bin/wrangler.js');
const isConnectorBranch = branch === 'connector-readonly-v1';
const dryRun = process.env.WFGG_PREVIEW_DEPLOY_DRY_RUN === '1';

const args = isConnectorBranch
  ? ['deploy', '--env', 'staging', '--containers-rollout=immediate']
  : ['versions', 'upload'];

if (dryRun) {
  args.push('--dry-run', '--outdir', isConnectorBranch
    ? '/tmp/wfgg-api-staging-preview-command'
    : '/tmp/wfgg-api-standard-preview-command');
}

console.log(`[wfgg preview deploy] branch=${branch || 'unknown'} command=wrangler ${args.join(' ')}`);
const result = spawnSync(process.execPath, [realCli, ...args], {
  stdio: 'inherit',
  env: process.env
});

if (result.error) {
  console.error('[wfgg preview deploy] failed to start Wrangler:', result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
