import fs from 'node:fs';
const path='frontend/index.html';
let s=fs.readFileSync(path,'utf8');
const before='portal-auth-mobile-guard-v1.js?v=001';
const after='portal-auth-mobile-guard-v1.js?v=002-module-session';
if(!s.includes(after)){
  if(!s.includes(before)) throw new Error('portal auth mobile guard script tag not found');
  s=s.replace(before,after);
  fs.writeFileSync(path,s);
}
console.log('WFGG_PORTAL_MODULE_LINK_CACHE_BUST_V1=OK');
