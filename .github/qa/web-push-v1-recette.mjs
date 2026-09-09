import fs from 'node:fs';
import assert from 'node:assert/strict';

const worker=fs.readFileSync('frontend/_worker.js','utf8');
const app=fs.readFileSync('frontend/train-native/app.v15.js','utf8');
const sw=fs.readFileSync('frontend/train-native/wfgg-push-sw.js','utf8');
const manifest=JSON.parse(fs.readFileSync('frontend/train-native/manifest.webmanifest','utf8'));

assert.match(worker,/WFGG_TRAIN_PUSH_STATIC_V1/);
assert.match(worker,/WFGG_WEB_PUSH_SW_PRESERVE_V1/);
assert.match(worker,/\/train\/wfgg-push-sw\.js/);
assert.match(worker,/\/train\/manifest\.webmanifest/);
assert.match(app,/WFGG_WEB_PUSH_CLIENT_V1/);
assert.match(app,/Notification\.requestPermission/);
assert.match(app,/pushManager\.subscribe/);
assert.match(app,/\/api\/push\/subscribe/);
assert.match(app,/\/api\/push\/subscription/);
assert.match(app,/WFGG_WEB_PUSH_SW_REGISTER_V1/);
assert.match(app,/isStandaloneApp\(\)/);
assert.match(sw,/self\.addEventListener\('push'/);
assert.match(sw,/showNotification/);
assert.match(sw,/notificationclick/);
assert.equal(manifest.start_url,'/train/');
assert.equal(manifest.scope,'/train/');
assert.equal(manifest.display,'standalone');
console.log('Portal Web Push v1 source contract: PASS');
