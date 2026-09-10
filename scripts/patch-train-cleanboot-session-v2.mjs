import fs from 'node:fs';

const cleanbootPath='frontend/portal-train-cleanboot-v1.js';
const indexPath='frontend/index.html';

let s=fs.readFileSync(cleanbootPath,'utf8');
if(!s.includes("const VERSION='WFGG_PORTAL_TRAIN_CLEANBOOT_V1';")) throw new Error('cleanboot marker missing');

s=s.replace("const VERSION='WFGG_PORTAL_TRAIN_CLEANBOOT_V1';", "const VERSION='WFGG_PORTAL_TRAIN_CLEANBOOT_V2';\n  const PORTAL_TOKEN_KEY='wfgg_portal_session';");

const oldBlock=`    const url=cleanBootUrl(link);\n    try{\n      await Promise.race([cleanupTrainRuntime(),timeout(1200)]);\n    }catch(_){ }\n    location.assign(url);`;
const newBlock=`    const url=cleanBootUrl(link);\n\n    /* WFGG_TRAIN_CLEANBOOT_SESSION_BRIDGE_V2\n       Le cleanboot intercepte le clic en phase capture. Il doit donc synchroniser\n       lui-même la session module avant toute navigation vers /train/. */\n    const portalToken=String(localStorage.getItem(PORTAL_TOKEN_KEY)||'').trim();\n    if(!portalToken){\n      opening=false;\n      location.assign('/?returnTo='+encodeURIComponent(new URL(url).pathname+new URL(url).search));\n      return;\n    }\n\n    try{\n      const sessionResponse=await fetch('/api/module-session',{\n        method:'POST',\n        headers:{Authorization:'Bearer '+portalToken},\n        cache:'no-store',\n        credentials:'same-origin'\n      });\n      if(!sessionResponse.ok) throw new Error('module_session_'+sessionResponse.status);\n      await Promise.race([cleanupTrainRuntime(),timeout(1200)]);\n      location.assign(url);\n    }catch(_){\n      opening=false;\n      location.assign('/?returnTo='+encodeURIComponent(new URL(url).pathname+new URL(url).search));\n    }`;
if(!s.includes(oldBlock)) throw new Error('navigation block missing');
s=s.replace(oldBlock,newBlock);
fs.writeFileSync(cleanbootPath,s);

let html=fs.readFileSync(indexPath,'utf8');
if(!html.includes('portal-train-cleanboot-v1.js?v=001')) throw new Error('index cleanboot version missing');
html=html.replace('portal-train-cleanboot-v1.js?v=001','portal-train-cleanboot-v1.js?v=002-session-bridge');
fs.writeFileSync(indexPath,html);
