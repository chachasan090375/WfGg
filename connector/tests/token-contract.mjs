import { __test } from '../../worker/src/lastwar-connector.js';
import { webcrypto } from 'node:crypto';

if (!globalThis.crypto) globalThis.crypto = webcrypto;
if (!globalThis.btoa) globalThis.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
if (!globalThis.atob) globalThis.atob = (s) => Buffer.from(s, 'base64').toString('binary');

const env = { APP_SECRET: 'ci-only-secret-not-production' };
const enc = new TextEncoder();

function toBase64Url(bytes) {
  return Buffer.from(bytes).toString('base64url');
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, enc.encode(value));
  return Buffer.from(signature).toString('hex');
}

function fail(message, status = 400) {
  const e = new Error(message);
  e.status = status;
  throw e;
}

const token = await __test.signAccessToken(env, hmacHex, toBase64Url, {
  device_id: 'lwdev_test',
  user_id: 'user_test',
  scope: 'lastwar:sync'
});
const claims = await __test.verifyAccessToken(env, hmacHex, token, fail);
if (claims.device_id !== 'lwdev_test' || claims.user_id !== 'user_test' || claims.scope !== 'lastwar:sync') {
  throw new Error('access-token contract failed');
}

__test.validateProfileShape({
  account: { uid: '123456789', serverId: '1234', playerName: 'CI Player' },
  heroes: [],
  gear: [],
  research: {},
  meta: { gameVersion: 'ci' }
}, fail);

let rejected = false;
try {
  __test.validateProfileShape({
    account: { uid: '123456789', accessToken: 'must-never-upload' }
  }, fail);
} catch (error) {
  rejected = /SENSITIVE_FIELD_REJECTED/.test(error.message);
}
if (!rejected) throw new Error('sensitive-field firewall did not reject an access token');

console.log('CONNECTOR_TOKEN_CONTRACT=PASS');
console.log(`SCHEMA=${__test.SNAPSHOT_SCHEMA}`);
