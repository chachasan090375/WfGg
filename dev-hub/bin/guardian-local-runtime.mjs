#!/usr/bin/env node
process.env.CHACHA_D1_LOCAL_DB ||= process.env.CHACHA_GUARDIAN_LOCAL_DB || '/opt/chacha-dev/runtime/sovereign-state/shadow/guardian.db';
process.env.CHACHA_D1_LOCAL_PORT ||= process.env.CHACHA_GUARDIAN_LOCAL_PORT || '8871';
process.env.CHACHA_D1_LOCAL_BIND ||= process.env.CHACHA_GUARDIAN_LOCAL_BIND || '127.0.0.1';
process.env.CHACHA_D1_LOCAL_WORKER ||= new URL('../guardian/worker.js',import.meta.url).pathname;
process.env.CHACHA_D1_LOCAL_SERVICE ||= 'chacha-dev-guardian-local-shadow';
await import('./d1-worker-local-runtime.mjs');
